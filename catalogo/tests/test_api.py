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
        'last_verified_at', 'state', 'id_interno', 'neighborhood', 'zone', 'building', 'geografia',
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
        'appearances', 'memberships', 'price_history', 'geografia',
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


@pytest.fixture
def catalogo_variado(escenario):
    store, run, servicio, client = escenario
    store.save_page(run, 2, '2', A, 'otros', [anuncio('3-M3'), anuncio('4-M4'), anuncio('5-M5')],
                    None, search_url=A)
    store.plan_incremental(run)
    def guardar(pid, normal, extra=None):
        d = documento()
        d['normalized'].update(normal)
        d['extra'] = extra or {}
        store.result(run, pid, 'success', d)
    guardar(ID, {
        'operation': 'Venta y Arriendo', 'price': 1000, 'currency': 'COP',
        'zone': 'Norte', 'neighborhood': 'Usaquén', 'area': 80, 'area_unit': 'm2',
        'built_area': 90, 'built_area_unit': 'm²', 'private_area': 70, 'private_area_unit': 'm2',
        'rooms': 3, 'bathrooms': 2, 'garages': 1, 'stratum': 5,
        'description': 'Jardín y terraza',
    }, {'salePrice': 1000, 'rentPrice': 10})
    guardar('2-M2', {
        'property_type': 'Apartamento', 'price': 2000, 'city': 'Medellín',
        'zone': 'Sur', 'neighborhood': 'El Poblado', 'area': 120, 'area_unit': 'm2',
        'rooms': 2, 'bathrooms': 1, 'garages': 0, 'stratum': 4,
    })
    guardar('3-M3', {
        'price': 500, 'currency': 'USD', 'area': 80, 'area_unit': 'm2',
        'rooms': 1, 'bathrooms': 1,
    })
    guardar('4-M4', {
        'operation': None, 'price': None, 'currency': None, 'city': None,
        'property_type': None, 'rooms': None, 'bathrooms': None,
    })
    guardar('5-M5', {'price': None})
    with store.connect() as db:
        for pid, fecha in (
            (ID, '2026-10-20T12:00:00+00:00'),
            ('2-M2', '2026-10-21T12:00:00+00:00'),
            ('3-M3', '2026-10-24T12:00:00+00:00'),
            ('4-M4', None), ('5-M5', None),
        ):
            db.execute('UPDATE properties SET updated=? WHERE id=?', (fecha, pid))
        db.execute("UPDATE search_memberships SET state='removed' WHERE search_url=?", (B,))
    return store, servicio, client


@pytest.mark.parametrize('parametros,esperados', [
    ({'texto': 'JARDIN'}, [ID]),
    ({'ciudad': 'BOGOTA'}, [ID, '3-M3', '5-M5']),
    ({'zonas': ['norte', 'sin-zona']}, [ID]),
    ({'barrios': ['usaquen', 'sin-barrio']}, [ID]),
    ({'tipos': ['apartamento']}, ['2-M2']),
    ({'tipos': ['apartamento', 'oficina']}, ['2-M2']),
    ({'operacion': 'arriendo'}, [ID]),
    ({'operacion': 'venta', 'moneda': 'COP', 'precio_min': '1000', 'precio_max': '2000'}, [ID, '2-M2']),
    ({'moneda': 'USD'}, ['3-M3']),
    ({'area_min_m2': '80', 'area_max_m2': '80'}, [ID, '3-M3']),
    ({'tipo_area': 'construida', 'area_min_m2': '90'}, [ID]),
    ({'tipo_area': 'privada', 'area_min_m2': '80'}, []),
    ({'habitaciones_min': 2, 'habitaciones_max': 2}, ['2-M2']),
    ({'banos_min': 2, 'parqueaderos_min': 1}, [ID]),
    ({'parqueaderos_min': 0}, [ID, '2-M2']),
    ({'estratos': [4]}, ['2-M2']),
    ({'fuente': 'otro'}, []),
    ({'disponibilidad': 'retirado'}, []),
    ({'search_url': B, 'disponibilidad': 'retirado'}, [ID]),
    ({'fuente': 'metrocuadrado', 'id_busqueda': B, 'disponibilidad': 'retirado'}, [ID]),
    ({'requiere_revision': False, 'ciudad': 'Medellin'}, ['2-M2']),
])
def test_filtros_http_sobre_datos_persistidos(catalogo_variado, parametros, esperados):
    client = catalogo_variado[2]
    respuesta = client.get('/api/catalog', params=parametros)
    assert respuesta.status_code == 200, respuesta.text
    assert [p['id'] for p in respuesta.json()['items']] == esperados
    assert respuesta.json()['total'] == len(esperados)


def test_rango_de_arriendo_usa_precio_correcto_sin_convertir_moneda(catalogo_variado):
    client = catalogo_variado[2]
    parametros = {'operacion': 'arriendo', 'moneda': 'COP', 'precio_max': 10, 'orden': 'precio_asc'}
    body = client.get('/api/catalog', params=parametros).json()
    assert body['total'] == 1
    item = body['items'][0]
    assert item['price'] == 10 and item['operation'] == 'arriendo' and item['currency'] == 'COP'
    assert item['ofertas'] == [{'operation': 'arriendo', 'price': 10, 'currency': 'COP'}]
    parametros['moneda'] = 'USD'
    assert client.get('/api/catalog', params=parametros).json()['total'] == 0
    sin_filtros = client.get('/api/catalog').json()['items'][0]
    assert sin_filtros['price'] == 1000
    assert 'ofertas' not in sin_filtros


def test_filtros_combinados_orden_total_y_paginacion(catalogo_variado):
    _, servicio, client = catalogo_variado
    params = {
        'texto': 'terraza', 'ciudad': 'bogota', 'tipos': ['casa'],
        'operacion': 'venta', 'moneda': 'COP', 'precio_min': 1000, 'precio_max': 1000,
        'tipo_area': 'privada', 'area_min_m2': 70, 'area_max_m2': 70,
        'habitaciones_min': 3, 'banos_min': 2, 'parqueaderos_min': 1,
        'disponibilidad': 'activo',
    }
    assert client.get('/api/catalog', params=params).json()['total'] == 1
    paginas = []
    for offset in (0, 1, 2, 3):
        respuesta = client.get('/api/catalog', params={
            'operacion': 'venta', 'moneda': 'COP', 'orden': 'precio_desc',
            'limit': 1, 'offset': offset,
        }).json()
        assert respuesta['total'] == 3
        paginas.extend(respuesta['items'])
    assert [p['id'] for p in paginas] == ['2-M2', ID, '5-M5']
    assert len({p['id_interno'] for p in paginas}) == 3
    assert len(servicio.listar()) == 5  # Varias búsquedas no duplican el inmueble.


@pytest.mark.parametrize('orden', ['area_asc', 'area_desc'])
def test_orden_http_area_empates_y_ausentes(catalogo_variado, orden):
    client = catalogo_variado[2]
    body = client.get('/api/catalog', params={'orden': orden}).json()
    pares = sorted((ID, '3-M3'), key=lambda id: identificar_inmueble('metrocuadrado', id))
    ausentes = sorted(('4-M4', '5-M5'), key=lambda id: identificar_inmueble('metrocuadrado', id))
    esperado = pares + ['2-M2'] if orden == 'area_asc' else ['2-M2'] + pares
    assert [p['id'] for p in body['items']] == esperado + ausentes
    assert body == client.get('/api/catalog', params={'orden': orden}).json()


def test_orden_http_actualizacion_no_confunde_extraccion_y_presencia(catalogo_variado):
    client = catalogo_variado[2]
    body = client.get('/api/catalog?orden=actualizacion_desc').json()
    assert [p['id'] for p in body['items']][:3] == ['3-M3', '2-M2', ID]
    assert client.get('/api/catalog?orden=actualizacion_asc').json()['items'][0]['id'] == ID


def test_paginacion_anterior_hasta_1000_y_offset_vacio(catalogo_variado):
    client = catalogo_variado[2]
    body = client.get('/api/catalog?limit=1000&offset=0').json()
    assert body['total'] == 5 and len(body['items']) == 5 and body['limit'] == 1000
    vacia = client.get('/api/catalog?limit=2&offset=100').json()
    assert vacia == {'total': 5, 'items': [], 'limit': 2, 'offset': 100}


@pytest.mark.parametrize('query', [
    'precio_min=10',
    'precio_min=10&moneda=COP',
    'orden=precio_desc',
    'operacion=venta&moneda=COP&precio_min=20&precio_max=10',
    'area_min_m2=100&area_max_m2=80',
    'habitaciones_min=3&habitaciones_max=1',
    'banos_min=-1',
    'parqueaderos_min=-1',
    'area_min_m2=NaN',
    'precio_min=Infinity&operacion=venta&moneda=COP',
    'moneda=cop',
    'tipos=desconocido',
    'operacion=compra',
    'tipo_area=indefinida',
    'disponibilidad=vendido',
    'orden=otro',
    'id_busqueda=sin-fuente',
    'texto=%20%20',
])
def test_consultas_nuevas_invalidas_dan_422(catalogo_variado, query):
    assert catalogo_variado[2].get('/api/catalog?' + query).status_code == 422


def test_busquedas_contradictorias_no_se_ignoran(catalogo_variado):
    client = catalogo_variado[2]
    respuesta = client.get('/api/catalog', params={
        'search_url': A, 'fuente': 'metrocuadrado', 'id_busqueda': B,
    })
    assert respuesta.status_code == 422
