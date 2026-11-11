"""Revisión comercial y ejecuciones, independientes del catálogo y del scraper."""
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
import json
import sqlite3
from uuid import uuid4
from pathlib import Path
from typing import Protocol

from .persistencia import ErrorPersistencia


def ahora():
    return datetime.now(timezone.utc).isoformat()


class RepositorioSeguimiento(Protocol):
    def leer(self, oportunidad): ...
    def decision(self, oportunidad, inmueble, estado): ...
    def decisiones(self, oportunidad): ...
    def activo(self, cliente): ...
    def activar(self, cliente, activo): ...
    def iniciar(self, oportunidad, huella, forzar=False): ...
    def terminar(self, oportunidad, huella, datos): ...
    def cache(self, clave): ...
    def guardar_cache(self, clave, datos): ...
    def guardar_matching(self, oportunidad, firma, datos): ...
    def registrar_resultados(self, oportunidad, resultados): ...
    def novedades(self, oportunidad): ...
    def marcar_vistas(self, oportunidad, mostradas): ...
    def reservar_gemini(self, oportunidad, solicitud, datos): ...
    def terminar_gemini(self, solicitud, datos): ...
    def actualizar_gemini(self, solicitud, datos): ...
    def ultima_gemini(self, oportunidad): ...


class SeguimientoSQLite:
    def __init__(self, ruta):
        self.ruta = Path(ruta).resolve()

    @contextmanager
    def conexion(self, escribir=False):
        db = None
        try:
            if not escribir and not self.ruta.exists():
                yield None
                return
            if escribir:
                self.ruta.parent.mkdir(parents=True, exist_ok=True)
            db = sqlite3.connect(self.ruta if escribir else self.ruta.as_uri() + '?mode=ro', uri=not escribir, timeout=10)
            db.row_factory = sqlite3.Row
            if escribir:
                db.execute('BEGIN IMMEDIATE')
                db.execute('CREATE TABLE IF NOT EXISTS radar_decisiones (oportunidad TEXT, inmueble TEXT, estado TEXT NOT NULL CHECK(estado IN (\'pendiente\',\'preseleccionado\',\'descartado\')), actualizado TEXT NOT NULL, PRIMARY KEY(oportunidad,inmueble))')
                db.execute('CREATE TABLE IF NOT EXISTS radar_clientes_estado (cliente TEXT PRIMARY KEY, activo INTEGER NOT NULL, actualizado TEXT NOT NULL)')
                db.execute('CREATE TABLE IF NOT EXISTS radar_matching (oportunidad TEXT PRIMARY KEY, huella TEXT NOT NULL, estado TEXT NOT NULL, actualizado TEXT NOT NULL, datos TEXT NOT NULL)')
                db.execute('CREATE TABLE IF NOT EXISTS radar_gemini_cache (clave TEXT PRIMARY KEY, datos TEXT NOT NULL)')
                db.execute('CREATE TABLE IF NOT EXISTS radar_matching_pendiente (oportunidad TEXT PRIMARY KEY)')
                db.execute('CREATE TABLE IF NOT EXISTS radar_novedad_base (oportunidad TEXT PRIMARY KEY, fecha TEXT NOT NULL)')
                db.execute('CREATE TABLE IF NOT EXISTS radar_novedades (oportunidad TEXT, relacion TEXT, detectada TEXT NOT NULL, ultima_deteccion TEXT NOT NULL, tipo TEXT NOT NULL, apariciones INTEGER NOT NULL, presente INTEGER NOT NULL, nueva INTEGER NOT NULL, vista TEXT, PRIMARY KEY(oportunidad,relacion))')
                db.execute('CREATE TABLE IF NOT EXISTS radar_novedad_alias (oportunidad TEXT, alias TEXT, relacion TEXT NOT NULL, PRIMARY KEY(oportunidad,alias))')
                db.execute('CREATE TABLE IF NOT EXISTS radar_novedad_eventos (oportunidad TEXT NOT NULL, relacion TEXT NOT NULL, fecha TEXT NOT NULL, tipo TEXT NOT NULL)')
                db.execute('CREATE TABLE IF NOT EXISTS radar_gemini_ejecuciones (solicitud TEXT PRIMARY KEY, oportunidad TEXT NOT NULL, estado TEXT NOT NULL, fecha TEXT NOT NULL, datos TEXT NOT NULL)')
                db.execute('CREATE UNIQUE INDEX IF NOT EXISTS radar_gemini_activa ON radar_gemini_ejecuciones(oportunidad) WHERE estado=\'procesando\'')
            yield db
            if escribir:
                db.commit()
        except (sqlite3.Error, OSError, ValueError) as exc:
            raise ErrorPersistencia('No se pudo acceder al seguimiento de coincidencias') from exc
        finally:
            if db is not None:
                db.close()

    @staticmethod
    def tabla(db, nombre):
        return db and db.execute('SELECT 1 FROM sqlite_master WHERE name=?', (nombre,)).fetchone()

    def decisiones(self, oportunidad):
        with self.conexion() as db:
            return {r['inmueble']: dict(r) for r in db.execute('SELECT * FROM radar_decisiones WHERE oportunidad=?', (oportunidad,))} if self.tabla(db, 'radar_decisiones') else {}

    def decision(self, oportunidad, inmueble, estado):
        if estado not in ('pendiente', 'preseleccionado', 'descartado'):
            raise ValueError('Selecciona un estado de revisión válido')
        with self.conexion(True) as db:
            db.execute('INSERT INTO radar_decisiones VALUES (?,?,?,?) ON CONFLICT(oportunidad,inmueble) DO UPDATE SET estado=excluded.estado,actualizado=excluded.actualizado', (oportunidad, inmueble, estado, ahora()))

    def activo(self, cliente):
        with self.conexion() as db:
            fila = db.execute('SELECT activo FROM radar_clientes_estado WHERE cliente=?', (cliente,)).fetchone() if self.tabla(db, 'radar_clientes_estado') else None
            return bool(fila['activo']) if fila else True

    def activar(self, cliente, activo):
        with self.conexion(True) as db:
            db.execute('INSERT INTO radar_clientes_estado VALUES (?,?,?) ON CONFLICT(cliente) DO UPDATE SET activo=excluded.activo,actualizado=excluded.actualizado', (cliente, int(activo), ahora()))

    def leer(self, oportunidad):
        with self.conexion() as db:
            fila = db.execute('SELECT * FROM radar_matching WHERE oportunidad=?', (oportunidad,)).fetchone() if self.tabla(db, 'radar_matching') else None
            return dict(fila) | {'datos': json.loads(fila['datos'])} if fila else None

    def iniciar(self, oportunidad, huella, forzar=False):
        with self.conexion(True) as db:
            fila = db.execute('SELECT * FROM radar_matching WHERE oportunidad=?', (oportunidad,)).fetchone()
            if fila:
                if fila['estado'] == 'procesando' and datetime.fromisoformat(fila['actualizado']) > datetime.now(timezone.utc) - timedelta(minutes=10):
                    if fila['huella'] != huella:
                        db.execute('INSERT OR IGNORE INTO radar_matching_pendiente VALUES (?)', (oportunidad,))
                    return False
                if fila['huella'] == huella and fila['estado'] == 'listo' and not forzar:
                    return False
            # Conserva el resultado anterior mientras se evalúa el siguiente.
            datos = fila['datos'] if fila else '{}'
            db.execute('INSERT OR REPLACE INTO radar_matching VALUES (?,?,?,?,?)', (oportunidad, huella, 'procesando', ahora(), datos))
            return True

    def terminar(self, oportunidad, huella, datos):
        with self.conexion(True) as db:
            db.execute("UPDATE radar_matching SET estado='listo',actualizado=?,datos=? WHERE oportunidad=? AND huella=?", (ahora(), json.dumps(datos, ensure_ascii=False), oportunidad, huella))
            pendiente = db.execute('DELETE FROM radar_matching_pendiente WHERE oportunidad=?', (oportunidad,)).rowcount
            return bool(pendiente)

    def cache(self, clave):
        with self.conexion() as db:
            fila = db.execute('SELECT datos FROM radar_gemini_cache WHERE clave=?', (clave,)).fetchone() if self.tabla(db, 'radar_gemini_cache') else None
            return json.loads(fila['datos']) if fila else None

    def guardar_cache(self, clave, datos):
        with self.conexion(True) as db:
            db.execute('INSERT OR REPLACE INTO radar_gemini_cache VALUES (?,?)', (clave, json.dumps(datos, ensure_ascii=False)))

    def guardar_matching(self, oportunidad, firma, datos):
        with self.conexion(True) as db:
            db.execute('INSERT OR REPLACE INTO radar_matching VALUES (?,?,?,?,?)',
                       (oportunidad, firma, 'listo', ahora(), json.dumps(datos, ensure_ascii=False)))
            # Las solicitudes heredadas jamás autorizan una llamada al proveedor.
            db.execute('DELETE FROM radar_matching_pendiente WHERE oportunidad=?', (oportunidad,))

    def registrar_resultados(self, oportunidad, resultados):
        """Línea base aditiva y seguimiento de relaciones, sin deduplicar anuncios."""
        with self.conexion(True) as db:
            fecha = ahora()
            inicial = not db.execute('SELECT 1 FROM radar_novedad_base WHERE oportunidad=?', (oportunidad,)).fetchone()
            db.execute('INSERT OR IGNORE INTO radar_novedad_base VALUES (?,?)', (oportunidad, fecha))
            previas = {r['relacion']: dict(r) for r in db.execute('SELECT * FROM radar_novedades WHERE oportunidad=?', (oportunidad,))}
            presentes = set()
            for r in resultados:
                i = r.inmueble
                identidad = 'g:' + i.inmueble_id if i.inmueble_id else 'p:' + i.id_interno
                aliases = [identidad, *['p:' + p.id_interno for p in (i.publicaciones or (i,))]]
                conocidas = [db.execute('SELECT relacion FROM radar_novedad_alias WHERE oportunidad=? AND alias=?', (oportunidad, a)).fetchone() for a in aliases]
                relacion = next((f['relacion'] for f in conocidas if f), str(uuid4()))
                anterior = previas.get(relacion)
                if relacion in presentes and anterior:
                    # Una separación humana produce relaciones independientes,
                    # conservando la línea base de las publicaciones ya conocidas.
                    relacion = str(uuid4())
                    db.execute('INSERT INTO radar_novedades VALUES (?,?,?,?,?,?,?,?,?)',
                               (oportunidad, relacion, anterior['detectada'], anterior['ultima_deteccion'],
                                anterior['tipo'], anterior['apariciones'], anterior['presente'], anterior['nueva'], anterior['vista']))
                    db.execute('INSERT INTO radar_novedad_eventos SELECT oportunidad,?,fecha,tipo FROM radar_novedad_eventos WHERE oportunidad=? AND relacion=?', (relacion, oportunidad, anterior['relacion']))
                if anterior is None:
                    db.execute('INSERT INTO radar_novedades VALUES (?,?,?,?,?,?,?,?,?)',
                               (oportunidad, relacion, fecha, fecha, 'inicial' if inicial else 'nueva', 1, 1, int(not inicial), fecha if inicial else None))
                    db.execute('INSERT INTO radar_novedad_eventos VALUES (?,?,?,?)', (oportunidad, relacion, fecha, 'inicial' if inicial else 'nueva'))
                elif not anterior['presente']:
                    db.execute("UPDATE radar_novedades SET presente=1,nueva=1,ultima_deteccion=?,tipo='reaparicion',apariciones=apariciones+1 WHERE oportunidad=? AND relacion=?", (fecha, oportunidad, relacion))
                    db.execute('INSERT INTO radar_novedad_eventos VALUES (?,?,?,?)', (oportunidad, relacion, fecha, 'reaparicion'))
                else:
                    db.execute('UPDATE radar_novedades SET presente=1 WHERE oportunidad=? AND relacion=?', (oportunidad, relacion))
                for alias in aliases:
                    db.execute('INSERT OR REPLACE INTO radar_novedad_alias VALUES (?,?,?)', (oportunidad, alias, relacion))
                presentes.add(relacion)
            for relacion in previas.keys() - presentes:
                db.execute('UPDATE radar_novedades SET presente=0 WHERE oportunidad=? AND relacion=?', (oportunidad, relacion))
                if previas[relacion]['presente']:
                    db.execute('INSERT INTO radar_novedad_eventos VALUES (?,?,?,?)', (oportunidad, relacion, fecha, 'desaparicion'))

    def novedades(self, oportunidad):
        with self.conexion() as db:
            if not self.tabla(db, 'radar_novedades'):
                return {}
            return {r['alias']: dict(r) for r in db.execute('SELECT a.alias,n.* FROM radar_novedad_alias a JOIN radar_novedades n USING(oportunidad,relacion) WHERE oportunidad=?', (oportunidad,))}

    def marcar_vistas(self, oportunidad, mostradas):
        with self.conexion(True) as db:
            for relacion, deteccion in mostradas:
                fecha = ahora()
                cambio = db.execute('UPDATE radar_novedades SET nueva=0,vista=? WHERE oportunidad=? AND relacion=? AND ultima_deteccion=? AND presente=1 AND nueva=1', (fecha, oportunidad, relacion, deteccion)).rowcount
                if cambio:
                    db.execute('INSERT INTO radar_novedad_eventos VALUES (?,?,?,?)', (oportunidad, relacion, fecha, 'vista'))

    def reservar_gemini(self, oportunidad, solicitud, datos):
        with self.conexion(True) as db:
            # Lease vencido: estado incierto, nunca reintentar ni consumir automáticamente.
            vencidas = db.execute("SELECT solicitud,datos FROM radar_gemini_ejecuciones WHERE oportunidad=? AND estado='procesando' AND fecha<?", (oportunidad, (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat())).fetchall()
            for fila in vencidas:
                anterior = json.loads(fila['datos']) | {'resultado': 'interrumpida', 'aviso': 'Evaluación interrumpida. El consumo del proveedor puede ser desconocido; hace falta otra solicitud explícita.'}
                db.execute("UPDATE radar_gemini_ejecuciones SET estado='listo',datos=? WHERE solicitud=?", (json.dumps(anterior, ensure_ascii=False), fila['solicitud']))
            if db.execute("SELECT 1 FROM radar_gemini_ejecuciones WHERE solicitud=? OR (oportunidad=? AND estado='procesando')", (solicitud, oportunidad)).fetchone():
                return False
            db.execute('INSERT INTO radar_gemini_ejecuciones VALUES (?,?,?,?,?)', (solicitud, oportunidad, 'procesando', ahora(), json.dumps(datos, ensure_ascii=False)))
            return True

    def terminar_gemini(self, solicitud, datos):
        with self.conexion(True) as db:
            db.execute("UPDATE radar_gemini_ejecuciones SET estado='listo',datos=? WHERE solicitud=? AND estado='procesando'", (json.dumps(datos, ensure_ascii=False), solicitud))

    def actualizar_gemini(self, solicitud, datos):
        with self.conexion(True) as db:
            db.execute("UPDATE radar_gemini_ejecuciones SET datos=? WHERE solicitud=? AND estado='procesando'", (json.dumps(datos, ensure_ascii=False), solicitud))

    def ultima_gemini(self, oportunidad):
        with self.conexion() as db:
            fila = db.execute('SELECT * FROM radar_gemini_ejecuciones WHERE oportunidad=? ORDER BY fecha DESC LIMIT 1', (oportunidad,)).fetchone() if self.tabla(db, 'radar_gemini_ejecuciones') else None
            if not fila:
                return None
            resultado = dict(fila) | {'datos': json.loads(fila['datos'])}
            if fila['estado'] == 'procesando' and datetime.fromisoformat(fila['fecha']) < datetime.now(timezone.utc) - timedelta(minutes=10):
                resultado['estado'] = 'interrumpida'
                resultado['datos']['aviso'] = 'Evaluación interrumpida. El consumo del proveedor puede ser desconocido; otra llamada requiere un clic explícito.'
            return resultado
