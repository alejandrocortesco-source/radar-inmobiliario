"""Frontera HTTP común: IAP firmado o desarrollo explícito en loopback.

La autorización de cuentas vive exclusivamente en IAP/IAM. No se crean sesiones,
usuarios ni credenciales propias; tampoco se aceptan identidades sin firma.
"""
import ipaddress
import os
import re
from functools import lru_cache
from urllib.parse import urlsplit

import jwt
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

IAP_KEYS = 'https://www.gstatic.com/iap/verify/public_key-jwk'
IAP_ISSUER = 'https://cloud.google.com/iap'
AUDIENCE = re.compile(r'/projects/[0-9]+/locations/[a-z0-9-]+/services/[a-z][a-z0-9-]*')
SAFE_METHODS = {'GET', 'HEAD', 'OPTIONS'}
DOCS = {'/docs', '/docs/oauth2-redirect', '/redoc', '/openapi.json'}


def en_cloud_run():
    return any(k in os.environ for k in ('K_SERVICE', 'K_REVISION', 'K_CONFIGURATION'))


def loopback(host):
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def origen_valido(value):
    """Un origen HTTPS canónico, sin ruta, credenciales ni parámetros."""
    try:
        url = urlsplit(value)
        return (bool(re.fullmatch(r'https://[a-z0-9.-]+(?::[0-9]+)?', value))
                and url.hostname and url.username is None
                and url.password is None and not url.path and not url.query
                and not url.fragment and url.port != 0
                and value == f'https://{url.netloc}')
    except ValueError:
        return False


@lru_cache(maxsize=1)
def claves_iap():
    # Caché JWKS de PyJWT (5 min), rotación y cooldown ante kid desconocido.
    # Sin caché indefinida por clave ni URL tomada de la credencial recibida.
    return jwt.PyJWKClient(IAP_KEYS, cache_jwk_set=True, lifespan=300, timeout=5)


def validar_iap(token, audience):
    header = jwt.get_unverified_header(token)
    if header.get('alg') != 'ES256' or not isinstance(header.get('kid'), str) or not header['kid']:
        raise jwt.InvalidTokenError('Cabecera inválida')
    key = claves_iap().get_signing_key(header['kid'])
    claims = jwt.decode(token, key.key, algorithms=['ES256'], audience=audience,
                        issuer=IAP_ISSUER, leeway=30,
                        options={'require': ['exp', 'iat', 'iss', 'aud', 'sub'], 'strict_aud': True})
    # IAP limita la duración a 10 minutos + dos tolerancias de reloj.
    if (type(claims['iat']) not in (int, float) or type(claims['exp']) not in (int, float)
            or not 0 < claims['exp'] - claims['iat'] <= 660 or not claims['sub']):
        raise jwt.InvalidTokenError('Vigencia inválida')
    return claims


class AccesoRadar:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] not in ('http', 'websocket'):
            return await self.app(scope, receive, send)
        if scope['type'] == 'websocket':
            # No hay flujos WebSocket en Radar; no dejar una vía futura abierta.
            return await send({'type': 'websocket.close', 'code': 1008})
        request = Request(scope)

        async def rechazo(status, detail):
            # Mensajes fijos: nunca incluir token, claims ni excepciones del proveedor.
            response = JSONResponse({'detail': detail}, status_code=status,
                                    headers={'Cache-Control': 'no-store'})
            await response(scope, receive, send)

        if scope['path'] == '/health' and request.method in {'GET', 'HEAD'}:
            response = (Response() if request.method == 'HEAD'
                        else JSONResponse({'status': 'ok'}))
            return await response(scope, receive, send)

        mode = os.environ.get('RADAR_AUTH_MODE', '')
        if mode == 'local' and not en_cloud_run():
            # Usar la conexión ASGI, nunca X-Forwarded-* o cabeceras de identidad.
            client, server = scope.get('client'), scope.get('server')
            host = request.headers.get('host', '')
            try:
                host_url = urlsplit(f'http://{host}')
                host_ok = (host_url.hostname == 'localhost' or loopback(host_url.hostname or ''))
                host_ok = host_ok and not host_url.username and not host_url.password and not host_url.path
                host_ok = host_ok and not host_url.query and not host_url.fragment and host_url.port != 0
            except ValueError:
                host_ok = False
            if (not client or not server or not loopback(client[0])
                    or not loopback(server[0]) or not host_ok):
                return await rechazo(403, 'El modo local requiere loopback.')
            origin = f"{scope['scheme']}://{host}"
        elif mode == 'iap':
            audience = os.environ.get('RADAR_IAP_AUDIENCE', '')
            origin = os.environ.get('RADAR_PUBLIC_ORIGIN', '')
            if not AUDIENCE.fullmatch(audience) or not origen_valido(origin):
                return await rechazo(503, 'Acceso no configurado.')
            tokens = request.headers.getlist('x-goog-iap-jwt-assertion')
            if len(tokens) != 1 or not tokens[0] or len(tokens[0]) > 16384:
                return await rechazo(401, 'Se requiere acceso mediante IAP.')
            try:
                # La descarga de JWKS no bloquea el loop de FastAPI.
                claims = await run_in_threadpool(validar_iap, tokens[0], audience)
            except Exception:
                # Incluye fallos de red/JWKS: siempre cerrado y sin registrar credenciales.
                return await rechazo(401, 'Credencial IAP no válida.')
            scope.setdefault('state', {})['iap_subject'] = claims['sub']
            if scope['path'] in DOCS:
                return await rechazo(404, 'No encontrado.')
        else:
            return await rechazo(503, 'Acceso no configurado.')

        if request.method not in SAFE_METHODS:
            # Origin obligatorio también en JSON/API: sin fallback Referer ni CORS.
            origins = request.headers.getlist('origin')
            if (origins != [origin]
                    or request.headers.get('sec-fetch-site') in {'cross-site', 'same-site'}):
                return await rechazo(403, 'Origen de solicitud no permitido.')
        return await self.app(scope, receive, send)
