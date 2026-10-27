"""Repositorio sustituible; SQLite propio, migración aditiva y transaccional."""
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
from typing import Protocol
from uuid import uuid4
from pydantic import ValidationError

from .modelos import Cliente, ClienteDatos, Oportunidad, OportunidadDatos


class NoEncontrado(ValueError):
    pass


class ErrorPersistencia(RuntimeError):
    pass


class Repositorio(Protocol):
    def clientes(self) -> list[Cliente]: ...
    def cliente(self, identificador: str) -> Cliente: ...
    def guardar_cliente(self, datos: ClienteDatos, identificador: str | None = None) -> Cliente: ...
    def oportunidades(self) -> list[Oportunidad]: ...
    def oportunidad(self, identificador: str) -> Oportunidad: ...
    def guardar_oportunidad(self, datos: OportunidadDatos, identificador: str | None = None) -> Oportunidad: ...
    def capturar(self, cliente: ClienteDatos, necesidades, estado: str,
                 cliente_id: str | None, oportunidad_id: str | None) -> Oportunidad: ...


class SQLite:
    def __init__(self, ruta: str | Path):
        self.ruta = Path(ruta).resolve()

    @contextmanager
    def _conexion(self, escritura=False):
        db = None
        try:
            if escritura:
                self.ruta.parent.mkdir(parents=True, exist_ok=True)
                db = sqlite3.connect(self.ruta, timeout=10)
                db.execute('PRAGMA foreign_keys=ON')
                db.execute('BEGIN IMMEDIATE')
                # Versión propia: no cambia user_version ni tablas ajenas.
                db.execute('CREATE TABLE IF NOT EXISTS consola_migraciones (version INTEGER PRIMARY KEY)')
                versiones = {r[0] for r in db.execute('SELECT version FROM consola_migraciones')}
                if versiones - {1}:
                    raise ErrorPersistencia('La base de la Consola pertenece a una versión más reciente')
                if 1 not in versiones:
                    db.execute('CREATE TABLE consola_clientes (id TEXT PRIMARY KEY, nombre TEXT NOT NULL, telefono TEXT, creado_en TEXT NOT NULL, actualizado_en TEXT NOT NULL)')
                    db.execute('CREATE TABLE consola_oportunidades (id TEXT PRIMARY KEY, cliente_id TEXT NOT NULL REFERENCES consola_clientes(id), necesidades TEXT NOT NULL, estado TEXT NOT NULL CHECK (estado IN (\'abierta\',\'cerrada\')), creado_en TEXT NOT NULL, actualizado_en TEXT NOT NULL)')
                    db.execute('CREATE INDEX consola_oportunidades_cliente ON consola_oportunidades(cliente_id)')
                    db.execute('INSERT INTO consola_migraciones VALUES (1)')
            else:
                if not self.ruta.exists():
                    yield None
                    return
                db = sqlite3.connect(self.ruta.as_uri() + '?mode=ro', uri=True, timeout=10)
                db.execute('PRAGMA query_only=ON')
                db.execute('BEGIN')
                if not db.execute("SELECT 1 FROM sqlite_master WHERE name='consola_migraciones'").fetchone():
                    yield None
                    return
                if {r[0] for r in db.execute('SELECT version FROM consola_migraciones')} != {1}:
                    raise ErrorPersistencia('Versión de almacenamiento de la Consola incompatible')
            db.row_factory = sqlite3.Row
            yield db
            if escritura:
                db.commit()
        except (sqlite3.Error, OSError, ValidationError) as exc:
            raise ErrorPersistencia('No se pudo acceder al almacenamiento de clientes y oportunidades') from exc
        finally:
            if db is not None:
                db.close()  # Revierte cualquier transacción incompleta.

    @staticmethod
    def _cliente(fila):
        return Cliente.model_validate(dict(fila))

    @staticmethod
    def _oportunidad(fila):
        from .modelos import Necesidades
        datos = dict(fila)
        datos['necesidades'] = Necesidades.model_validate_json(datos['necesidades'])
        return Oportunidad.model_validate(datos)

    def _listar(self, tabla, convertir):
        with self._conexion() as db:
            return [convertir(r) for r in db.execute(f'SELECT * FROM {tabla} ORDER BY creado_en DESC, id')] if db else []

    def clientes(self):
        return self._listar('consola_clientes', self._cliente)

    def oportunidades(self):
        return self._listar('consola_oportunidades', self._oportunidad)

    def _obtener(self, tabla, identificador, convertir):
        with self._conexion() as db:
            fila = db.execute(f'SELECT * FROM {tabla} WHERE id=?', (identificador,)).fetchone() if db else None
            if fila is None:
                raise NoEncontrado('Cliente u oportunidad no encontrado')
            return convertir(fila)

    def cliente(self, identificador):
        return self._obtener('consola_clientes', identificador, self._cliente)

    def oportunidad(self, identificador):
        return self._obtener('consola_oportunidades', identificador, self._oportunidad)

    def _guardar(self, db, tabla, datos, identificador):
        ahora = datetime.now(timezone.utc).isoformat()
        if identificador:
            fila = db.execute(f'SELECT * FROM {tabla} WHERE id=?', (identificador,)).fetchone()
            if fila is None:
                raise NoEncontrado('Cliente u oportunidad no encontrado')
            db.execute(f'UPDATE {tabla} SET ' + ','.join(f'{k}=?' for k in datos) + ', actualizado_en=? WHERE id=?',
                       (*datos.values(), ahora, identificador))
        else:
            identificador = str(uuid4())
            datos = dict(datos, id=identificador, creado_en=ahora, actualizado_en=ahora)
            db.execute(f'INSERT INTO {tabla} (' + ','.join(datos) + ') VALUES (' + ','.join('?' for _ in datos) + ')', tuple(datos.values()))
        return db.execute(f'SELECT * FROM {tabla} WHERE id=?', (identificador,)).fetchone()

    def guardar_cliente(self, datos, identificador=None):
        with self._conexion(True) as db:
            return self._cliente(self._guardar(db, 'consola_clientes', datos.model_dump(), identificador))

    def _guardar_oportunidad(self, db, datos, identificador):
        if not db.execute('SELECT 1 FROM consola_clientes WHERE id=?', (datos.cliente_id,)).fetchone():
            raise NoEncontrado('Cliente no encontrado')
        valores = {'cliente_id': datos.cliente_id, 'necesidades': datos.necesidades.model_dump_json(), 'estado': datos.estado}
        return self._oportunidad(self._guardar(db, 'consola_oportunidades', valores, identificador))

    def guardar_oportunidad(self, datos, identificador=None):
        with self._conexion(True) as db:
            return self._guardar_oportunidad(db, datos, identificador)

    def capturar(self, cliente, necesidades, estado, cliente_id=None, oportunidad_id=None):
        # Un formulario guarda ambos conceptos de manera atómica.
        with self._conexion(True) as db:
            c = self._cliente(self._guardar(db, 'consola_clientes', cliente.model_dump(), cliente_id))
            return self._guardar_oportunidad(db, OportunidadDatos(
                cliente_id=c.id, necesidades=necesidades, estado=estado), oportunidad_id)
