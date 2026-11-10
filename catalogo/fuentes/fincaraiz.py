"""Búsquedas Fincaraíz: URLs preservadas y criterios resueltos por evidencia."""
import json
import re
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

PORTAL = 'https://www.fincaraiz.com.co'
REFERENCIA = PORTAL + '/venta/casas-y-apartamentos/la-carolina/zona-norte/bogota'


def validar_url(url):
    if not isinstance(url, str) or len(url) > 4096 or any(c.isspace() or ord(c) < 32 for c in url):
        raise ValueError('Ingresa una URL pública de resultados de Fincaraíz')
    p = urlsplit(url)
    if (p.scheme not in ('https', 'http') or p.hostname not in ('www.fincaraiz.com.co', 'fincaraiz.com.co')
            or p.username or p.password or p.port not in (None, 80, 443)
            or not re.match(r'^/(venta|arriendo)/[^/]+(?:/[^/]+)*/?$', p.path)
            or re.search(r'/pagina\d+/?$', p.path)):
        raise ValueError('Usa la primera página de una búsqueda de venta o arriendo de Fincaraíz; no una ficha')
    return urlunsplit(('https', 'www.fincaraiz.com.co', p.path.rstrip('/'), p.query, ''))


def identidad(url):
    p = urlsplit(validar_url(url))
    # Todos los parámetros se conservan: no adivinar cuáles filtran el portal.
    return urlunsplit((p.scheme, p.netloc, p.path, urlencode(sorted(parse_qsl(p.query, keep_blank_values=True))), ''))


def criterios(filters):
    op = filters.get('operation_type_id') or {}
    locs = (filters.get('locations') or {}).get('value') or []
    types = filters.get('property_type_id') or []
    if not isinstance(types, list) or len(locs) != 1:
        raise ValueError('Ubicación múltiple o ambigua: utiliza la URL filtrada')
    loc = locs[0]
    city = loc.get('city') or []
    if len(city) != 1 or not loc.get('id') or not loc.get('type') or not city[0].get('id'):
        raise ValueError('La búsqueda debe precisar una ciudad y un barrio o zona verificables')
    return {'operacion': str(op.get('value', '')), 'operacion_nombre': op.get('text'),
            'ciudad': city[0]['id'], 'ciudad_nombre': city[0]['name'],
            'ubicacion': loc['id'], 'ubicacion_nombre': loc['name'] + ' · ' + loc['type'] + ' · ' + city[0]['name'],
            'tipos': sorted(str(t['value']) for t in types),
            'tipos_nombres': {str(t['value']): t['text'] for t in types}}


def opciones_iniciales():
    return json.loads(Path(__file__).with_name('fincaraiz_opciones.json').read_text(encoding='utf-8'))


def resolver(valores, opciones):
    tipos = sorted(set(valores.get('fr_tipos', '').split(',')) - {''})
    for c in opciones:
        cr = c['criterios']
        if not cr or set(c['filtros']) - {'operation_type_id', 'property_type_id', 'locations', 'country_id', 'currencyID', 'm2Currency', 'order'}:
            continue
        if all(str(valores.get('fr_' + k, '')) == cr[k] for k in ('operacion', 'ciudad', 'ubicacion')) and tipos == cr['tipos']:
            return c['url_efectiva']
    raise ValueError('Esta combinación aún no tiene una URL equivalente comprobada. Usa una URL filtrada; al verificarla se incorporan sus opciones sin inventar slugs o IDs.')
