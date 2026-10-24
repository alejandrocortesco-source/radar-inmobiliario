"""Contrato mínimo de lectura, sin tipos ni operaciones propios de SQLite."""

from typing import Protocol

from ..modelos import Inmueble


class RepositorioCatalogo(Protocol):
    def listar(self) -> tuple[Inmueble, ...]:
        """Catálogo completo, incluidos anuncios sin ficha y retirados."""
        ...

    def obtener(self, id_interno: str) -> Inmueble | None:
        """Ficha por identidad interna; None si no existe."""
        ...
