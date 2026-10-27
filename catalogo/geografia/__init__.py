"""Normalización determinística, sin red ni inferencias a partir de una búsqueda.

La confirmación expresa consistencia de los campos publicados con el nomenclátor;
no certifica la ubicación física del inmueble. Los originales nunca se reescriben.
"""
from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import re
from unicodedata import normalize, combining


def normalizar(texto):
    return ' '.join(''.join(c for c in normalize('NFKD', texto or '') if not combining(c)).casefold().split())


def normalizar_ciudad(texto):
    valor = ' '.join(re.sub(r'[^\w\s]', ' ', normalizar(texto)).split())
    return 'bogota' if valor.replace(' ', '') in {'bogota', 'bogotadc'} else valor


def clave(texto):
    return ' '.join(re.sub(r'[^\w\s]', ' ', normalizar(texto)).split())


_DATOS = Path(__file__).with_name('barrios.json').read_bytes()
CATALOGO = json.loads(_DATOS)
# Cambiar REGLAS al modificar la interpretación, además del catálogo versionado.
REGLAS = 'geografia-1'
VERSION = sha256(_DATOS + REGLAS.encode()).hexdigest()
_INDICE = {(b['ciudad'], clave(b['nombre'])): b for b in CATALOGO['barrios']}
_MARCADOR = re.compile(r'(?<!\w)(?:EDIFICIO|EDIF\.?)(?!\w)\s*', re.I)
_VACIOS = {'', 'na', 'n a', 'no aplica', 'sin dato', 'otros', 'otro'}


@dataclass(frozen=True, slots=True)
class Geografia:
    ciudad_original: str | None
    barrio_original: str | None
    barrio_comun_original: str | None
    zona_original: str | None
    sector_original: str | None
    ciudad_clave: str
    barrio_id: str | None
    barrio: str | None
    zona: str | None
    edificio: str | None
    estado: str
    motivos: tuple[str, ...]
    evidencias: tuple[str, ...]
    version: str = VERSION


def resolver_barrio(ciudad, valor, *, sector=None):
    """Resolución exacta en ciudad. El edificio no participa en la identidad.

    BARRIO es un prefijo de campo. La localidad y el sector publicado pueden
    ser calificadores explícitos, nunca se busca un barrio dentro del texto.
    Devuelve (entrada, edificio, regla); desconocido no equivale a otro barrio.
    """
    texto = valor if isinstance(valor, str) else ''
    partes = _MARCADOR.split(texto, maxsplit=1)
    edificio = ' '.join(partes[1].split()) or None if len(partes) == 2 else None
    nombre = clave(partes[0])
    if nombre.startswith('barrio '):
        nombre = nombre[7:]
    ciudad = normalizar_ciudad(ciudad)
    directo = _INDICE.get((ciudad, nombre))
    if directo:
        return directo, edificio, 'nombre exacto' + (' + marcador de edificio' if edificio else '')
    candidatos = []
    for b in CATALOGO['barrios']:
        if b['ciudad'] != ciudad:
            continue
        base = clave(b['nombre'])
        calificadores = {clave(b['localidad'])}
        if sector and clave(sector) not in _VACIOS:
            calificadores.add(clave(sector))
        if nombre in {base + ' ' + c for c in calificadores}:
            candidatos.append(b)
    if len(candidatos) == 1:
        return candidatos[0], edificio, 'nombre exacto + calificador publicado'
    return None, None, 'nombre fuera del catálogo controlado'


def normalizar_geografia(*, ciudad=None, barrio=None, barrio_comun=None, zona=None, sector=None):
    originales = (ciudad, barrio, barrio_comun, zona, sector)
    if any(v is not None and not isinstance(v, str) for v in originales):
        raise TypeError('Los campos geográficos deben ser texto o None')
    zonas = {clave(v): v for v in ('Norte', 'Sur', 'Centro', 'Oriental', 'Occidental')}
    zona_normal = zonas.get(clave(zona))
    encontrados, edificios, motivos, evidencias = [], [], [], []
    for campo, valor in (('neighborhood', barrio), ('common_neighborhood', barrio_comun)):
        if clave(valor) in _VACIOS:
            continue
        entrada, edificio, regla = resolver_barrio(ciudad, valor, sector=sector)
        if entrada is None:
            motivos.append(f'{campo}: nombre no reconocido en el catálogo controlado')
        else:
            encontrados.append(entrada)
            evidencias.append(f'{campo}: {entrada["id"]}; {regla}')
            if edificio:
                edificios.append(edificio)
    ids = {b['id'] for b in encontrados}
    if len(ids) > 1:
        motivos.append('Los dos campos publicados identifican barrios distintos')
    if not encontrados:
        motivos.append('No hay barrio identificado con confianza')
    if zona_normal and any(clave(b['zona']) != clave(zona_normal) for b in encontrados):
        motivos.append('La zona publicada contradice el barrio identificado')
    if zona and clave(zona) not in _VACIOS and zona_normal is None:
        motivos.append('Zona publicada no reconocida')
    if len({clave(e) for e in edificios}) > 1:
        motivos.append('Los campos identifican edificios distintos')
    confirmado = bool(encontrados) and not motivos
    return Geografia(*originales, normalizar_ciudad(ciudad),
        encontrados[0]['id'] if confirmado else None,
        encontrados[0]['nombre'] if confirmado else None, zona_normal,
        edificios[0] if edificios and len({clave(e) for e in edificios}) == 1 else None,
        'confirmada' if confirmado else 'pendiente', tuple(motivos), tuple(evidencias))
