"""Identidad física supervisada en la base auxiliar. Migración aditiva perezosa."""
from dataclasses import replace
from itertools import combinations
import json
from typing import Protocol
from uuid import uuid4

from oportunidades.seguimiento import SeguimientoSQLite, ahora
from catalogo.identificacion import VERSION, UMBRAL, candidatos, comparar, hechos, huella


class DecisionInvalida(Exception):
    """Conflicto de revisión; no es un fallo de almacenamiento."""


class RepositorioAsociaciones(Protocol):
    def miembros(self): ...
    def analizar(self, items, completo=False): ...
    def revisar(self, a, b, items): ...
    def decidir(self, a, b, accion, items, firma, aceptar=False): ...
    def proyectar(self, items): ...


class AsociacionesSQLite(SeguimientoSQLite):
    def escritura(self, db):
        db.execute('CREATE TABLE IF NOT EXISTS radar_identificacion_datos (publicacion TEXT PRIMARY KEY, huella TEXT NOT NULL)')
        db.execute('CREATE TABLE IF NOT EXISTS radar_identificacion_pares (a TEXT, b TEXT, evidencia TEXT NOT NULL, estado TEXT NOT NULL, firma_decision TEXT, actor TEXT, fecha TEXT, PRIMARY KEY(a,b))')
        db.execute('CREATE TABLE IF NOT EXISTS radar_inmueble_publicaciones (publicacion TEXT PRIMARY KEY, inmueble TEXT NOT NULL)')
        db.execute('CREATE INDEX IF NOT EXISTS radar_inmueble_miembros ON radar_inmueble_publicaciones(inmueble)')
        db.execute('CREATE TABLE IF NOT EXISTS radar_identificacion_historial (id INTEGER PRIMARY KEY, a TEXT, b TEXT, accion TEXT, actor TEXT, fecha TEXT, evidencia TEXT)')
        db.execute('CREATE TABLE IF NOT EXISTS radar_identificacion_ejecuciones (id INTEGER PRIMARY KEY, fecha TEXT, estado TEXT, detalle TEXT)')

    def miembros(self):
        with self.conexion() as db:
            return dict(db.execute('SELECT publicacion,inmueble FROM radar_inmueble_publicaciones')) if self.tabla(db, 'radar_inmueble_publicaciones') else {}

    def proyectar(self, items):
        mapa = self.miembros()
        grupos = {}
        for i in items:
            if i.id_interno in mapa:
                grupos.setdefault(mapa[i.id_interno], []).append(i)
        return tuple(replace(i, inmueble_id=mapa.get(i.id_interno),
                             publicaciones=tuple(sorted(grupos.get(mapa.get(i.id_interno), ()), key=lambda p: p.id_interno))) for i in items)

    def pares(self):
        with self.conexion() as db:
            if not self.tabla(db, 'radar_identificacion_pares'):
                return []
            return [dict(r) | {'evidencia': json.loads(r['evidencia'])} for r in db.execute('SELECT * FROM radar_identificacion_pares')]

    def ejecucion(self):
        with self.conexion() as db:
            r = db.execute('SELECT * FROM radar_identificacion_ejecuciones ORDER BY id DESC LIMIT 1').fetchone() if self.tabla(db, 'radar_identificacion_ejecuciones') else None
            return dict(r) if r else None

    def analizar(self, items, completo=False):
        items = tuple(items)
        try:
            with self.conexion(True) as db:
                self.escritura(db)
                previas = dict(db.execute('SELECT publicacion,huella FROM radar_identificacion_datos'))
                firmas = {i.id_interno: huella([VERSION, hechos(i)]) for i in items}
                nuevos = {k for k, v in firmas.items() if completo or previas.get(k) != v}
                por_id = {i.id_interno: i for i in items}
                pruebas = {(e['a'], e['b']): e for e in candidatos(items, nuevos)}
                # Refresca también descartes/confirmaciones que dejaron de compartir bloque.
                for r in db.execute('SELECT a,b FROM radar_identificacion_pares'):
                    if (r['a'] in nuevos or r['b'] in nuevos) and r['a'] in por_id and r['b'] in por_id:
                        pruebas[r['a'], r['b']] = comparar(por_id[r['a']], por_id[r['b']])
                for (a,b), e in pruebas.items():
                    existe = db.execute('SELECT 1 FROM radar_identificacion_pares WHERE a=? AND b=?', (a,b)).fetchone()
                    if e['puntuacion'] >= UMBRAL or existe:
                        db.execute("INSERT INTO radar_identificacion_pares(a,b,evidencia,estado) VALUES (?,?,?,'pendiente') ON CONFLICT(a,b) DO UPDATE SET evidencia=excluded.evidencia", (a,b,json.dumps(e, default=str, ensure_ascii=False)))
                db.executemany('INSERT OR REPLACE INTO radar_identificacion_datos VALUES (?,?)', firmas.items())
                db.execute('INSERT INTO radar_identificacion_ejecuciones(fecha,estado,detalle) VALUES (?,?,?)', (ahora(), 'correcto', f'{len(nuevos)} publicaciones nuevas/modificadas; {len(pruebas)} pares evaluados'))
            return len(pruebas)
        except Exception as exc:
            with self.conexion(True) as db:
                self.escritura(db)
                db.execute('INSERT INTO radar_identificacion_ejecuciones(fecha,estado,detalle) VALUES (?,?,?)', (ahora(), 'error', type(exc).__name__))
            raise

    @staticmethod
    def _revision(a, b, items, mapa):
        por_id = {i.id_interno: i for i in items}
        if a == b or a not in por_id or b not in por_id:
            raise DecisionInvalida('Las dos publicaciones deben estar disponibles y ser distintas.')
        ids = {a,b} | {k for k,v in mapa.items() if v in {mapa.get(a), mapa.get(b)}}
        if ids - por_id.keys():
            raise DecisionInvalida('Faltan publicaciones del grupo. Restaura su fuente antes de cambiar la asociación.')
        relaciones = [comparar(por_id[x], por_id[y]) for x,y in combinations(sorted(ids), 2)]
        firma = huella([sorted((k,mapa.get(k)) for k in ids), [r['huella'] for r in relaciones]])
        return {'ids': sorted(ids), 'relaciones': relaciones, 'firma': firma}

    def revisar(self, a, b, items):
        return self._revision(a, b, items, self.miembros())

    def decidir(self, a, b, accion, items, firma, aceptar=False):
        if accion not in ('confirmado', 'descartado', 'despues', 'deshacer'):
            raise DecisionInvalida('Acción desconocida.')
        a,b = sorted((a,b))
        with self.conexion(True) as db:
            self.escritura(db)
            mapa = dict(db.execute('SELECT publicacion,inmueble FROM radar_inmueble_publicaciones'))
            revision = self._revision(a,b,items,mapa)
            if firma != revision['firma']:
                raise DecisionInvalida('Los datos o el grupo cambiaron. Vuelve a revisar antes de decidir.')
            if accion in ('confirmado', 'deshacer') and not aceptar:
                raise DecisionInvalida('Confirma que revisaste todas las relaciones y el efecto de esta acción.')
            actor = 'operadora local (sin autenticación)'
            fecha = ahora()
            if accion == 'deshacer':
                if mapa.get(a) is None or mapa.get(a) != mapa.get(b):
                    raise DecisionInvalida('Estas publicaciones no están agrupadas.')
                # Disuelve todo el grupo explícitamente; no deja enlaces transitivos ocultos.
                db.execute('DELETE FROM radar_inmueble_publicaciones WHERE inmueble=?', (mapa[a],))
                for x,y in combinations(revision['ids'], 2):
                    db.execute("UPDATE radar_identificacion_pares SET estado='pendiente',firma_decision=NULL,actor=?,fecha=? WHERE a=? AND b=?", (actor,fecha,x,y))
            elif accion == 'confirmado':
                for e in revision['relaciones']:
                    r = db.execute('SELECT estado FROM radar_identificacion_pares WHERE a=? AND b=?', (e['a'],e['b'])).fetchone()
                    if r and r['estado'] == 'descartado':
                        raise DecisionInvalida('Hay una relación descartada. Devuélvela a revisión antes de confirmar el grupo.')
                gid = min((mapa[k] for k in revision['ids'] if k in mapa), default=str(uuid4()))
                for iid in revision['ids']:
                    db.execute('INSERT OR REPLACE INTO radar_inmueble_publicaciones VALUES (?,?)', (iid,gid))
            elif accion in ('descartado', 'despues') and mapa.get(a) and mapa.get(a) == mapa.get(b):
                raise DecisionInvalida('Deshaz primero la asociación confirmada.')
            relaciones = revision['relaciones'] if accion == 'confirmado' else [e for e in revision['relaciones'] if (e['a'],e['b']) == (a,b)]
            for e in relaciones:
                estado = 'pendiente' if accion in ('despues','deshacer') else accion
                db.execute('INSERT INTO radar_identificacion_pares VALUES (?,?,?,?,?,?,?) ON CONFLICT(a,b) DO UPDATE SET evidencia=excluded.evidencia,estado=excluded.estado,firma_decision=excluded.firma_decision,actor=excluded.actor,fecha=excluded.fecha',
                           (e['a'],e['b'],json.dumps(e,default=str,ensure_ascii=False),estado,e['huella'],actor,fecha))
            db.execute('INSERT INTO radar_identificacion_historial(a,b,accion,actor,fecha,evidencia) VALUES (?,?,?,?,?,?)', (a,b,accion,actor,fecha,json.dumps(revision,default=str,ensure_ascii=False)))
