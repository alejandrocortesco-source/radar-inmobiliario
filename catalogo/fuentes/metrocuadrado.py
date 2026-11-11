"""Validación sintáctica de búsquedas; no navega ni cambia sus filtros."""
import re
from urllib.parse import urlsplit


def validar_url(url):
    mensaje = ('Usa una URL de búsqueda de Metrocuadrado: /inmuebles/… o '
               '/tipo-de-inmueble/venta-o-arriendo/ubicación. No uses una ficha individual.')
    if not isinstance(url, str):
        raise ValueError(mensaje)
    url = url.strip()
    try:
        p = urlsplit(url)
        valida = (p.scheme in ('http', 'https')
                  and p.hostname in ('metrocuadrado.com', 'www.metrocuadrado.com')
                  and p.username is None and p.password is None
                  and p.port in (None, 80, 443) and len(url) <= 4096
                  and not any(c.isspace() or ord(c) < 32 for c in url))
        # Conservar rutas históricas. Las rutas por tipos mantienen literalmente
        # sus slugs: no se convierten a /inmuebles/ ni se infieren equivalencias.
        ruta = p.path.startswith('/inmuebles/') or re.fullmatch(
            r'/(?!inmueble(?:/|$))[a-z0-9]+(?:-[a-z0-9]+)*/(?:venta|arriendo)'
            r'(?:/[a-z0-9]+(?:-[a-z0-9]+)*)+/?', p.path)
    except ValueError:
        valida, ruta = False, False
    if not valida or not ruta:
        raise ValueError(mensaje)
    return url
