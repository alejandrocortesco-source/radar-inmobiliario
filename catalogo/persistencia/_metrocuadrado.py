"""Traducción conservadora del documento ya normalizado por Metrocuadrado.

No importa ni ejecuta el scraper. Los datos ambiguos permanecen desconocidos.
"""

import unicodedata
from ..geografia import normalizar_geografia
from datetime import datetime
from decimal import Decimal, InvalidOperation

from ..modelos import (
    Calidad, Disponibilidad, Inmueble, Oferta, Operacion, Origen,
    PresenciaBusqueda, TipoInmueble,
)


def _texto(valor):
    return valor.strip() if isinstance(valor, str) and valor.strip() else None


def _clave(valor):
    return ''.join(c for c in unicodedata.normalize('NFD', _texto(valor) or '')
                   if not unicodedata.combining(c)).casefold()


def _numero(valor, *, cero=False):
    if isinstance(valor, bool) or valor is None:
        return None
    try:
        resultado = Decimal(str(valor))
    except (InvalidOperation, ValueError):
        return None
    return resultado if resultado.is_finite() and (resultado >= 0 if cero else resultado > 0) else None


def _entero(valor):
    numero = _numero(valor, cero=True)
    return int(numero) if numero is not None and numero == numero.to_integral_value() else None


def _coordenada(valor, limite):
    if isinstance(valor, bool) or valor is None:
        return None
    try:
        numero = Decimal(str(valor))
    except (InvalidOperation, ValueError):
        return None
    return numero if numero.is_finite() and -limite <= numero <= limite else None


def _fecha(valor):
    if not isinstance(valor, str):
        return None
    try:
        resultado = datetime.fromisoformat(valor)
    except ValueError:
        return None
    return resultado if resultado.tzinfo is not None and resultado.utcoffset() is not None else None


def _moneda(valor):
    if isinstance(valor, dict):
        valor = valor.get('code') or valor.get('codigo') or valor.get('nombre')
    valor = (_texto(valor) or '').upper()
    valor = {'COL$': 'COP', 'US$': 'USD', '€': 'EUR',
             'PESOS COLOMBIANOS': 'COP'}.get(valor, valor)
    return valor if len(valor) == 3 and valor.isascii() and valor.isalpha() else None


def _objeto(valor, nombre):
    if valor is None:
        return {}
    if not isinstance(valor, dict):
        raise ValueError(f'{nombre} debe ser un objeto JSON')
    return valor


def convertir(fila, documento, presencias, config, *, geografia=None):
    documento = _objeto(documento, 'documento')
    normal = _objeto(documento.get('normalized'), 'normalized')
    extra = _objeto(documento.get('extra'), 'extra')
    fuentes = _objeto(documento.get('sources'), 'sources')
    original = _objeto(fuentes.get('flight_property'), 'flight_property') or extra
    config = _objeto(config, 'configuración')
    tipo_original = _texto(normal.get('property_type')) or _texto(fila['property_type'])
    operacion_original = _texto(normal.get('operation')) or _texto(original.get('businessType'))
    tipo = {t.value: t for t in TipoInmueble}.get(_clave(tipo_original))
    if _clave(tipo_original) in ('apartaestudio', 'apartamento'):
        tipo = TipoInmueble.APARTAMENTO
    if tipo is None and tipo_original is not None:
        tipo = TipoInmueble.OTRO
    codigo_moneda = _moneda(normal.get('currency')) or _moneda(original.get('currency'))
    # Solo la configuración de una captura que coincide con el documento global.
    # Una ejecución posterior fallida no debe cambiar la moneda de la ficha fiable.
    if codigo_moneda is None and not normal.get('currency') and not original.get('currency'):
        codigo_moneda = _moneda(config.get('listing_currency'))
    operaciones = {
        'venta': (Operacion.VENTA,), 'arriendo': (Operacion.ARRIENDO,),
        'venta y arriendo': (Operacion.VENTA, Operacion.ARRIENDO),
    }.get(_clave(operacion_original), ())
    ofertas = []
    for operacion in operaciones:
        es_precio_normalizado = operacion == operaciones[0]
        valor = normal.get('price') if es_precio_normalizado else None
        if valor is None:
            valor = original.get('salePrice' if operacion == Operacion.VENTA else 'rentPrice')
        ofertas.append(Oferta(operacion=operacion, precio=_numero(valor), moneda=codigo_moneda))
    estados = {
        'active': Disponibilidad.ACTIVO,
        'possibly_removed': Disponibilidad.POSIBLEMENTE_RETIRADO,
        'removed': Disponibilidad.RETIRADO,
    }
    busquedas = tuple(PresenciaBusqueda(
        id_busqueda=p['search_url'], url=p['search_url'],
        disponibilidad=estados.get(p['state'], Disponibilidad.DESCONOCIDA),
        ultima_verificacion=_fecha(p['last_verified_at']),
    ) for p in presencias)
    primeras = [f for p in presencias if (f := _fecha(p['first_seen'])) is not None]
    verificaciones = [b.ultima_verificacion for b in busquedas if b.ultima_verificacion is not None]
    caracteristicas = []
    grupos = documento.get('features')
    if grupos is None:
        grupos = []
    if not isinstance(grupos, list):
        raise ValueError('features debe ser una lista')
    for grupo in grupos:
        if not isinstance(grupo, dict) or not isinstance(grupo.get('items', []), list):
            raise ValueError('grupo de características inválido')
        titulo = _texto(grupo.get('title'))
        for item in grupo.get('items', []):
            if texto := _texto(item):
                caracteristicas.append(f'{titulo}: {texto}' if titulo else texto)
    fotos = documento.get('photos')
    if fotos is None:
        fotos = []
    if not isinstance(fotos, list):
        raise ValueError('photos debe ser una lista')
    fotos = tuple(dict.fromkeys(
        f for valor in fotos if (f := _texto(valor)) and f.startswith(('https://', 'http://'))
    ))
    areas = {}
    for campo in ('area', 'built_area', 'private_area'):
        # Regla del mercado local: presentar valores positivos en m², sin
        # reescribir los valores ni las unidades originales de la captura.
        areas[campo] = _numero(normal.get(campo))
    estrato = _entero(normal.get('stratum'))
    coordenadas = original.get('coordinates')
    coordenadas = coordenadas if isinstance(coordenadas, dict) else {}
    # Capturas anteriores conservan la precisión en la evidencia del enlace.
    campos = documento.get('fields')
    campo_mapa = campos.get('map_url') if isinstance(campos, dict) else None
    evidencia = campo_mapa.get('raw') if isinstance(campo_mapa, dict) else None
    evidencia = evidencia if isinstance(evidencia, dict) else {}
    aproximada = original.get('ubicacionaproximada', evidencia.get('ubicacionaproximada'))
    geografia = geografia or normalizar_geografia(
        ciudad=_texto(normal.get('city')) or _texto(fila['city']),
        barrio=normal.get('neighborhood'), barrio_comun=normal.get('common_neighborhood'),
        zona=normal.get('zone'), sector=normal.get('sector'))
    return Inmueble(
        origen=Origen(
            fuente='metrocuadrado', id_original=fila['id'], url=_texto(fila['url']),
            tipo_original=tipo_original, operacion_original=operacion_original,
            primera_observacion=min(primeras, default=None),
            ultima_verificacion=max(verificaciones, default=None),
            ultima_extraccion=_fecha(fila['updated']),
            actualizado_en_fuente=_fecha(normal.get('update_date')),
            busquedas=busquedas,
        ),
        titulo=_texto(normal.get('title')) or _texto(fila['title']),
        descripcion=_texto(normal.get('description')), tipo=tipo, ofertas=tuple(ofertas),
        ciudad=_texto(normal.get('city')) or _texto(fila['city']),
        zona=geografia.zona, barrio=geografia.barrio,
        geografia=geografia, edificio=geografia.edificio,
        direccion=_texto(normal.get('address')),
        latitud=_coordenada(normal.get('latitude', coordenadas.get('lat')), 90),
        longitud=_coordenada(normal.get('longitude', coordenadas.get('lon')), 180),
        ubicacion_aproximada={'S': True, 'N': False}.get(aproximada) if isinstance(aproximada, str) else None,
        portal_map_url=_texto(normal.get('portal_map_url')), map_url=_texto(normal.get('map_url')),
        area_publicada_m2=areas['area'], area_construida_m2=areas['built_area'],
        area_privada_m2=areas['private_area'], habitaciones=_entero(normal.get('rooms')),
        banos=_entero(normal.get('bathrooms')), parqueaderos=_entero(normal.get('garages')),
        estrato=estrato if estrato in range(1, 7) else None, fotos=fotos,
        caracteristicas=tuple(dict.fromkeys(caracteristicas)),
        calidad={'success': Calidad.COMPLETA, 'partial': Calidad.PARCIAL}.get(
            documento.get('quality'), Calidad.DESCONOCIDA),
        requiere_revision=bool(fila['needs_refresh']),
    )
