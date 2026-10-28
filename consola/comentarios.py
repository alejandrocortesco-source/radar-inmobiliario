"""Una observación por ID interno; adición independiente del esquema de v0.3."""
import sqlite3
from oportunidades.persistencia import ErrorPersistencia


class Comentarios:
    def __init__(self, ruta):
        self.ruta = ruta

    def leer(self, identificador):
        if not self.ruta.exists():
            return ''
        try:
            with sqlite3.connect(self.ruta.as_uri() + '?mode=ro', uri=True, timeout=10) as db:
                if not db.execute("SELECT 1 FROM sqlite_master WHERE name='consola_comentarios'").fetchone():
                    return ''
                fila = db.execute('SELECT texto FROM consola_comentarios WHERE inmueble_id=?', (identificador,)).fetchone()
                return fila[0] if fila else ''
        except (OSError, sqlite3.Error) as exc:
            raise ErrorPersistencia('No se pudo leer el comentario. Vuelve a intentar.') from exc

    def guardar(self, identificador, texto):
        try:
            self.ruta.parent.mkdir(parents=True, exist_ok=True)
            with sqlite3.connect(self.ruta, timeout=10) as db:
                db.execute('BEGIN IMMEDIATE')
                db.execute('CREATE TABLE IF NOT EXISTS consola_comentarios (inmueble_id TEXT PRIMARY KEY, texto TEXT NOT NULL)')
                db.execute('INSERT INTO consola_comentarios VALUES (?,?) ON CONFLICT(inmueble_id) DO UPDATE SET texto=excluded.texto', (identificador, texto))
        except (OSError, sqlite3.Error) as exc:
            raise ErrorPersistencia('No se pudo guardar. El texto se conserva; vuelve a intentar.') from exc
