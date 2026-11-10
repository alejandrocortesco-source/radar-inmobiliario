"""Nombres de búsquedas en la base auxiliar; nunca escribe en el scraper."""
from contextlib import closing
from pathlib import Path
import sqlite3
import json

from .contrato import ErrorLecturaCatalogo


class BusquedasSQLite:
    def __init__(self, ruta):
        self.ruta = Path(ruta).resolve()

    def listar(self):
        if not self.ruta.exists():
            return ()
        try:
            with closing(sqlite3.connect(self.ruta.as_uri() + '?mode=ro', uri=True)) as db:
                db.row_factory = sqlite3.Row
                if not db.execute("SELECT 1 FROM sqlite_master WHERE name='consola_busquedas'").fetchone():
                    return ()
                filas = [dict(r) for r in db.execute('SELECT * FROM consola_busquedas ORDER BY fuente,nombre,id_busqueda')]
                estados = {}
                if db.execute("SELECT 1 FROM sqlite_master WHERE name='radar_busquedas_estado'").fetchone():
                    estados = {(r['fuente'], r['id_busqueda']): bool(r['activa']) for r in db.execute('SELECT * FROM radar_busquedas_estado')}
                return tuple({**r, 'activa': estados.get((r['fuente'], r['id_busqueda']), True)} for r in filas)
        except (sqlite3.Error, OSError) as exc:
            raise ErrorLecturaCatalogo('No se pudieron leer los nombres de búsquedas') from exc

    def guardar(self, fuente, id_busqueda, url, nombre):
        try:
            self.ruta.parent.mkdir(parents=True, exist_ok=True)
            with closing(sqlite3.connect(self.ruta, timeout=10)) as db:
                with db:
                    db.execute('CREATE TABLE IF NOT EXISTS consola_busquedas (fuente TEXT NOT NULL, id_busqueda TEXT NOT NULL, url TEXT NOT NULL, nombre TEXT NOT NULL, PRIMARY KEY(fuente,id_busqueda))')
                    db.execute('INSERT INTO consola_busquedas VALUES (?,?,?,?) ON CONFLICT(fuente,id_busqueda) DO UPDATE SET url=excluded.url,nombre=excluded.nombre',
                               (fuente, id_busqueda, url, nombre))
        except (sqlite3.Error, OSError) as exc:
            raise ErrorLecturaCatalogo('No se pudo guardar el nombre de la búsqueda') from exc

    def opciones_wasi(self):
        from ..fuentes.wasi import opciones_iniciales
        resultado = opciones_iniciales()
        if not self.ruta.exists():
            return resultado
        try:
            with closing(sqlite3.connect(self.ruta.as_uri() + '?mode=ro', uri=True)) as db:
                if db.execute("SELECT 1 FROM sqlite_master WHERE name='radar_wasi_opciones'").fetchone():
                    resultado.update({k: json.loads(v) for k, v in db.execute('SELECT clave,opciones FROM radar_wasi_opciones')})
        except (sqlite3.Error, ValueError) as exc:
            raise ErrorLecturaCatalogo('No se pudieron leer las opciones de Wasi') from exc
        return resultado

    def guardar_opciones_wasi(self, registros):
        try:
            self.ruta.parent.mkdir(parents=True, exist_ok=True)
            with closing(sqlite3.connect(self.ruta)) as db, db:
                db.execute('CREATE TABLE IF NOT EXISTS radar_wasi_opciones(clave TEXT PRIMARY KEY,opciones TEXT NOT NULL)')
                db.executemany('INSERT OR REPLACE INTO radar_wasi_opciones VALUES (?,?)',
                               [(k, json.dumps(v, ensure_ascii=False)) for k, v in registros.items()])
        except (sqlite3.Error, OSError) as exc:
            raise ErrorLecturaCatalogo('No se pudieron guardar las opciones de Wasi') from exc

    def configuracion_wasi(self, identificador):
        if not self.ruta.exists():
            return None
        try:
            with closing(sqlite3.connect(self.ruta.as_uri() + '?mode=ro', uri=True)) as db:
                if not db.execute("SELECT 1 FROM sqlite_master WHERE name='radar_wasi_busquedas'").fetchone():
                    return None
                fila = db.execute('SELECT config FROM radar_wasi_busquedas WHERE id=?', (identificador,)).fetchone()
                return json.loads(fila[0]) if fila else None
        except (sqlite3.Error, OSError, ValueError) as exc:
            raise ErrorLecturaCatalogo('No se pudo leer la configuración Wasi') from exc

    def guardar_wasi(self, nombre, config, reemplazar=None):
        from ..fuentes.wasi import RED, identidad
        identificador = identidad(config)
        if not isinstance(nombre, str) or not nombre.strip() or len(nombre.strip()) > 120:
            raise ValueError('El nombre debe tener entre 1 y 120 caracteres')
        self.ruta.parent.mkdir(parents=True, exist_ok=True)
        try:
            with closing(sqlite3.connect(self.ruta, timeout=10)) as db, db:
                db.execute('CREATE TABLE IF NOT EXISTS consola_busquedas (fuente TEXT NOT NULL, id_busqueda TEXT NOT NULL, url TEXT NOT NULL, nombre TEXT NOT NULL, PRIMARY KEY(fuente,id_busqueda))')
                db.execute('CREATE TABLE IF NOT EXISTS radar_wasi_busquedas(id TEXT PRIMARY KEY, config TEXT NOT NULL)')
                # Los IDs/filtros son estables; un guardado explícito puede
                # actualizar etiquetas del portal. Cada run conserva su snapshot.
                db.execute('INSERT INTO radar_wasi_busquedas VALUES (?,?) ON CONFLICT(id) DO UPDATE SET config=excluded.config',
                           (identificador, json.dumps(config, ensure_ascii=False)))
                db.execute("INSERT INTO consola_busquedas VALUES ('wasi',?,?,?) ON CONFLICT(fuente,id_busqueda) DO UPDATE SET nombre=excluded.nombre",
                           (identificador, RED, nombre.strip()))
                if reemplazar and reemplazar != identificador:
                    db.execute("DELETE FROM consola_busquedas WHERE fuente='wasi' AND id_busqueda=?", (reemplazar,))
        except sqlite3.Error as exc:
            raise ErrorLecturaCatalogo('No se pudo guardar la búsqueda Wasi') from exc
        return identificador

    def eliminar(self, fuente, id_busqueda):
        """Quita configuración auxiliar; conserva el catálogo y sus procedencias."""
        if not self.ruta.exists():
            return False
        try:
            with closing(sqlite3.connect(self.ruta.as_uri() + '?mode=rw', uri=True, timeout=10)) as db:
                with db:
                    if not db.execute("SELECT 1 FROM sqlite_master WHERE name='consola_busquedas'").fetchone():
                        return False
                    return db.execute('DELETE FROM consola_busquedas WHERE fuente=? AND id_busqueda=?',
                                      (fuente, id_busqueda)).rowcount > 0
        except (sqlite3.Error, OSError) as exc:
            raise ErrorLecturaCatalogo('No se pudo eliminar la búsqueda') from exc
    def opciones_fincaraiz(self):
        from ..fuentes.fincaraiz import opciones_iniciales
        opciones = {c['url_efectiva']: c for c in opciones_iniciales()}
        if self.ruta.exists():
            with closing(sqlite3.connect(self.ruta.as_uri() + '?mode=ro', uri=True)) as db:
                if db.execute("SELECT 1 FROM sqlite_master WHERE name='radar_fincaraiz_busquedas'").fetchone():
                    for (raw,) in db.execute('SELECT config FROM radar_fincaraiz_busquedas'):
                        c = json.loads(raw)
                        if c.get('criterios'):
                            opciones[c['url_efectiva']] = c
        return list(opciones.values())

    def configuracion_fincaraiz(self, identificador):
        if not self.ruta.exists():
            return None
        with closing(sqlite3.connect(self.ruta.as_uri() + '?mode=ro', uri=True)) as db:
            if not db.execute("SELECT 1 FROM sqlite_master WHERE name='radar_fincaraiz_busquedas'").fetchone():
                return None
            fila = db.execute('SELECT config FROM radar_fincaraiz_busquedas WHERE id=?', (identificador,)).fetchone()
            return json.loads(fila[0]) if fila else None

    def guardar_fincaraiz(self, nombre, config, reemplazar=None):
        from ..fuentes.fincaraiz import identidad
        key = identidad(config['url_efectiva'])
        if not isinstance(nombre, str) or not 1 <= len(nombre.strip()) <= 120:
            raise ValueError('El nombre debe tener entre 1 y 120 caracteres')
        if not isinstance(config.get('filtros'), dict):
            raise ValueError('Faltan filtros verificados por el portal')
        self.ruta.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.ruta, timeout=10)) as db, db:
            db.execute('CREATE TABLE IF NOT EXISTS consola_busquedas (fuente TEXT NOT NULL, id_busqueda TEXT NOT NULL, url TEXT NOT NULL, nombre TEXT NOT NULL, PRIMARY KEY(fuente,id_busqueda))')
            db.execute('CREATE TABLE IF NOT EXISTS radar_fincaraiz_busquedas(id TEXT PRIMARY KEY, config TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS radar_fincaraiz_revisiones(id INTEGER PRIMARY KEY, busqueda TEXT NOT NULL, config TEXT NOT NULL, fecha TEXT DEFAULT CURRENT_TIMESTAMP)')
            db.execute('CREATE TABLE IF NOT EXISTS radar_busquedas_estado(fuente TEXT NOT NULL,id_busqueda TEXT NOT NULL,activa INTEGER NOT NULL DEFAULT 1,PRIMARY KEY(fuente,id_busqueda))')
            if reemplazar and not db.execute("SELECT 1 FROM consola_busquedas WHERE fuente='fincaraiz' AND id_busqueda=?", (reemplazar,)).fetchone():
                raise ValueError('La búsqueda a editar ya no existe')
            raw = json.dumps(config, ensure_ascii=False)
            db.execute('INSERT INTO radar_fincaraiz_busquedas VALUES (?,?) ON CONFLICT(id) DO UPDATE SET config=excluded.config', (key, raw))
            db.execute('INSERT INTO radar_fincaraiz_revisiones(busqueda,config) VALUES (?,?)', (key, raw))
            db.execute("INSERT INTO consola_busquedas VALUES ('fincaraiz',?,?,?) ON CONFLICT(fuente,id_busqueda) DO UPDATE SET url=excluded.url,nombre=excluded.nombre", (key, config['url_efectiva'], nombre.strip()))
            if reemplazar and reemplazar != key:
                db.execute("DELETE FROM consola_busquedas WHERE fuente='fincaraiz' AND id_busqueda=?", (reemplazar,))
                old = db.execute("SELECT activa FROM radar_busquedas_estado WHERE fuente='fincaraiz' AND id_busqueda=?", (reemplazar,)).fetchone()
                db.execute("INSERT OR REPLACE INTO radar_busquedas_estado VALUES ('fincaraiz',?,?)", (key, old[0] if old else 1))
        return key

    def cambiar_estado(self, fuente, identificador, activa):
        if not self.ruta.exists():
            raise ValueError('Búsqueda inexistente')
        with closing(sqlite3.connect(self.ruta, timeout=10)) as db, db:
            if not db.execute('SELECT 1 FROM consola_busquedas WHERE fuente=? AND id_busqueda=?', (fuente, identificador)).fetchone():
                raise ValueError('Búsqueda inexistente')
            db.execute('CREATE TABLE IF NOT EXISTS radar_busquedas_estado(fuente TEXT NOT NULL,id_busqueda TEXT NOT NULL,activa INTEGER NOT NULL DEFAULT 1,PRIMARY KEY(fuente,id_busqueda))')
            db.execute('INSERT OR REPLACE INTO radar_busquedas_estado VALUES (?,?,?)', (fuente, identificador, int(activa)))
