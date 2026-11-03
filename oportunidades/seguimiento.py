"""Revisión comercial y ejecuciones, independientes del catálogo y del scraper."""
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
import json
import sqlite3
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
