"""Contratos HTTP originales, UUID comunes y revisión técnica en bases sintéticas."""

import json
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from catalogo.api import crear_router
from catalogo.identidad import identificar_inmueble
from catalogo.persistencia.sqlite import CatalogoSQLite
from catalogo.servicio import ServicioCatalogo
from metro.prices import search_identity
from metro.storage import Store
from metro.web import app
import metro.web as web


A = 'https://www.metrocuadrado.com/inmuebles/venta/bogota/norte'
B = 'https://www.metrocuadrado.com/inmuebles/venta/bogota/centro'
ID = '1-M1'
UUID = identificar_inmueble('metrocuadrado', ID)


def anuncio(pid=ID, precio=1000):
    return {'id': pid, 'url': 'https://www.metrocuadrado.com/inmueble/casa/' + pid,
            'raw': {'mtiponegocio': 'venta', 'mvalorventa': precio, 'currency': 'COP'}}


def documento(titulo='Casa completa', precio=1000, calidad='success'):
    return {
        'normalized': {
            'title': titulo, 'price': precio, 'currency': 'COP', 'operation': 'venta',
            'city': 'Bogotá', 'property_type': 'Casa',
            'description': 'Descripción completa', 'map_url': 'https://map.test/',
            'portal_map_url': 'https://portal.test/#location-section',
        },
        'quality': calidad, 'photos': ['https://foto.test/1.jpg'], 'features': [],
        'fields': {'map_url': {'raw': {'ubicacionaproximada': 'S'}}},
        'sources': {}, 'extra': {}, 'media': {}, 'visible_text': '', 'errors': [],
    }


@pytest.fixture
def escenario(tmp_path, monkeypatch):
    ruta = tmp_path / 'api.sqlite'
    monkeypatch.setenv('METRO_DB', str(ruta))
    store = Store(ruta)
    run = store.new_run(A, {'urls': [A, B], 'listing_currency': 'COP'})
    store.save_page(run, 1, '1', A, 'a', [anuncio(), anuncio('2-M2')], None, search_url=A)
    store.save_page(run, 1, '1', B, 'b', [anuncio()], None, search_url=B)
    store.plan_incremental(run)
    store.result(run, ID, 'success', documento())
    repo = CatalogoSQLite(ruta)
    servicio = ServicioCatalogo(repo, revision=repo, normalizar_busqueda=search_identity)
    return store, run, servicio, TestClient(app)


def test_servicio_comun_consulta_modelos_sin_fastapi_ni_sqlite():
    class Repositorio:
        def listar(self):
            return ('resultado',)
        def obtener(self, identificador):
            return identificador
    servicio = ServicioCatalogo(Repositorio())
    assert servicio.listar() == ('resultado',)
    assert servicio.obtener('identidad') == 'identidad'


def test_catalogo_conserva_contrato_y_agrega_identidad_interna(escenario):
    store, _, servicio, client = escenario
    body = client.get('/api/catalog').json()
    assert set(body) == {'total', 'items', 'limit', 'offset'}
    assert (body['total'], body['limit'], body['offset']) == (2, 100, 0)
    item = body['items'][0]
    assert set(item) == {
        'id', 'url', 'title', 'price', 'city', 'property_type', 'needs_refresh',
        'last_verified_at', 'state', 'id_interno',
    }
    assert item['id'] == ID and item['id_interno'] == UUID
    assert item['title'] == 'Casa completa' and item['price'] == 1000
    assert item['city'] == 'Bogotá' and item['property_type'] == 'Casa'
    assert item['state'] == 'active' and item['needs_refresh'] == 0
    assert len(servicio.listar()) == 2
    assert servicio.obtener(UUID).id_interno == item['id_interno']
    assert servicio.catalogo_compatible() == body
    assert store.catalog() == body  # Entrada histórica delegada, misma consulta.


def test_parametros_antiguos_por_busqueda_estado_y_pagina(escenario):
    store, _, _, client = escenario
    with store.connect() as db:
        db.execute("UPDATE search_memberships SET state='removed' WHERE search_url=?", (B,))
    # Normalización existente: parámetros de seguimiento no cambian la búsqueda.
    scoped = client.get('/api/catalog', params={'search_url': B + '?utm_source=x&search=form'})
    assert scoped.status_code == 200
    assert scoped.json()['total'] == 1
    assert scoped.json()['items'][0]['state'] == 'removed'
    assert client.get('/api/catalog?state=removed').json()['total'] == 0
    assert client.get('/api/catalog', params={'search_url': B, 'state': 'removed'}).json()['total'] == 1
    pagina = client.get('/api/catalog?limit=1&offset=1').json()
    assert pagina['total'] == 2 and pagina['items'][0]['id'] == '2-M2'
    assert client.get('/api/catalog?state=sin-estado').json()['total'] == 0


def test_ficha_original_y_uuid_tienen_misma_respuesta_y_evidencia(escenario):
    _, run, servicio, client = escenario
    original = client.get('/api/properties/' + ID)
    interna = client.get('/api/properties/' + UUID)
    assert original.status_code == interna.status_code == 200
    body = original.json()
    assert body == interna.json()
    assert set(body) == {
        'id', 'url', 'id_interno', 'job', 'data', 'catalog_data', 'needs_refresh',
        'appearances', 'memberships', 'price_history',
    }
    assert body['id'] == ID and body['id_interno'] == UUID
    assert body['data'] == body['catalog_data'] == documento()
    assert body['job']['run_id'] == run
    assert isinstance(body['job']['data_json'], str)  # Contrato técnico previo.
    assert json.loads(body['job']['data_json']) == documento()
    assert len(body['appearances']) == len(body['memberships']) == 2
    assert body['price_history'] == []
    assert servicio.obtener(UUID).fotos == tuple(body['data']['photos'])


def test_revision_parcial_no_sustituye_catalogo_y_run_id_preserva_instantanea(escenario):
    store, _, _, client = escenario
    run = store.new_run(A, {'urls': [A]})
    store.save_page(run, 1, '1', A, 'nueva', [anuncio(precio=1200)], None, search_url=A)
    store.plan_incremental(run)
    store.result(run, ID, 'partial', documento('Captura parcial', 1200, 'partial'))
    actual = client.get('/api/properties/' + ID).json()
    captura = client.get('/api/properties/' + UUID, params={'run_id': run}).json()
    assert actual['job']['status'] == 'partial'
    assert actual['data'] == documento()
    assert actual['needs_refresh'] is True
    assert captura['data'] == documento('Captura parcial', 1200, 'partial')
    assert captura['catalog_data'] == documento()
    cambio = captura['price_history'][0]
    assert cambio['previous_price']['amount'] == '1000'
    assert cambio['new_price']['amount'] == '1200'
    assert 'previous_price_json' not in cambio
    inexistente = client.get('/api/properties/' + ID + '?run_id=999').json()
    assert inexistente['job'] is None and inexistente['data'] == documento()


def test_ejecucion_sin_cambios_reutiliza_documento(escenario):
    store, _, _, client = escenario
    run = store.new_run(A, {'urls': [A], 'listing_currency': 'COP'})
    store.save_page(run, 1, '1', A, 'otra', [anuncio()], None, search_url=A)
    store.plan_incremental(run)
    body = client.get('/api/properties/' + ID).json()
    assert body['job']['run_id'] == run
    assert body['job']['status'] == 'unchanged'
    assert body['data'] == body['catalog_data'] == documento()


def test_endpoints_tecnicos_exportaciones_y_html_siguen_operativos(escenario):
    _, run, _, client = escenario
    assert client.get('/health').json() == {'status': 'ok'}
    assert client.get('/api/runs').json()[0]['id'] == run
    assert client.get('/api/properties').json()['total'] == 2
    assert client.get(f'/api/runs/{run}/report').json()['summary']['unique'] == 2
    exportacion = client.get(f'/api/runs/{run}/export')
    assert exportacion.status_code == 200
    assert 'attachment' in exportacion.headers['content-disposition']
    ficha = next(p for p in exportacion.json()['properties'] if p['id'] == ID)
    assert ficha['data'] == documento() and ficha['id_interno'] == UUID
    for ruta in ('/', '/catalog', '/properties/' + ID, '/properties/' + UUID):
        assert client.get(ruta).status_code == 200
    assert client.get('/api/runs/999/report').status_code == 404


@pytest.mark.parametrize('ruta', [
    '/api/catalog?limit=0', '/api/catalog?limit=1001', '/api/catalog?offset=-1',
    '/api/properties/1-M1?run_id=abc',
])
def test_validacion_http_previa_se_conserva(escenario, ruta):
    assert escenario[3].get(ruta).status_code == 422


def test_ficha_ausente_y_anuncio_pendiente(escenario):
    client = escenario[3]
    assert client.get('/api/properties/desconocido').json() == {'detail': 'Inmueble no encontrado'}
    assert client.get('/api/properties/desconocido').status_code == 404
    pendiente = client.get('/api/properties/2-M2').json()
    assert pendiente['data'] is None and pendiente['catalog_data'] is None


def test_router_reutilizable_sin_segundo_servidor(escenario):
    servicio = escenario[2]
    independiente = FastAPI()
    independiente.include_router(crear_router(lambda: servicio))
    cliente = TestClient(independiente)
    assert cliente.get('/api/catalog').json() == escenario[3].get('/api/catalog').json()
    assert cliente.get('/api/properties/' + UUID).json()['id'] == ID


def test_rutas_catalogo_y_ficha_estan_registradas_una_sola_vez():
    for ruta in ('/api/catalog', '/api/properties/{property_id}'):
        assert sum(r.path == ruta and 'GET' in (r.methods or set()) for r in app.routes) == 1


def test_api_de_consulta_no_inicializa_store_ni_crea_base(tmp_path, monkeypatch):
    ruta = tmp_path / 'no-existe.sqlite'
    monkeypatch.setenv('METRO_DB', str(ruta))
    def no_inicializar(*args, **kwargs):
        raise AssertionError('La lectura no debe construir Store')
    monkeypatch.setattr(web, 'Store', no_inicializar)
    client = TestClient(app)
    for endpoint in ('/api/catalog', '/api/properties/' + ID):
        assert client.get(endpoint).status_code == 503
    assert not ruta.exists()


def test_consultas_http_no_alteran_registros_ni_esquema(escenario, monkeypatch):
    store, _, _, client = escenario
    import hashlib
    ruta = Path(store.path)
    antes = hashlib.sha256(ruta.read_bytes()).hexdigest()
    def no_inicializar(*args, **kwargs):
        raise AssertionError('La lectura no debe construir Store')
    monkeypatch.setattr(web, 'Store', no_inicializar)
    assert client.get('/api/catalog').status_code == 200
    assert client.get('/api/properties/' + ID).status_code == 200
    assert hashlib.sha256(ruta.read_bytes()).hexdigest() == antes


def test_importacion_desde_carpeta_scraper_sin_instalar_paquetes():
    raiz = Path(__file__).resolve().parents[2]
    resultado = subprocess.run(
        [sys.executable, '-B', '-c', 'from metro.web import app; print(app.title)'],
        cwd=raiz / 'scraper', capture_output=True, text=True, timeout=15,
    )
    assert resultado.returncode == 0, resultado.stderr
    assert 'Metrocuadrado' in resultado.stdout
