"""Presentación de contactos públicos, sin inferir indicativos ni enviar mensajes."""
import re
from urllib.parse import urlencode


def enlace_contacto(valor, *, whatsapp=False):
    if not isinstance(valor, str) or not re.fullmatch(r"\+?[0-9][0-9 ().-]*", valor.strip()):
        return None
    numero = re.sub(r"[ ().-]", "", valor.strip())
    digitos = numero.lstrip('+')
    if not 7 <= len(digitos) <= 15 or len(set(digitos)) == 1:
        return None
    if whatsapp:
        # wa.me requiere formato internacional: solo explícito o COP 57 publicado.
        if not ((numero.startswith('+') and digitos[0] != '0') or
                (len(digitos) == 12 and digitos.startswith('57'))):
            return None
        return 'https://wa.me/' + digitos
    return 'tel:' + numero


def url_anunciante(i):
    return '/consola/anunciante?' + urlencode({'inmueble': i.id_interno})


def contactos(inmuebles):
    grupos = {}
    for i in inmuebles:
        clave = (i.telefono, i.telefono_fijo, i.whatsapp, i.anunciante_direccion)
        if not any(clave):
            continue
        grupos.setdefault(clave, []).append(i)
    return [{'campos': [(etiqueta, valor, enlace_contacto(valor, whatsapp=etiqueta == 'WhatsApp'))
                        for etiqueta, valor in zip(('Móvil', 'Fijo', 'WhatsApp'), clave[:3]) if valor],
             'direccion': clave[3], 'inmuebles': items} for clave, items in grupos.items()]
