"""Normalización pura de los campos observados. Ningún HTML de cuenta se persiste."""
import re
import base64
import json
from urllib.parse import urlsplit, parse_qs, urlencode, urlunsplit

from metro.extraction import ExtractionError
from metro.prices import price


def enlace_anuncio(valor, codigo):
    if not isinstance(valor, str):
        return None
    try:
        p = urlsplit(valor)
        if (p.scheme not in ('http', 'https') or not p.hostname or p.username or p.password
                or not p.path.rstrip('/').endswith('/' + codigo)):
            return None
        return urlunsplit((p.scheme, p.netloc, p.path, '', ''))
    except ValueError:
        return None


def whatsapp_limpio(url):
    # El mensaje de Wasi incluye la identidad de la cuenta conectada. Conservar
    # solo el destino publicado; no copiar el mensaje ni datos de Mónica.
    if not isinstance(url, str):
        return None
    try:
        p = urlsplit(url)
    except ValueError:
        return None
    if p.scheme == 'https' and p.hostname == 'wa.me' and re.fullmatch(r'/\d+', p.path):
        return 'https://wa.me' + p.path
    if p.scheme == 'https' and p.hostname == 'api.whatsapp.com' and p.path == '/send':
        phone = parse_qs(p.query).get('phone', [''])[0]
        if re.fullmatch(r'\d+', phone):
            return 'https://api.whatsapp.com/send?' + urlencode({'phone': phone})
    return None


def publicacion_whatsapp(url, codigo):
    if not whatsapp_limpio(url):
        return None
    texto = parse_qs(urlsplit(url).query).get('text', [''])[0]
    for enlace in re.findall(r'https?://[^\s<>]+', texto):
        if publicado := enlace_anuncio(enlace.rstrip('.,)'), codigo):
            return publicado
    return None


def operacion(texto):
    return {'Vender': 'venta', 'Alquiler': 'arriendo', 'Vender - Alquiler': 'venta y arriendo',
            'Vender - Permutar': 'venta', 'Alquiler - Permutar': 'arriendo',
            'Vender - Alquiler - Permutar': 'venta y arriendo'}.get(texto)


def numero(valor, *, entero=False, positivo=True):
    if valor is None or not str(valor).strip():
        return None
    text = re.sub(r'\s*(?:M2|m²)\s*$', '', str(valor)).strip()
    parsed = price(text, 'COP', 'venta')
    if text == '0' and not positivo:
        return 0
    if parsed['status'] != 'valid':
        raise ValueError('Número no interpretable')
    from decimal import Decimal
    n = Decimal(parsed['amount'])
    if entero and n != n.to_integral_value():
        raise ValueError('Entero no interpretable')
    return int(n) if entero else float(n)


def listado(fila):
    codigo = str(fila.get('id') or '').strip()
    if not re.fullmatch(r'\d+', codigo) or codigo != str(fila.get('codigo') or '').strip():
        raise ExtractionError(f'Código de fila y código Wasi no coinciden: fila={codigo}, texto={fila.get("codigo")}')
    lineas = [l.strip() for l in fila['info'].splitlines() if l.strip()]
    titulo = fila.get('title')
    negocio_tipo = next((l for l in lineas if ' - ' in l and not l.startswith('$')), '')
    negocios = ('Vender - Alquiler - Permutar', 'Vender - Alquiler', 'Vender - Permutar', 'Alquiler - Permutar', 'Alquiler', 'Vender')
    negocio = next((n for n in negocios if negocio_tipo.startswith(n + ' - ')), None)
    tipo = negocio_tipo[len(negocio) + 3:].strip() if negocio else None
    oper = operacion(negocio)
    precios = re.findall(r'\$\s*([\d.,]+)', fila['info'])
    try:
        importe = numero(precios[0]) if len(precios) == 1 else None
    except ValueError:
        importe = None
    raw = {'businessType': oper, 'mvalorventa': importe if oper != 'arriendo' else None,
           'mvalorarriendo': importe if oper == 'arriendo' else None, 'currency': 'COP',
           'wasi': {'title': titulo, 'company': fila.get('company'), 'company_id': fila.get('company_id'),
                    'property_type': tipo, 'public_url': enlace_anuncio(fila.get('public_url'), codigo)}}
    return {'id': codigo, 'url': 'wasi:' + codigo, 'raw': raw, 'group': 'results'}


def normalizar(codigo, datos, fila, contacto=None):
    if str(datos.get('labels', {}).get('Código', '')).strip() != codigo:
        raise ExtractionError('La ficha no corresponde al código solicitado')
    labels = datos['labels']
    normal = {'id': codigo, 'url': fila['raw']['wasi'].get('public_url'), 'currency': 'COP'}
    fields, errores = {}, []
    def campo(nombre, valor, convertir=lambda v: v):
        estado = 'absent' if valor is None or str(valor).strip() == '' else 'present'
        resultado = None
        if estado == 'present':
            try:
                resultado = convertir(valor)
            except (ValueError, TypeError):
                estado = 'error'
                errores.append({'field': nombre, 'error': 'Valor no interpretable'})
        normal[nombre] = resultado
        fields[nombre] = {'status': estado, 'raw': valor, 'source': 'wasi.detail.labels'}
    campo('title', datos.get('title'))
    campo('description', datos.get('description'))
    campo('operation', operacion(labels.get('Tipo de negocio')))
    campo('property_type', labels.get('Tipo de inmueble'))
    ubicacion = [v.strip() for v in labels.get('Ubicación', '').split(',')]
    campo('city', ubicacion[0] if ubicacion and ubicacion[0] else None)
    campo('zone', labels.get('Localidad'))
    campo('neighborhood', labels.get('Zona / barrio'))
    for nombre, etiqueta in (('built_area', 'Área Construida'), ('private_area', 'Área Privada'),
                              ('rooms', 'Alcobas'), ('bathrooms', 'Baños'), ('garages', 'Garaje'), ('stratum', 'Estrato'),
                              ('administration', 'Valor Administración')):
        valor = labels.get(etiqueta)
        if nombre == 'administration' and valor:
            valor = valor.replace('$', '').replace('COP', '').strip()
        campo(nombre, valor, lambda v, n=nombre: numero(v, entero=n in ('rooms', 'bathrooms', 'garages', 'stratum'), positivo=n not in ('rooms', 'bathrooms', 'garages')))
    # Área terreno no equivale al área publicada sin especificación.
    normal['area'] = None
    fields['area'] = {'status': 'absent', 'raw': None, 'source': 'wasi.detail'}
    campo('floor', labels.get('Piso'))
    campo('address', labels.get('Dirección'))
    precios = datos.get('prices', {})
    extra = {}
    precios_invalidos = set()
    for oper, etiqueta, clave in (('venta', 'Venta', 'salePrice'), ('arriendo', 'Alquiler', 'rentPrice')):
        valor = precios.get(etiqueta)
        try:
            extra[clave] = numero(valor.replace('$', '').replace('COP', '').strip()) if valor else None
        except ValueError:
            extra[clave] = None
            precios_invalidos.add(clave)
            errores.append({'field': 'price', 'error': 'Precio de ficha no interpretable'})
    clave_precio = 'rentPrice' if normal['operation'] == 'arriendo' else 'salePrice'
    campo('price', extra.get(clave_precio))
    if clave_precio in precios_invalidos:
        fields['price'] = {'status': 'error', 'raw': precios.get('Alquiler' if clave_precio == 'rentPrice' else 'Venta'),
                           'source': 'wasi.detail.price'}
    if normal['price'] is None:
        errores.append({'field': 'price', 'error': 'Precio de ficha desconocido; requiere revisión conservadora'})
    company = fila['raw']['wasi'].get('company')
    campo('advertiser', company)
    contacto = contacto or {}
    if not normal['url']:
        normal['url'] = enlace_anuncio(contacto.get('public_url'), codigo)
    fields['url'] = {'status': 'present' if normal['url'] else 'absent', 'raw': normal['url'],
                     'source': 'wasi.listing.original_link' if fila['raw']['wasi'].get('public_url') else 'wasi.company_panel.published_property_link'}
    for nombre in ('phone', 'local_phone', 'whatsapp', 'advertiser_address'):
        campo(nombre, contacto.get(nombre))
        fields[nombre]['source'] = 'wasi.company_panel.property:' + codigo
    for nombre in ('latitude', 'longitude', 'map_url', 'portal_map_url', 'update_date'):
        campo(nombre, None)
    if not normal['title'] or not normal['operation']:
        errores.append({'field': 'core', 'error': 'Título u operación no disponibles'})
    fotos = {}
    for url in datos.get('photos', []):
        if not url.startswith(('https://', 'http://')):
            continue
        clave, ancho = url, 0
        if url.startswith('https://image.wasi.co/'):
            try:
                raw = json.loads(base64.b64decode(urlsplit(url).path.lstrip('/') + '===', validate=False))
                clave = (raw.get('bucket'), raw['key'])
                ancho = int(raw.get('edits', {}).get('resize', {}).get('width', 0))
            except (ValueError, KeyError, TypeError):
                pass
        if clave not in fotos or fotos[clave][0] < ancho:
            fotos[clave] = (ancho, url)
    fields['photos'] = {'status': 'present' if fotos else 'absent', 'raw': len(fotos), 'source': 'wasi.detail.gallery'}
    caracteristicas = list(datos.get('features', []))
    if labels.get('Año construcción'):
        caracteristicas.append('Año construcción: ' + labels['Año construcción'])
    return {'normalized': normal, 'fields': fields, 'features': [{'title': 'Características', 'items': caracteristicas}],
            'photos': [v[1] for v in fotos.values()], 'media': {}, 'extra': extra,
            'sources': {'wasi_listing': fila['raw']['wasi'], 'wasi_contacts': {'property_id': codigo, 'company': company}},
            'visible_text': '', 'errors': errores, 'quality': 'partial' if errores else 'success'}
