"""Persistencia web contra almacenamiento simulado, sin Google ni datos reales."""
import asyncio
import os
import sqlite3
import threading
from contextlib import closing
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx
import pytest
from google.api_core.exceptions import PreconditionFailed
from starlette.applications import Starlette
from starlette.background import BackgroundTask
from starlette.responses import JSONResponse
from starlette.routing import Route

from consola.acceso import AccesoRadar
from consola.durable import WebDurable
from wasi.durable import EstadoGCS


class Blob:
    def __init__(self):
        self.generation = None
        self.data = None
        self.fail_upload = False
        self.mutex = threading.Lock()

    def upload_from_string(self, data, if_generation_match, **kwargs):
        with self.mutex:
            if self.fail_upload:
                raise RuntimeError('synthetic-secret-must-not-leak')
            if if_generation_match != (self.generation or 0):
                raise PreconditionFailed('busy')
            self.generation = (self.generation or 0) + 1
            self.data = data

    def reload(self, **kwargs):
        if self.data is None:
            raise RuntimeError('NotFound')

    def download_as_bytes(self, if_generation_match, **kwargs):
        assert if_generation_match == self.generation
        return self.data

    def delete(self, if_generation_match, **kwargs):
        with self.mutex:
            assert if_generation_match == self.generation
            self.generation = None
            self.data = None


class Client:
    def __init__(self):
        self.blobs = {}

    def bucket(self, name):
        return self

    def blob(self, name):
        return self.blobs.setdefault(name, Blob())


@pytest.fixture
def durable(tmp_path, monkeypatch):
    monkeypatch.setenv('RADAR_CRM_DB', str(tmp_path / 'must-not-write.sqlite'))
    client = Client()
    source = tmp_path / 'source'
    source.mkdir()
    db = sqlite3.connect(source / 'metro-consola.sqlite')
    db.execute('CREATE TABLE synthetic (value TEXT)')
    db.commit()
    db.close()
    factory = lambda: EstadoGCS('synthetic', client=client)
    with factory() as state:
        state.guardar(source)

    def write():
        with closing(sqlite3.connect(os.environ['RADAR_CRM_DB'])) as db, db:
            db.execute("INSERT INTO synthetic VALUES ('RADAR_CLOUD_TEST')")

    async def endpoint(request):
        if request.method == 'POST':
            if request.url.path == '/background':
                return JSONResponse({'ok': True}, background=BackgroundTask(write))
            write()
        with closing(sqlite3.connect(os.environ['RADAR_CRM_DB'])) as db, db:
            rows = db.execute('SELECT value FROM synthetic').fetchall()
        return JSONResponse({'values': [r[0] for r in rows]})

    app = Starlette(routes=[Route('/record', endpoint, methods=['GET', 'POST']),
                            Route('/background', endpoint, methods=['POST'])])
    return client, factory, app


def call(app, method='GET', path='/record'):
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='https://synthetic.example') as c:
            return await c.request(method, path)
    with ThreadPoolExecutor(max_workers=1) as executor:
        return executor.submit(lambda: asyncio.run(run())).result()


def test_reemplazo_recupera_escritura_confirmada_y_entorno(durable, tmp_path):
    client, factory, app = durable
    old_path = os.environ['RADAR_CRM_DB']
    first = WebDurable(app, factory, tmp_path / 'instance1')
    assert call(first, 'POST').status_code == 200
    second = WebDurable(app, factory, tmp_path / 'instance2')
    assert call(second).json()['values'] == ['RADAR_CLOUD_TEST']
    assert os.environ['RADAR_CRM_DB'] == old_path
    assert not Path(old_path).exists()
    assert not list((tmp_path / 'instance1').glob('request-*'))


def test_background_termina_antes_del_checkpoint(durable, tmp_path):
    client, factory, app = durable
    assert call(WebDurable(app, factory, tmp_path / 'first'), 'POST', '/background').status_code == 200
    assert call(WebDurable(app, factory, tmp_path / 'replacement')).json()['values'] == ['RADAR_CLOUD_TEST']


def test_subida_fallida_no_confirma_y_no_filtra_secreto(durable, tmp_path, caplog):
    client, factory, app = durable
    client.blob('radar/state.tar.gz').fail_upload = True
    response = call(WebDurable(app, factory, tmp_path / 'instance'), 'POST')
    assert response.status_code == 503
    assert 'synthetic-secret' not in response.text + caplog.text
    client.blob('radar/state.tar.gz').fail_upload = False
    assert call(WebDurable(app, factory, tmp_path / 'replacement')).json()['values'] == []


def test_job_exclusivo_rechaza_web_sin_mutacion(durable, tmp_path):
    client, factory, app = durable
    before = client.blob('radar/state.tar.gz').data
    with factory():
        response = call(WebDurable(app, factory, tmp_path / 'web'), 'POST')
        assert response.status_code == 503
        assert response.headers['retry-after'] == '30'
    assert client.blob('radar/state.tar.gz').data == before
    assert call(WebDurable(app, factory, tmp_path / 'replacement')).json()['values'] == []


def test_acceso_antes_de_storage(durable, tmp_path, monkeypatch):
    _, _, app = durable
    monkeypatch.setenv('RADAR_AUTH_MODE', 'iap')
    monkeypatch.setenv('RADAR_IAP_AUDIENCE', '/projects/123/locations/us-central1/services/synthetic')
    monkeypatch.setenv('RADAR_PUBLIC_ORIGIN', 'https://synthetic.example')
    def forbidden():
        pytest.fail('No se permite tocar storage antes de autenticar')
    protected = AccesoRadar(WebDurable(app, forbidden, tmp_path / 'web'))
    assert call(protected).status_code == 401
    assert call(protected, path='/health').status_code == 200

def test_app_real_clientes_catalogo_y_reemplazo(escenario_consola, tmp_path, monkeypatch):
    import shutil
    from metro.web import app as real_app
    client = Client()
    source = tmp_path / 'source'
    source.mkdir()
    shutil.copyfile(escenario_consola['ruta'], source / 'metro.sqlite')
    factory = lambda: EstadoGCS('synthetic', client=client)
    with factory() as state:
        state.guardar(source)
    monkeypatch.setenv('RADAR_AUTH_MODE', 'iap')
    monkeypatch.setenv('RADAR_IAP_AUDIENCE', '/projects/123/locations/us-central1/services/synthetic')
    monkeypatch.setenv('RADAR_PUBLIC_ORIGIN', 'https://synthetic.example')
    monkeypatch.setattr('consola.acceso.validar_iap', lambda *a: {'sub': 'synthetic'})
    def instance(name):
        return AccesoRadar(WebDurable(real_app, factory, tmp_path / name))
    async def scenario():
        headers = {'x-goog-iap-jwt-assertion': 'synthetic', 'origin': 'https://synthetic.example'}
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=instance('first')), base_url='https://synthetic.example', headers=headers) as c:
            response = await c.post('/api/clientes', json={'nombre': 'RADAR_CLOUD_TEST', 'telefono': None})
            assert response.status_code == 201
            identifier = response.json()['id']
            assert (await c.get('/v0.6/')).status_code == 200
            assert (await c.get('/v0.4/')).status_code == 200
            assert (await c.get('/api/catalog')).status_code == 200
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=instance('replacement')), base_url='https://synthetic.example', headers=headers) as c:
            response = await c.get('/api/clientes/' + identifier)
            assert response.status_code == 200
            assert response.json()['nombre'] == 'RADAR_CLOUD_TEST'
    with ThreadPoolExecutor(max_workers=1) as executor:
        executor.submit(lambda: asyncio.run(scenario())).result()
