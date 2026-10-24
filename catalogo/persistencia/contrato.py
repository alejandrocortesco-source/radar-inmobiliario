"""Contratos de lectura común y de compatibilidad con la revisión existente."""

from dataclasses import dataclass
from typing import Protocol

from ..modelos import Inmueble


class ErrorLecturaCatalogo(RuntimeError):
    """Un almacenamiento no puede entregar el catálogo solicitado."""


class RepositorioCatalogo(Protocol):
    def listar(self) -> tuple[Inmueble, ...]:
        ...

    def obtener(self, id_interno: str) -> Inmueble | None:
        ...


@dataclass(frozen=True)
class RegistroCatalogo:
    """Modelo común y valores originales necesarios para conservar la API."""
    inmueble: Inmueble
    resumen: dict
    documento: dict | None
    presencias: tuple[dict, ...]


@dataclass(frozen=True)
class RevisionCatalogo:
    registro: RegistroCatalogo
    documento: dict | None
    trabajos: tuple[dict, ...]
    apariciones: tuple[dict, ...]
    historial: tuple[dict, ...]


class RepositorioRevision(Protocol):
    """Evidencia técnica opcional, separada del contrato del catálogo común."""
    def listar_registros(self) -> tuple[RegistroCatalogo, ...]:
        ...

    def obtener_revision(self, identificador: str) -> RevisionCatalogo | None:
        ...
