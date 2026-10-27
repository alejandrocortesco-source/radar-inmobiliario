"""Proyección geográfica auxiliar; nunca migra ni escribe la BD del scraper.

Las lecturas no crean archivos. Cada fila es válida solo para el documento,
ciudad y versión de reglas que la originaron. Una captura nueva se normaliza
en memoria hasta el siguiente reprocesamiento explícito.
"""
from dataclasses import asdict
from contextlib import closing
from hashlib import sha256
import json
from pathlib import Path
import sqlite3

from . import Geografia, VERSION


def ruta_proyeccion(origen):
    return Path(origen).with_name(Path(origen).stem + '-geografia.sqlite')


def huella_documento(data_json, ciudad):
    return sha256(json.dumps([data_json, ciudad], ensure_ascii=False).encode()).hexdigest()


def leer(origen):
    ruta = ruta_proyeccion(origen)
    if not ruta.is_file():
        return {}
    try:
        with closing(sqlite3.connect(ruta.resolve().as_uri() + '?mode=ro', uri=True)) as db:
            return {id: (huella, json.loads(datos)) for id, huella, datos in db.execute(
                'SELECT id_original, huella_documento, datos_json FROM ubicaciones WHERE version=?', (VERSION,))}
    except (sqlite3.Error, ValueError):
        # Caché auxiliar ausente o inválida: se recalcula sin escribirla.
        return {}


def recuperar(cache, fila):
    entrada = cache.get(fila['id'])
    if not entrada or entrada[0] != huella_documento(fila['data_json'], fila['city']):
        return None
    try:
        datos = dict(entrada[1])
        datos['motivos'] = tuple(datos['motivos'])
        datos['evidencias'] = tuple(datos['evidencias'])
        return Geografia(**datos)
    except (TypeError, ValueError, KeyError):
        return None


def reprocesar(origen, destino=None):
    """Migración transaccional, aditiva e idempotente. Devuelve filas cambiadas."""
    from ..persistencia.sqlite import CatalogoSQLite
    origen = Path(origen).resolve()
    destino = Path(destino).resolve() if destino else ruta_proyeccion(origen)
    if destino == origen:
        raise ValueError('La proyección debe ser distinta de la base del scraper')
    repo = CatalogoSQLite(origen)
    with repo._conexion() as lectura:
        por_id = {r.inmueble.origen.id_original: r.inmueble for r in repo._leer_registros(lectura)}
        filas = lectura.execute('SELECT id, data_json, city FROM properties').fetchall()
    destino.parent.mkdir(parents=True, exist_ok=True)
    cambios = 0
    with closing(sqlite3.connect(destino)) as db, db:
        db.execute('BEGIN IMMEDIATE')
        db.execute('CREATE TABLE IF NOT EXISTS migraciones (version INTEGER PRIMARY KEY)')
        db.execute('''CREATE TABLE IF NOT EXISTS ubicaciones (
            id_original TEXT PRIMARY KEY, id_interno TEXT NOT NULL,
            huella_documento TEXT NOT NULL, version TEXT NOT NULL,
            datos_json TEXT NOT NULL, actualizado TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)''')
        db.execute('INSERT OR IGNORE INTO migraciones VALUES (1)')
        for id, documento, ciudad in filas:
            i = por_id[id]
            cursor = db.execute('''INSERT INTO ubicaciones
                (id_original,id_interno,huella_documento,version,datos_json) VALUES (?,?,?,?,?)
                ON CONFLICT(id_original) DO UPDATE SET
                huella_documento=excluded.huella_documento, version=excluded.version,
                datos_json=excluded.datos_json, actualizado=CURRENT_TIMESTAMP
                WHERE ubicaciones.huella_documento!=excluded.huella_documento
                   OR ubicaciones.version!=excluded.version
                   OR ubicaciones.datos_json!=excluded.datos_json''',
                (id, i.id_interno, huella_documento(documento, ciudad), VERSION,
                 json.dumps(asdict(i.geografia), ensure_ascii=False)))
            cambios += cursor.rowcount
    return {'total': len(filas), 'actualizados': cambios, 'destino': str(destino), 'version': VERSION}
