"""Identidad v1 de anuncios. No identifica ni fusiona inmuebles físicos."""

import json
import re
from uuid import UUID, uuid5


# Parte del contrato persistente: no cambiar namespace ni codificación al migrar.
NAMESPACE_CATALOGO = UUID('92758523-b53a-5f81-91ef-535e498e70f8')


def normalizar_fuente(fuente: str) -> str:
    """Clave técnica ASCII: minúsculas, números, guion o guion bajo."""
    if not isinstance(fuente, str):
        raise TypeError('fuente debe ser texto')
    fuente = fuente.strip().lower()
    if not re.fullmatch(r'[a-z0-9][a-z0-9_-]*', fuente):
        raise ValueError('fuente debe ser una clave técnica no vacía')
    return fuente


def normalizar_id_original(id_original: str) -> str:
    """Preserva mayúsculas, ceros iniciales y caracteres del identificador."""
    if not isinstance(id_original, str):
        raise TypeError('id_original debe ser texto')
    id_original = id_original.strip()
    if not id_original:
        raise ValueError('id_original no puede estar vacío')
    return id_original


def identificar_inmueble(fuente: str, id_original: str) -> str:
    """UUID5 estable de la pareja fuente/ID, sin depender de URL o atributos."""
    nombre = json.dumps(
        [normalizar_fuente(fuente), normalizar_id_original(id_original)],
        ensure_ascii=False, separators=(',', ':'),
    )
    return str(uuid5(NAMESPACE_CATALOGO, nombre))
