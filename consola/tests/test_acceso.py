"""IAP con ES256 y JWKS sintéticos; ninguna conexión a Google o Gemini."""
import io
import json
import time
from unittest.mock import Mock

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient
from fastapi.routing import APIRoute

from consola.acceso import IAP_ISSUER, IAP_KEYS, claves_iap
from metro.web import app
import metro.web as web
from test_browser import servidor, pagina

AUD = '/projects/123456789/locations/us-central1/services/radar-sintetico'
ORIGIN = 'https://radar-sintetico.example'


@pytest.fixture
def iap(monkeypatch, tmp_path):
    # Incluso las aserciones de cabeceras GET deben quedar aisladas de datos reales.
    for name, filename in [('METRO_DB', 'metro.sqlite'), ('RADAR_CRM_DB', 'crm.sqlite'),
                           ('WASI_DB', 'wasi.sqlite'), ('FINCARAIZ_DB', 'fincaraiz.sqlite')]:
        monkeypatch.setenv(name, str(tmp_path / filename))
    monkeypatch.setenv('RADAR_AUTH_MODE', 'iap')
    monkeypatch.setenv('RADAR_IAP_AUDIENCE', AUD)
    monkeypatch.setenv('RADAR_PUBLIC_ORIGIN', ORIGIN)
    monkeypatch.setenv('K_SERVICE', 'radar-sintetico')
    private = ec.generate_private_key(ec.SECP256R1())
    public = json.loads(jwt.algorithms.ECAlgorithm.to_jwk(private.public_key()))
    public.update(kid='sintetica', alg='ES256', use='sig')
    opener = Mock()

    def abrir(request, **kwargs):
        assert request.full_url == IAP_KEYS
        assert kwargs['timeout'] == 5
        return io.BytesIO(json.dumps({'keys': [public]}).encode())

    opener.open.side_effect = abrir
    monkeypatch.setattr('jwt.jwks_client.urllib.request.build_opener', lambda *a: opener)
    claves_iap.cache_clear()

    def token(cambios=None, quitar=(), key=None, headers=None):
        now = int(time.time())
        claims = {'iss': IAP_ISSUER, 'aud': AUD, 'iat': now - 1,
                  'exp': now + 599, 'sub': 'cuenta-sintetica', 'email': 'sintetica@example.test'}
        claims.update(cambios or {})
        for field in quitar:
            claims.pop(field)
        return jwt.encode(claims, key or private, algorithm='ES256',
                          headers={'kid': 'sintetica', **(headers or {})})

    yield token, opener
    claves_iap.cache_clear()


def cliente_iap(token=None, **kwargs):
    headers = {'Origin': ORIGIN}
    if token is not None:
        headers['X-Goog-IAP-JWT-Assertion'] = token
    return TestClient(app, headers=headers, **kwargs)


@pytest.mark.parametrize('caso', ['manipulada', 'firma_ajena', 'expirada', 'audiencia', 'emisor',
    'futura', 'larga', 'sin_exp', 'sin_iat', 'sin_sub', 'aud_lista', 'kid', 'algoritmo', 'rota'])
def test_credenciales_invalidas(iap, caso):
    token, _ = iap
    now = int(time.time())
    variantes = {
        'expirada': {'iat': now - 700, 'exp': now - 100},
        'audiencia': {'aud': AUD + '-otro'}, 'emisor': {'iss': 'https://evil.test'},
        'futura': {'iat': now + 100, 'exp': now + 600}, 'larga': {'exp': now + 900},
        'aud_lista': {'aud': [AUD]},
    }
    if caso == 'manipulada':
        parts = token().split('.')
        claims = json.loads(jwt.utils.base64url_decode(parts[1]))
        claims['sub'] = 'intruso'
        parts[1] = jwt.utils.base64url_encode(json.dumps(claims).encode()).decode()
        credencial = '.'.join(parts)
    elif caso == 'firma_ajena':
        credencial = token(key=ec.generate_private_key(ec.SECP256R1()))
    elif caso.startswith('sin_'):
        credencial = token(quitar=[caso[4:]])
    elif caso == 'kid':
        credencial = token(headers={'kid': 'desconocida'})
    elif caso == 'algoritmo':
        credencial = jwt.encode({'sub': 'intruso'}, 'sintetica-no-real-de-32-caracteres', algorithm='HS256', headers={'kid': 'sintetica'})
    elif caso == 'rota':
        credencial = 'no.es.jwt'
    else:
        credencial = token(variantes[caso])
    response = cliente_iap(credencial).get('/api/clientes')
    assert response.status_code == 401
    assert credencial not in response.text


def test_sin_credencial_ni_cabeceras_falsificadas(iap):
    c = cliente_iap()
    c.headers.update({'X-Goog-Authenticated-User-Email': 'accounts.google.com:dueno@example.test',
                      'X-Goog-Authenticated-User-ID': 'accounts.google.com:123',
                      'X-Forwarded-For': '127.0.0.1', 'X-Forwarded-Host': 'localhost'})
    assert c.get('/v0.6/').status_code == 401


def test_todas_las_rutas_rechazan_antes_de_dependencias(iap, monkeypatch, tmp_path):
    import re
    def prohibido(*args, **kwargs):
        pytest.fail('No se deben consultar datos, escribir ni crear tareas sin acceso')
    for route in app.routes:
        if isinstance(route, APIRoute):
            for dependency in route.dependant.dependencies:
                monkeypatch.setitem(app.dependency_overrides, dependency.call, prohibido)
    monkeypatch.setattr(web, 'Store', prohibido)
    monkeypatch.setenv('METRO_DB', str(tmp_path / 'no-crear.sqlite'))
    monkeypatch.setenv('RADAR_CRM_DB', str(tmp_path / 'no-crear-crm.sqlite'))
    c = cliente_iap()
    for route in app.routes:
        if route.path == '/health':
            continue
        path = re.sub(r'\{[^}]+\}', 'sintetico', route.path)
        for method in getattr(route, 'methods', {'GET'}):
            assert c.request(method, path).status_code == 401, (method, path)
    assert c.get('/v0.4/static/v04.js').status_code == 401
    assert c.get('/consola/static/v06.js').status_code == 401
    assert list(tmp_path.iterdir()) == []


def test_identidad_validada_y_cache(iap, escenario_consola):
    token, opener = iap
    c = cliente_iap(token())
    for path in ('/', '/v0.6/', '/v0.4/', '/consola/', '/catalog', '/api/catalog',
                 '/api/clientes', '/api/runs', '/consola/exportar.csv', '/v0.4/exportar.csv',
                 f"/api/runs/{escenario_consola['run']}/export", '/consola/static/v06.js'):
        assert c.get(path).status_code == 200, path
    assert opener.open.call_count == 1
    response = c.post('/api/clientes', json={'nombre': 'Cuenta autorizada'})
    assert response.status_code == 201
    assert len(c.get('/api/clientes').json()) == 1
    for path in ('/docs', '/openapi.json', '/redoc', '/docs/oauth2-redirect'):
        assert c.get(path).status_code == 404


def test_jwks_expiracion_y_fallo_cerrado(iap, escenario_consola):
    token, opener = iap
    c = cliente_iap(token())
    assert c.get('/api/clientes').status_code == 200
    # Expirar caché mediante su API; una descarga fallida nunca abre el acceso.
    claves_iap().jwk_set_cache.put(None)
    opener.open.side_effect = TimeoutError('no registrar datos')
    assert c.get('/api/clientes').status_code == 401
    assert opener.open.call_count == 2


def test_rotacion_de_claves_iap(iap, escenario_consola):
    token, opener = iap
    assert cliente_iap(token()).get('/api/clientes').status_code == 200
    nueva = ec.generate_private_key(ec.SECP256R1())
    public = json.loads(jwt.algorithms.ECAlgorithm.to_jwk(nueva.public_key()))
    public.update(kid='rotada', alg='ES256', use='sig')
    opener.open.side_effect = lambda *a, **kw: io.BytesIO(json.dumps({'keys': [public]}).encode())
    rotado = token(key=nueva, headers={'kid': 'rotada'})
    # El cooldown evita forzar descargas con kids arbitrarios. Tras él se renueva.
    assert cliente_iap(rotado).get('/api/clientes').status_code == 401
    claves_iap()._last_successful_fetch -= 31
    assert cliente_iap(rotado).get('/api/clientes').status_code == 200
    assert opener.open.call_count == 2


def test_duplicados_y_sin_tokens_en_logs(iap, caplog):
    token, _ = iap
    credencial = token({'exp': int(time.time()) - 100})
    c = cliente_iap(credencial)
    assert c.get('/api/clientes').status_code == 401
    assert credencial not in caplog.text and 'cuenta-sintetica' not in caplog.text
    headers = [('X-Goog-IAP-JWT-Assertion', token()), ('X-Goog-IAP-JWT-Assertion', token())]
    assert cliente_iap().get('/api/clientes', headers=headers).status_code == 401


def test_cli_local_rechaza_bind_publico(tmp_path):
    import os
    import subprocess
    import sys
    result = subprocess.run([sys.executable, 'scraper/run.py', '--db', str(tmp_path / 'sin-base.sqlite'),
                             'serve', '--host', '0.0.0.0'], capture_output=True, text=True,
                            env=dict(os.environ), timeout=15)
    assert result.returncode == 2 and 'requiere --host de loopback' in result.stderr
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize('mode,audience,origin', [('', AUD, ORIGIN), ('desconocido', AUD, ORIGIN),
    ('local', AUD, ORIGIN), ('iap', '', ORIGIN), ('iap', 'https://servicio.run.app', ORIGIN),
    ('iap', '/projects/123/global/backendServices/456', ORIGIN), ('iap', AUD, ''),
    ('iap', AUD, 'http://radar.test'), ('iap', AUD, ORIGIN + '/ruta'),
    ('iap', AUD, 'https://@radar.test'), ('iap', AUD, 'https://radar.test mala')])
def test_configuracion_cloud_run_cerrada(iap, monkeypatch, mode, audience, origin):
    monkeypatch.setenv('RADAR_AUTH_MODE', mode)
    monkeypatch.setenv('RADAR_IAP_AUDIENCE', audience)
    monkeypatch.setenv('RADAR_PUBLIC_ORIGIN', origin)
    c = cliente_iap(iap[0]())
    assert c.get('/v0.6/').status_code == 503
    assert c.get('/health').json() == {'status': 'ok'}
    assert c.head('/health').content == b''
    for path in ('/health/', '/health/privado', '/Health'):
        assert c.get(path).status_code == 503


@pytest.mark.parametrize('cloud_marker', ['K_SERVICE', 'K_REVISION', 'K_CONFIGURATION'])
def test_local_prohibido_por_marcadores_cloud_run(monkeypatch, cloud_marker):
    monkeypatch.setenv(cloud_marker, '')
    assert TestClient(app).get('/api/clientes').status_code == 503


@pytest.mark.parametrize('base,peer', [('http://127.0.0.1', '192.0.2.1'),
    ('http://radar.test', '127.0.0.1'), ('http://192.0.2.2', '127.0.0.1')])
def test_local_solo_loopback(base, peer):
    c = TestClient(app, base_url=base, client=(peer, 50000),
                   headers={'X-Forwarded-For': '127.0.0.1', 'X-Forwarded-Host': 'localhost'})
    assert c.get('/api/clientes').status_code == 403


def test_local_debe_ser_explicito(monkeypatch):
    monkeypatch.delenv('RADAR_AUTH_MODE')
    c = TestClient(app)
    assert c.get('/api/clientes').status_code == 503
    assert c.get('/health').json() == {'status': 'ok'}


@pytest.mark.parametrize('origin', [None, 'null', 'https://evil.test', ORIGIN + '.evil.test',
    ORIGIN + '/', 'http://radar-sintetico.example'])
def test_origen_estricto_sin_mutaciones(iap, tmp_path, monkeypatch, origin):
    monkeypatch.setenv('RADAR_CRM_DB', str(tmp_path / 'sin-escrituras.sqlite'))
    c = cliente_iap(iap[0]())
    c.headers.pop('Origin')
    headers = {} if origin is None else {'Origin': origin}
    for method, path in [('POST', '/api/clientes'), ('PUT', '/api/clientes/falso'),
                         ('POST', '/v0.6/fuentes'), ('POST', '/v0.4/comentarios/falso'),
                         ('POST', '/v0.6/oportunidades/falsa/gemini')]:
        assert c.request(method, path, headers=headers, json={}).status_code == 403
    assert list(tmp_path.iterdir()) == []


def test_origen_duplicado_y_fetch_site(iap):
    c = cliente_iap(iap[0]())
    assert c.post('/api/clientes', headers=[('Origin', ORIGIN), ('Origin', ORIGIN)], json={}).status_code == 403
    assert c.post('/api/clientes', headers={'Sec-Fetch-Site': 'cross-site'}, json={}).status_code == 403
    assert c.get('/api/clientes', headers={'Origin': 'https://evil.test'}).headers.get('access-control-allow-origin') is None


@pytest.mark.parametrize('width,height', [(1440, 900), (768, 1024), (390, 844)])
def test_chromium_formulario_local_y_rechazo_otra_pagina(servidor, pagina, width, height):
    page = pagina
    page.set_viewport_size({'width': width, 'height': height})
    page.goto(servidor + '/v0.6/')
    assert page.locator('[data-dashboard-section]').count() == 4
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    # Un formulario nativo desde otro origen debe alcanzar la barrera con 403.
    page.route('https://otra.test/**', lambda route: route.fulfill(content_type='text/html', body=(
        f'<form method="post" action="{servidor}/api/clientes"><input name="nombre" value="Intruso">'
        '<button>Enviar</button></form>')))
    page.goto('https://otra.test/')
    with page.expect_response(servidor + '/api/clientes') as response:
        page.get_by_role('button', name='Enviar').click()
    assert response.value.status == 403
    page.goto(servidor + '/v0.6/clientes')
    assert 'Intruso' not in page.locator('body').inner_text()
