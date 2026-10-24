"""Lectura del catálogo global existente. No usar Store: su inicio migra la BD."""

import json
import sqlite3
from collections import defaultdict
from contextlib import contextmanager
from pathlib import Path
from decimal import Decimal

from ..identidad import identificar_inmueble
from ..modelos import Inmueble
from ._metrocuadrado import convertir


BASE_PREDETERMINADA = Path(__file__).resolve().parents[2] / 'scraper' / 'data' / 'metro.sqlite'


class ErrorCatalogoSQLite(RuntimeError):
    """Base ilegible, esquema incompatible o documento inválido."""


class CatalogoSQLite:
    def __init__(self, ruta: str | Path = BASE_PREDETERMINADA):
        self.ruta = Path(ruta).resolve()

    @contextmanager
    def _conexion(self):
        if not self.ruta.is_file():
            raise FileNotFoundError(f'No existe la base SQLite del catálogo: {self.ruta}')
        db = None
        try:
            # as_uri escapa espacios, # y ?. mode=ro impide crear la BD incluso
            # si desaparece entre is_file y connect. No usar immutable: omite WAL.
            db = sqlite3.connect(self.ruta.as_uri() + '?mode=ro', uri=True, timeout=5)
            db.row_factory = sqlite3.Row
            db.execute('PRAGMA query_only=ON')
            db.execute('BEGIN')  # Ficha y presencias pertenecen a una misma instantánea.
            yield db
        except sqlite3.Error as exc:
            raise ErrorCatalogoSQLite(
                f'No se pudo leer el catálogo en {self.ruta}. '
                f'Comprueba el acceso y el esquema incremental del scraper: {exc}'
            ) from exc
        finally:
            if db is not None:
                db.close()

    def _leer(self, db, id_original=None):
        condicion = ' WHERE p.id=?' if id_original is not None else ''
        args = (id_original,) if id_original is not None else ()
        filas = db.execute(
            """SELECT p.*,
              (SELECT r.config_json FROM jobs j JOIN runs r ON r.id=j.run_id
               WHERE j.property_id=p.id AND j.data_json=p.data_json
                 AND j.status IN ('success','partial')
               ORDER BY j.run_id DESC LIMIT 1) captura_config
              FROM properties p""" + condicion + ' ORDER BY p.id', args,
        ).fetchall()
        por_anuncio = defaultdict(list)
        consulta = 'SELECT * FROM search_memberships'
        if id_original is not None:
            consulta += ' WHERE property_id=?'
        for presencia in db.execute(consulta + ' ORDER BY property_id,search_url', args):
            por_anuncio[presencia['property_id']].append(presencia)
        resultado = []
        for fila in filas:
            try:
                documento = json.loads(fila['data_json'], parse_float=Decimal) if fila['data_json'] else {}
                config = json.loads(fila['captura_config']) if fila['captura_config'] else {}
                resultado.append(convertir(fila, documento, por_anuncio[fila['id']], config))
            except (ValueError, TypeError, KeyError, IndexError) as exc:
                raise ErrorCatalogoSQLite(
                    f'Datos inválidos en el anuncio {fila["id"]} de {self.ruta}: {exc}'
                ) from exc
        return tuple(resultado)

    def listar(self) -> tuple[Inmueble, ...]:
        """Todos los anuncios globales una vez, ordenados por ID interno."""
        with self._conexion() as db:
            return tuple(sorted(self._leer(db), key=lambda ficha: ficha.id_interno))

    def obtener(self, id_interno: str) -> Inmueble | None:
        """Identidad interna del paso 1; nunca interpreta el parámetro como SQL."""
        if not isinstance(id_interno, str):
            raise TypeError('id_interno debe ser texto')
        with self._conexion() as db:
            # UUID5 no es reversible. Sin añadir columnas ni índices a la BD,
            # se recorre solo la lista de IDs y se carga una única ficha.
            for fila in db.execute('SELECT id FROM properties'):
                if identificar_inmueble('metrocuadrado', fila['id']) == id_interno:
                    return self._leer(db, fila['id'])[0]
            return None
