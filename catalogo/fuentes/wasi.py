"""Búsquedas Wasi versionadas por contenido; IDs del portal sin equivalencias."""
import hashlib
import json
from decimal import Decimal, InvalidOperation
from pathlib import Path

RED = 'https://wasi.co/usuario/inmuebles/red'
GEO = ('id_pais', 'id_dpto', 'id_ciudad', 'id_localidad', 'id_zona')
SELECTS = GEO + ('property_type_id', 'business_type_id', 'garage', 'beedroms', 'bathrooms', 'typeAccount')
NUMERIC_INPUTS = ('building_date', 'area_from', 'area_to', 'price_from', 'price_to')
TEXT_INPUTS = ('title',)
INPUTS = NUMERIC_INPUTS + TEXT_INPUTS
LABELS = dict(zip(SELECTS + INPUTS, (
    'País', 'Departamento', 'Ciudad', 'Localidad', 'Zona / barrio', 'Tipo de inmueble',
    'Operación', 'Parqueaderos mínimos', 'Alcobas mínimas', 'Baños mínimos', 'Quién ofrece',
    'Construido desde el año', 'Área mínima', 'Área máxima', 'Precio mínimo COP', 'Precio máximo COP', 'Título contiene')))


def opciones_iniciales():
    return json.loads(Path(__file__).with_name('wasi_opciones.json').read_text(encoding='utf-8'))


def clave_opciones(campo, valores):
    padres = GEO[:GEO.index(campo)] if campo in GEO else ()
    return campo + ':' + '/'.join(str(valores.get(p, '')) for p in padres)


def opciones(campo, valores, registros):
    return registros.get(clave_opciones(campo, valores), [])


def configurar(valores, registros):
    filtros, etiquetas = {}, {}
    for campo in SELECTS:
        valor = str(valores.get(campo) or '').strip()
        if not valor:
            continue
        elegida = next((o for o in opciones(campo, filtros, registros) if o['value'] == valor), None)
        if elegida is None:
            raise ValueError(f'{LABELS[campo]}: opción no disponible para los filtros anteriores. Actualiza opciones de Wasi.')
        filtros[campo], etiquetas[campo] = valor, elegida['label']
    if not filtros.get('id_ciudad') or not (filtros.get('id_localidad') or filtros.get('id_zona')):
        raise ValueError('Wasi requiere ciudad y al menos una localidad o zona / barrio.')
    for campo in NUMERIC_INPUTS:
        valor = str(valores.get(campo) or '').strip()
        if not valor:
            continue
        try:
            numero = Decimal(valor)
            if not numero.is_finite() or numero < 0 or numero != numero.to_integral_value():
                raise ValueError()
        except (ValueError, InvalidOperation):
            raise ValueError(f'{LABELS[campo]} debe ser un entero positivo o cero.') from None
        filtros[campo] = str(int(numero))
    for campo in TEXT_INPUTS:
        valor = str(valores.get(campo) or '').strip()
        if valor:
            if len(valor) > 256 or any(ord(c) < 32 for c in valor):
                raise ValueError(f'{LABELS[campo]} debe tener como máximo 256 caracteres, sin saltos de línea.')
            filtros[campo] = valor
    for minimo, maximo in (('area_from', 'area_to'), ('price_from', 'price_to')):
        if minimo in filtros and maximo in filtros and int(filtros[minimo]) > int(filtros[maximo]):
            raise ValueError(f'{LABELS[maximo]} debe ser mayor o igual al mínimo.')
    return {'version': 1, 'filtros': filtros, 'etiquetas': etiquetas}


def identidad(config):
    canon = json.dumps(config['filtros'], sort_keys=True, separators=(',', ':'), ensure_ascii=True)
    return 'wasi:' + hashlib.sha256(canon.encode()).hexdigest()
