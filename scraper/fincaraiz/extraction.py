"""Datos públicos Next.js; sin endpoints ni teléfonos reconstruidos."""
import math
import re
from urllib.parse import urljoin, urlsplit
from catalogo.fuentes.fincaraiz import PORTAL
from metro.extraction import ExtractionError, sanitize


def numero(v):
    if isinstance(v, bool) or v is None:
        return None
    try:
        n = float(v)
        return n if math.isfinite(n) and n >= 0 else None
    except (TypeError, ValueError):
        return None


def enlace(p):
    codigo = str(p.get('id', ''))
    url = urljoin(PORTAL, p.get('link') or '')
    if not codigo.isdigit() or urlsplit(url).hostname != 'www.fincaraiz.com.co' or urlsplit(url).path.rstrip('/').split('/')[-1] != codigo:
        raise ExtractionError('Identidad o enlace del anuncio Fincaraíz inconsistente')
    op = (p.get('operation_type') or {}).get('name', '').lower()
    precio = (p.get('price') or {}).get('amount')
    return {'id': codigo, 'url': url, 'group': 'results', 'raw': {'businessType': op,
            'mvalorventa' if op == 'venta' else 'mvalorarriendo': precio,
            'currency': 'COP', 'fincaraiz': sanitize(p)}}


def normalizar(p, url):
    item = enlace(p)
    if item['url'] != url:
        raise ExtractionError('La ficha no corresponde al anuncio solicitado')
    loc = p.get('locations') or {}
    principal = loc.get('location_main') or {}
    ciudades = loc.get('city') or []
    owner = p.get('owner') or {}
    ficha = {t['field']: t.get('value') for t in p.get('technicalSheet', []) if isinstance(t, dict) and 'field' in t}
    n = {'id': item['id'], 'url': url, 'title': p.get('title'), 'description': p.get('description'),
         'operation': item['raw']['businessType'], 'property_type': (p.get('property_type') or {}).get('name'),
         'currency': 'COP', 'price': numero((p.get('price') or {}).get('amount')),
         'administration': numero((p.get('commonExpenses') or {}).get('amount')),
         'city': ciudades[0].get('name') if len(ciudades) == 1 else None,
         'neighborhood': principal.get('name') if principal.get('location_type') == 'neighbourhood' else None,
         'zone': principal.get('name') if principal.get('location_type') == 'zone' else None,
         'address': p.get('address') if p.get('showAddress') else None,
         'advertiser': owner.get('name'), 'advertiser_address': owner.get('address'),
         'advertiser_url': urljoin(PORTAL, owner['inmoPropsLink']) if owner.get('inmoPropsLink') else None,
         'phone': None, 'local_phone': None, 'whatsapp': None,
         'age': ficha.get('constructionYear'), 'publication_date': p.get('created_at'), 'update_date': p.get('updated_at')}
    # Solo campos completos publicados; masked_phone nunca se transforma en contacto.
    for key, target in (('phone', 'phone'), ('whatsapp_phone', 'whatsapp')):
        v = owner.get(key)
        if isinstance(v, str) and re.fullmatch(r'\+?\d[\d ().-]{6,19}', v) and 7 <= len(re.sub(r'\D', '', v)) <= 15:
            n[target] = v
    mapping = {'rooms': 'bedrooms', 'bathrooms': 'bathrooms', 'garages': 'garage', 'area': 'm2',
               'built_area': 'm2Built', 'private_area': 'm2apto', 'floor': 'floor', 'stratum': 'stratum',
               'latitude': 'latitude', 'longitude': 'longitude'}
    for target, origin in mapping.items():
        n[target] = p.get(origin) if target in ('latitude', 'longitude') else numero(p.get(origin))
    if n['price'] is not None and n['price'] <= 0:
        n['price'] = None
    fields = {k: {'status': 'present' if v is not None else 'absent', 'raw': v, 'source': 'fincaraiz.property.' + mapping.get(k, k)} for k, v in n.items()}
    errors = []
    for target, raw in (('price', (p.get('price') or {}).get('amount')), ('administration', (p.get('commonExpenses') or {}).get('amount'))):
        fields[target].update(raw=raw, source='fincaraiz.property.' + ('price.amount' if target == 'price' else 'commonExpenses.amount'))
        if raw is not None and n[target] is None:
            fields[target]['status'] = 'error'
            errors.append({'field': target, 'error': 'Importe inválido'})
    for target, origin in mapping.items():
        if p.get(origin) is not None and n[target] is None:
            fields[target].update(status='error', raw=p[origin]); errors.append({'field': target, 'error': 'Valor numérico inválido'})
    if not n['title'] or not n['description'] or n['operation'] not in ('venta', 'arriendo'):
        errors.append({'field': 'core', 'error': 'Ficha incompleta'})
    photos = list(dict.fromkeys(i['image'] for i in p.get('images', []) if isinstance(i, dict) and str(i.get('image', '')).startswith(('http://', 'https://'))))
    areas = {k: n[k] for k in ('area', 'built_area', 'private_area')}
    return {'normalized': n, 'fields': fields, 'quality': 'partial' if errors else 'success', 'errors': errors,
            'photos': photos, 'media': {}, 'visible_text': '',
            'features': [{'title': 'Ficha técnica', 'items': [str(t.get('text')) + ': ' + str(t['value']) for t in p.get('technicalSheet', []) if t.get('value')]},
                         {'title': 'Características', 'items': [f['name'] for f in p.get('facilities', []) if f.get('name')]}],
            'extra': {'location_main': principal, 'associated_locations': loc, 'areas': areas,
                      'area_discrepancy': len({v for v in areas.values() if v is not None}) > 1,
                      'contact_limit': 'Solo contactos publicados completos; no se envían formularios',
                      'antiquity_code': p.get('antiquity'), 'antiquity_label': ficha.get('constructionYear')},
            'sources': {'fincaraiz_property': sanitize(p)}}
