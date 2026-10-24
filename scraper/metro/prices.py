"""Comparación monetaria conservadora; no realiza conversión de divisas."""
from decimal import Decimal, InvalidOperation
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

SUPPORTED_CURRENCIES = {'COP', 'USD', 'EUR'}


def search_identity(url):
    parts = urlsplit(url)
    query = sorted((k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
                   if k not in ('search', 'src_url') and not k.startswith('utm_'))
    return urlunsplit(('https', 'www.metrocuadrado.com', parts.path.rstrip('/'), urlencode(query), ''))


def currency_code(value):
    if isinstance(value, dict):
        value = value.get('code') or value.get('codigo') or value.get('nombre')
    if value is None:
        return None
    value = str(value).strip().upper()
    return {'US$':'USD', 'COL$':'COP', '€':'EUR', 'PESOS COLOMBIANOS':'COP'}.get(value, value)


def price(value, currency=None, operation=None, *, fallback_currency=None, source=''):
    result = {'status':'uncomparable', 'amount':None, 'currency':None, 'operation':operation,
              'raw':str(value) if isinstance(value, Decimal) else value,
              'raw_currency':currency, 'source':source, 'reason':None}
    if operation not in ('venta','arriendo'):
        result['reason'] = 'unknown_operation'
        return result
    if value is None or value == '':
        result['reason'] = 'missing_price'
        return result
    explicit = currency_code(currency)
    text = str(value).strip().upper()
    embedded = set(re.findall(r'\b(COP|USD|EUR)\b', text))
    if 'US$' in text: embedded.add('USD')
    if 'COL$' in text: embedded.add('COP')
    if '€' in text: embedded.add('EUR')
    if len(embedded) > 1 or (explicit and embedded and explicit not in embedded):
        result['reason'] = 'conflicting_currency'
        return result
    code = explicit or next(iter(embedded), None) or currency_code(fallback_currency)
    result['currency'] = code
    result['currency_source'] = ('explicit' if explicit or embedded else
                                 'configured_search_currency' if code else 'unknown')
    if code not in SUPPORTED_CURRENCIES:
        result['reason'] = 'unknown_currency'
        return result
    try:
        if isinstance(value, bool):
            raise ValueError('boolean')
        if isinstance(value, (int, float, Decimal)):
            amount = Decimal(str(value))
        else:
            text = re.sub(r'\b(COP|USD|EUR)\b', '', text)
            for symbol in ('US$', 'COL$', '$', '€'):
                text = text.replace(symbol, '')
            text = re.sub(r'\s+', '', text)
            if not re.fullmatch(r'\d+(?:[.,]\d+)*', text):
                raise ValueError('ambiguous text')
            if ',' in text and '.' in text:
                decimal_sep = ',' if text.rfind(',') > text.rfind('.') else '.'
                thousands = '.' if decimal_sep == ',' else ','
                integer, fraction = text.rsplit(decimal_sep, 1)
                if not re.fullmatch(r'[1-9]\d{0,2}(?:'+re.escape(thousands)+r'\d{3})+', integer) or not 1 <= len(fraction) <= 2:
                    raise ValueError('ambiguous separators')
                text = integer.replace(thousands, '') + '.' + fraction
            elif ',' in text or '.' in text:
                sep = ',' if ',' in text else '.'
                if re.fullmatch(r'[1-9]\d{0,2}(?:'+re.escape(sep)+r'\d{3})+', text):
                    text = text.replace(sep, '')
                elif text.count(sep) == 1 and 1 <= len(text.rsplit(sep,1)[1]) <= 2:
                    text = text.replace(sep, '.')
                else:
                    raise ValueError('ambiguous separators')
            amount = Decimal(text)
        if not amount.is_finite() or amount <= 0 or amount.as_tuple().exponent < -2:
            raise ValueError('nonpositive, nonfinite or excessive precision')
    except (InvalidOperation, ValueError):
        result['reason'] = 'invalid_or_ambiguous_price'
        return result
    result.update(status='valid', amount=format(amount.normalize(),'f'), reason=None)
    return result


def listing_price(item, fallback_currency=None):
    raw = item.get('raw') or {}
    raw_operation = str(raw.get('mtiponegocio') or raw.get('businessType') or '').strip().lower()
    # El componente real del listado muestra arriendo sólo en oferta 'arriendo';
    # para 'venta y arriendo' publica mvalorventa. No mezcla ambas cantidades.
    operation = 'venta' if raw_operation == 'venta y arriendo' else raw_operation
    key = {'venta':'mvalorventa', 'arriendo':'mvalorarriendo'}.get(operation)
    value = raw.get(key) if key else None
    currency = next((raw[k] for k in ('currency','currencyCode','moneda','mmoneda') if raw.get(k)), None)
    result = price(value, currency, operation, fallback_currency=fallback_currency,
                   source=f'listing.{key}' if key else 'listing')
    result['raw_operation'] = raw_operation
    return result


def detail_price(data, fallback_currency=None):
    normalized = (data or {}).get('normalized') or {}
    raw_operation = str(normalized.get('operation') or '').strip().lower()
    operation = 'venta' if raw_operation == 'venta y arriendo' else raw_operation
    value, source = normalized.get('price'), 'detail.normalized.price'
    if value is None and raw_operation == 'venta y arriendo':
        raw = (data or {}).get('sources',{}).get('flight_property') or (data or {}).get('extra') or {}
        value, source = raw.get('salePrice'), 'detail.flight_property.salePrice'
    result = price(value, normalized.get('currency'), operation,
                   fallback_currency=fallback_currency, source=source)
    result['raw_operation'] = raw_operation
    return result


def comparable(a, b):
    return (a.get('status') == b.get('status') == 'valid' and
            a.get('currency') == b.get('currency') and a.get('operation') == b.get('operation'))


def same_price(a, b):
    return comparable(a, b) and Decimal(a['amount']) == Decimal(b['amount'])
