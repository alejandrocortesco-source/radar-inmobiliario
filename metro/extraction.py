"""Adaptador observado el 24/10/2026: React Flight + /rest-search/search.

No ejecuta JavaScript incrustado. Lee JSON y selecciona objetos de datos públicos.
"""
import hashlib
import json
import re
from decimal import Decimal, InvalidOperation
from urllib.parse import urljoin, urlsplit, urlunsplit, parse_qsl, urlencode

BASE = 'https://www.metrocuadrado.com'
SECRET = re.compile(r'token|cookie|session|secret|password|api.?key|authorization|recaptcha|nonce', re.I)


class ExtractionError(RuntimeError):
    pass


class Restricted(ExtractionError):
    pass


def sanitize(value):
    if isinstance(value, dict):
        return {k: sanitize(v) for k, v in value.items() if not SECRET.search(k)}
    if isinstance(value, list):
        return [sanitize(v) for v in value]
    if isinstance(value, str) and value.startswith(('http://', 'https://')):
        p = urlsplit(value)
        return urlunsplit((p.scheme, p.netloc, p.path, urlencode(
            [(k, v) for k, v in parse_qsl(p.query) if not SECRET.search(k)]), ''))
    return value


def walk(value):
    if isinstance(value, dict):
        yield value
        for v in value.values():
            yield from walk(v)
    elif isinstance(value, list):
        for v in value:
            yield from walk(v)


def flight_records(scripts):
    chunks = []
    decoder = json.JSONDecoder()
    for script in scripts:
        for chunk in script.split('self.__next_f.push(')[1:]:
            try:
                arr, _ = decoder.raw_decode(chunk)
            except ValueError:
                continue
            if len(arr) > 1 and arr[0] == 1 and isinstance(arr[1], str):
                chunks.append(arr[1])
    # Flight puede dividir un registro entre varios scripts.
    stream = ''.join(chunks).encode('utf-8')
    records = {}
    pos = 0
    while pos < len(stream):
        match = re.match(rb'\s*([0-9a-f]+):', stream[pos:])
        if not match:
            end = stream.find(b'\n', pos)
            if end < 0:
                break
            pos = end + 1
            continue
        key = match[1].decode()
        pos += match.end()
        text = re.match(rb'T([0-9a-f]+),', stream[pos:])
        if text:
            pos += text.end()
            size = int(text[1], 16)
            records[key] = stream[pos:pos+size].decode('utf-8', errors='replace')
            pos += size
            continue
        end = stream.find(b'\n', pos)
        if end < 0:
            end = len(stream)
        try:
            records[key] = json.loads(stream[pos:end])
        except ValueError:
            pass  # Registros de módulos I, hints HL y errores no son datos de inmueble.
        pos = end + 1

    def resolve(v, seen=frozenset()):
        if isinstance(v, str) and re.match(r'^\$[0-9a-f]+(?::|$)', v):
            ref, *path = v[1:].split(':')
            if ref in records and ref not in seen:
                target = records[ref]
                try:
                    for part in path:
                        target = target[int(part)] if isinstance(target, list) else target[part]
                    return resolve(target, seen | {ref})
                except (KeyError, IndexError, TypeError, ValueError):
                    return v
        if isinstance(v, dict):
            return {k: resolve(x, seen) for k, x in v.items()}
        if isinstance(v, list):
            return [resolve(x, seen) for x in v]
        return v
    return [resolve(v, frozenset({k})) for k, v in records.items()]


def listing_from_records(records):
    for obj in walk(records):
        if isinstance(obj.get('initialResults'), dict) and isinstance(obj['initialResults'].get('results'), list):
            return sanitize(obj['initialResults'])
    raise ExtractionError('No se encontró initialResults público; el adaptador requiere revisión.')


def canonical(url):
    p = urlsplit(urljoin(BASE, url))
    if p.hostname not in ('www.metrocuadrado.com', 'metrocuadrado.com') or not p.path.startswith('/inmueble/'):
        raise ExtractionError(f'Enlace fuera de fichas de Metrocuadrado: {p.path}')
    return urlunsplit(('https', 'www.metrocuadrado.com', p.path.rstrip('/'), '', ''))


def identity(url, portal_id=None):
    url = canonical(url)
    tail = urlsplit(url).path.rsplit('/', 1)[-1]
    if portal_id and str(portal_id) != tail:
        raise ExtractionError('Identificador del objeto no coincide con su URL')
    return str(portal_id or tail) if tail else 'url:'+hashlib.sha256(url.encode()).hexdigest()


def listing_links(batch):
    if not isinstance(batch.get('results'), list):
        raise ExtractionError('Respuesta de listado sin results')
    links = {}
    # recommended se excluye incluso si contiene los mismos enlaces.
    for group in ('results', 'highlights'):
        for obj in batch.get(group) or []:
            url = obj.get('link') or (obj.get('data') or {}).get('murldetalle')
            if not url:
                raise ExtractionError('Resultado sin enlace; no se declara completa la página')
            item = {'id': identity(url, obj.get('midinmueble')), 'url': canonical(url),
                    'group': group, 'raw': sanitize(obj)}
            links.setdefault(item['id'], item)
    return list(links.values())


def fingerprint(batch):
    ids = sorted(identity(x['link'], x.get('midinmueble')) for x in batch['results'])
    return hashlib.sha256(json.dumps(ids).encode()).hexdigest()


def number(raw):
    if raw is None or raw == '':
        return None
    if isinstance(raw, (int, float)):
        return raw
    s = str(raw).strip()
    # Valores del JSON son números sin separadores de miles. No adivina locales.
    if not re.fullmatch(r'-?\d+(?:\.\d+)?', s):
        raise ValueError(f'Número ambiguo o no válido: {raw}')
    try:
        return float(Decimal(s))
    except InvalidOperation as exc:
        raise ValueError(str(exc)) from exc


def detail_from_records(records, property_id):
    candidates = [x for x in walk(records) if x.get('propertyId') == property_id and 'businessType' in x]
    if not candidates:
        raise ExtractionError('Ficha sin objeto público propertyId coincidente')
    # Conserva el objeto completo, no la variante con referencias sin resolver.
    return sanitize(max(candidates, key=lambda x: sum(isinstance(v, (dict,list)) for v in x.values())))


def normalize_detail(raw, url, visible_text='', ld=None, dom_media=None):
    normalized = {'id': raw['propertyId'], 'url': canonical(url)}
    fields = {}
    errors = []

    def field(name, path, numeric=False):
        value = raw
        for key in path.split('.'):
            value = value.get(key) if isinstance(value, dict) else None
        state = 'absent' if value is None or value == '' else 'present'
        converted = value
        if state == 'present' and isinstance(value,str) and re.match(r'^\$[0-9a-f]',value):
            state, converted = 'error', None
            errors.append({'field':name, 'error':'Referencia Flight sin resolver'})
        if state == 'present' and numeric:
            try:
                converted = number(value)
            except ValueError as exc:
                state, converted = 'error', None
                errors.append({'field': name, 'error': str(exc)})
        normalized[name] = converted if state == 'present' else None
        fields[name] = {'status': state, 'raw': value, 'source': 'flight.'+path}

    mapping = {'title':'title', 'property_type':'propertyType.nombre', 'operation':'businessType',
               'administration':'detail.adminPrice', 'city':'city.nombre', 'zone':'zone.nombre',
               'sector':'sector.nombre', 'neighborhood':'neighborhood', 'common_neighborhood':'commonNeighborhood',
               'address':'address', 'latitude':'coordinates.lat', 'longitude':'coordinates.lon',
               'area':'area', 'built_area':'areac', 'private_area':'areaPrivada',
               'rooms':'rooms', 'bathrooms':'bathrooms', 'garages':'garages', 'stratum':'stratum',
               'age':'builtTime', 'description':'comment', 'advertiser':'companyName',
               'advertiser_address':'companyAddress', 'phone':'contactPhone', 'whatsapp':'whatsapp',
               'local_phone':'localPhone', 'publication_date':'publicationDate', 'update_date':'updateDate',
               'video':'video', 'virtual_tour':'virtualTour', 'currency':'currency'}
    numeric = {'administration','latitude','longitude','area','built_area','private_area','rooms','bathrooms','garages','stratum'}
    for name, path in mapping.items():
        field(name, path, name in numeric)
    price_key = {'venta':'salePrice','arriendo':'rentPrice'}.get(raw.get('businessType'))
    field('price', price_key or 'price', True)
    # Unidad y moneda sólo si el DOM las publica; nunca inferidas por país o barrio.
    if normalized['currency'] is None and re.search(r'\bCOP\b',visible_text):
        normalized['currency'] = 'COP'
        fields['currency'] = {'status':'present','raw':'COP','source':'DOM: texto COP'}
    for name, label in (('built_area','Área Construida'),('private_area','Área Privada')):
        match = re.search(re.escape(label)+r'\s*([\d.,]+)\s*(m²|m2)',visible_text,re.I)
        if match:
            normalized[name+'_unit'] = match[2]
            if normalized[name] is None:
                try:
                    normalized[name] = number(match[1].replace(',','.'))
                    fields[name] = {'status':'present','raw':match[0],'source':'DOM: '+label}
                except ValueError as exc:
                    errors.append({'field':name,'error':str(exc)})
    features = raw.get('featured') if isinstance(raw.get('featured'),list) else []
    floor = next((item for group in features for item in group.get('items',[])
                  if re.match(r'Número de piso\s',item,re.I)), None)
    normalized['floor'] = floor.removeprefix('Número de piso').strip() if floor else None
    fields['floor'] = {'status':'present' if floor else 'absent','raw':floor,'source':'flight.featured'}
    photos = []
    for item in raw.get('images') or []:
        if isinstance(item,dict):
            photos.extend(v for k,v in item.items() if k in ('image','imageMobile') and isinstance(v,str) and v.startswith('http'))
    if raw.get('imageLink'):
        photos.append(raw['imageLink'])
    photos.extend((dom_media or {}).get('photos',[]))
    return {'schema_version':1, 'normalized':normalized, 'fields':fields,
            'features':features, 'photos':list(dict.fromkeys(photos)),
            'media':dom_media or {}, 'extra':raw,
            'sources':{'flight_property':raw,'json_ld':sanitize(ld or [])},
            'visible_text':visible_text, 'errors':errors,
            'quality':'partial' if errors else 'success'}
