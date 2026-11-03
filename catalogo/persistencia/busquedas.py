"""Nombres de búsquedas en la base auxiliar; nunca escribe en el scraper."""
from contextlib import closing
from pathlib import Path
import sqlite3

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
                return tuple(dict(r) for r in db.execute('SELECT * FROM consola_busquedas ORDER BY fuente,nombre,id_busqueda'))
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
