"""Lectura del catálogo global existente. No usar Store: su inicio migra la BD."""

import json
import sqlite3
from collections import defaultdict
from contextlib import contextmanager
from pathlib import Path
from decimal import Decimal
from datetime import datetime

from ..identidad import identificar_inmueble
from ..modelos import CategoriaActualizacion, Inmueble
from ..geografia.persistencia import leer as leer_geografia, recuperar as recuperar_geografia
from ._metrocuadrado import convertir
from .contrato import ErrorLecturaCatalogo, RegistroCatalogo, RevisionCatalogo


BASE_PREDETERMINADA = Path(__file__).resolve().parents[2] / 'scraper' / 'data' / 'metro.sqlite'


class ErrorCatalogoSQLite(ErrorLecturaCatalogo):
    """Base ilegible, esquema incompatible o documento inválido."""


class CatalogoSQLite:
    def __init__(self, ruta: str | Path = BASE_PREDETERMINADA, *, fuente='metrocuadrado'):
        self.ruta = Path(ruta).resolve()
        self.fuente = fuente

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

    def _categorias_actualizacion(self, db):
        # Última ejecución exitosa por búsqueda, incluso si no observó inmuebles.
        # Se lee en la misma transacción que las fichas; no se recalculan decisiones.
        actualizaciones = {}
        tablas = {r['name'] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not {'run_searches', 'listing_observations', 'price_changes'} <= tablas:
            # Catálogos anteriores sin evidencia incremental: ninguna categoría inferida.
            return actualizaciones
        for r in db.execute('''
            WITH ultimas AS (
                SELECT s.search_url, max(r.id) run_id FROM run_searches s
                JOIN runs r ON r.id=s.run_id WHERE r.status='completed'
                GROUP BY s.search_url
            )
            SELECT o.search_url, j.property_id, j.classification,
                   c.id cambio FROM ultimas u
            JOIN listing_observations o ON o.run_id=u.run_id AND o.search_url=u.search_url
            JOIN jobs j ON j.run_id=o.run_id AND j.property_id=o.property_id
            LEFT JOIN price_changes c ON c.run_id=j.run_id AND c.property_id=j.property_id
        '''):
            categorias = set()
            categoria = {'new': CategoriaActualizacion.NUEVOS,
                         'modified': CategoriaActualizacion.CAMBIO_PRECIO,
                         'review': CategoriaActualizacion.REVISION}.get(r['classification'])
            if categoria:
                categorias.add(categoria)
            if r['cambio'] is not None:
                categorias.add(CategoriaActualizacion.CAMBIO_PRECIO)
            actualizaciones[(r['search_url'], r['property_id'])] = tuple(sorted(categorias))
        return actualizaciones

    def _leer_registros(self, db, id_original=None):
        actualizaciones = self._categorias_actualizacion(db)
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
        geografia = leer_geografia(self.ruta)
        for fila in filas:
            try:
                documento = json.loads(fila['data_json'], parse_float=Decimal) if fila['data_json'] else {}
                config = json.loads(fila['captura_config']) if fila['captura_config'] else {}
                resultado.append(RegistroCatalogo(
                    inmueble=convertir(fila, documento, por_anuncio[fila['id']], config,
                                       geografia=recuperar_geografia(geografia, fila),
                                       actualizaciones=actualizaciones, fuente=self.fuente),
                    documento=json.loads(fila['data_json']) if fila['data_json'] else None,
                    resumen={**{k: fila[k] for k in (
                        'id', 'url', 'title', 'price', 'city', 'property_type', 'needs_refresh')},
                        **({'url': (documento.get('normalized') or {}).get('url')} if self.fuente == 'wasi' else {})},
                    presencias=tuple(dict(p) for p in por_anuncio[fila['id']]),
                ))
            except (ValueError, TypeError, KeyError, IndexError) as exc:
                raise ErrorCatalogoSQLite(
                    f'Datos inválidos en el anuncio {fila["id"]} de {self.ruta}: {exc}'
                ) from exc
        return tuple(resultado)

    def listar(self) -> tuple[Inmueble, ...]:
        """Todos los anuncios globales una vez, ordenados por ID interno."""
        with self._conexion() as db:
            return tuple(sorted(self._leer(db), key=lambda ficha: ficha.id_interno))

    def ultima_actualizacion(self):
        """Finalización exitosa más reciente del catálogo global, sin filtros."""
        with self._conexion() as db:
            columnas = {r['name'] for r in db.execute('PRAGMA table_info(runs)')}
            if not {'finished', 'status'} <= columnas:
                return None
            fechas = []
            for r in db.execute("SELECT finished FROM runs WHERE status='completed' AND finished IS NOT NULL"):
                try:
                    valor = datetime.fromisoformat(r['finished'].replace('Z', '+00:00'))
                    if valor.tzinfo is not None:
                        fechas.append(valor)
                except (ValueError, TypeError):
                    continue
            return max(fechas, default=None)

    def obtener(self, id_interno: str) -> Inmueble | None:
        """Identidad interna del paso 1; nunca interpreta el parámetro como SQL."""
        if not isinstance(id_interno, str):
            raise TypeError('id_interno debe ser texto')
        with self._conexion() as db:
            # UUID5 no es reversible. Sin añadir columnas ni índices a la BD,
            # se recorre solo la lista de IDs y se carga una única ficha.
            for fila in db.execute('SELECT id FROM properties'):
                if identificar_inmueble(self.fuente, fila['id']) == id_interno:
                    return self._leer(db, fila['id'])[0]
            return None

    def _leer(self, db, id_original=None):
        return tuple(r.inmueble for r in self._leer_registros(db, id_original))

    def listar_registros(self):
        with self._conexion() as db:
            return self._leer_registros(db)

    def obtener_revision(self, identificador):
        with self._conexion() as db:
            fila = db.execute('SELECT id FROM properties WHERE id=?', (identificador,)).fetchone()
            if fila is None:
                fila = next((r for r in db.execute('SELECT id FROM properties')
                             if identificar_inmueble(self.fuente, r['id']) == identificador), None)
            if fila is None:
                return None
            original = fila['id']
            registro = self._leer_registros(db, original)[0]
            trabajos = tuple(dict(r) for r in db.execute(
                'SELECT * FROM jobs WHERE property_id=? ORDER BY run_id DESC', (original,)))
            apariciones = tuple(dict(r) for r in db.execute(
                'SELECT run_id,page,url,search_url FROM appearances WHERE property_id=? '
                'ORDER BY run_id,search_url,page', (original,)))
            historial = [dict(r) for r in db.execute(
                'SELECT * FROM price_changes WHERE property_id=? ORDER BY id', (original,))]
            try:
                for cambio in historial:
                    for clave in ('previous_price_json', 'new_price_json', 'detail_price_json'):
                        valor = cambio.pop(clave)
                        cambio[clave.removesuffix('_json')] = json.loads(valor) if valor else None
                return RevisionCatalogo(
                    registro=registro, documento=registro.documento,
                    trabajos=trabajos, apariciones=apariciones, historial=tuple(historial),
                )
            except (ValueError, TypeError) as exc:
                raise ErrorCatalogoSQLite(f'Evidencia inválida en el anuncio {original}') from exc
