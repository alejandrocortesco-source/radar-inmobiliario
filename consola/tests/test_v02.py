"""Contratos v0.2: enlaces sin medios, exportación filtrada e historial real."""
import csv
import hashlib
import io
import json
from dataclasses import replace
from decimal import Decimal
from urllib.parse import parse_qs, urlsplit
import pytest

from bs4 import BeautifulSoup
from fastapi.testclient import TestClient

from catalogo.identidad import identificar_inmueble
from catalogo.modelos import TipoArea
from consola.presentacion import area_principal, enlace_mapa, historial_visible
from metro.web import app, servicio


@pytest.mark.parametrize('importe,moneda,esperado', [
    (Decimal('1250000'), 'COP', '$1.250.000'),
    (Decimal('1250000.50'), None, '$1.250.000,5'),
    (Decimal('1250'), 'USD', '$1.250'),
    (None, None, 'Precio no informado'),
])
def test_precio_visual_cop_sin_cambiar_oferta(importe, moneda, esperado):
    from catalogo.modelos import Inmueble, Oferta, Operacion, Origen
    from consola.presentacion import ofertas_visibles
    oferta = Oferta(operacion=Operacion.ARRIENDO, precio=importe, moneda=moneda)
    inmueble = Inmueble(origen=Origen(fuente='portal', id_original='1'), ofertas=(oferta,))
    vista = ofertas_visibles(inmueble)[0]
    assert vista['precio'] == esperado and vista['operacion'] == 'Arriendo'
    assert vista['moneda'] == 'COP'
    assert oferta.precio == importe and oferta.moneda == moneda


def test_historial_formato_cop_conserva_datos_y_verificacion():
    from copy import deepcopy
    from consola.presentacion import precio_historico
    dato = {'status': 'valid', 'amount': '1250000', 'currency': None, 'operation': 'venta'}
    copia = deepcopy(dato)
    assert precio_historico(dato) == 'Venta · $1.250.000'
    assert dato == copia
    assert precio_historico({**dato, 'status': 'uncomparable'}) == 'No comparable'


def test_formato_visual_no_altera_moneda_filtros_api_ni_exportacion(escenario_consola):
    datos = escenario_consola
    doc = datos['documentos']['1-M1']
    doc['normalized']['currency'] = 'USD'
    datos['store'].result(datos['run'], '1-M1', 'success', doc)
    antes = hashlib.sha256(datos['ruta'].read_bytes()).hexdigest()
    client = TestClient(app)
    params = {'texto': 'Casa con jardín 01', 'operacion': 'venta', 'moneda': 'USD', 'orden': 'precio_desc'}
    pagina = BeautifulSoup(client.get('/consola/', params=params).text, 'html.parser')
    assert pagina.select_one('td.prices').get_text(' ', strip=True) == '$101.000.000 · Venta'
    ficha = BeautifulSoup(client.get(pagina.select_one('.property-link')['href']).text, 'html.parser')
    assert ficha.select_one('.offers').get_text(' ', strip=True) == 'Venta $101.000.000 Arriendo $1.000.000'
    assert 'Moneda no informada' not in pagina.text + ficha.text
    assert client.get('/api/catalog', params=params).json()['items'][0]['currency'] == 'USD'
    filas = list(csv.DictReader(io.StringIO(client.get('/consola/exportar.csv', params=params).content.decode('utf-8-sig')), delimiter=';'))
    assert filas[0]['Moneda'] == 'USD' and filas[0]['Precio'] == '101000000'
    assert hashlib.sha256(datos['ruta'].read_bytes()).hexdigest() == antes


def test_historial_almacenado_con_operacion_moneda_y_verificacion(escenario_consola):
    store = escenario_consola['store']
    anterior = {'status': 'valid', 'amount': '540000000', 'currency': 'COP', 'operation': 'venta'}
    nuevo = {**anterior, 'amount': '520000000'}
    with store.connect() as db:
        db.execute('INSERT INTO price_changes (run_id,property_id,previous_price_json,new_price_json,'
                   'detected_at,source,verification,detail_price_json) VALUES (?,?,?,?,?,?,?,?)',
                   (escenario_consola['run'], '1-M1', json.dumps(anterior), json.dumps(nuevo),
                    '2026-10-24T13:00:00+00:00', 'listing', 'confirmed', json.dumps(nuevo)))
    ruta = escenario_consola['ruta']
    antes = hashlib.sha256(ruta.read_bytes()).hexdigest()
    pagina = BeautifulSoup(TestClient(app).get('/consola/inmuebles/' +
                           identificar_inmueble('metrocuadrado', '1-M1')).text, 'html.parser')
    fila = pagina.select_one('.history-table tbody tr').get_text(' ', strip=True)
    assert '$540.000.000' in fila and '$520.000.000' in fila and 'Venta' in fila
    assert '24/10/2026 · 08:00' in fila and 'Confirmado en ficha' in fila
    assert hashlib.sha256(ruta.read_bytes()).hexdigest() == antes


def test_historial_pendiente_no_se_presenta_confirmado():
    filas = historial_visible([{'verification': 'pending', 'new_price': {'status': 'uncomparable'}}])
    assert filas[0]['estado'] == 'Pendiente de verificar'
    assert filas[0]['nuevo'] == 'No comparable' and filas[0]['detalle'] == 'Sin dato'


def test_csv_exporta_todos_los_filtrados_sin_paginar(escenario_consola):
    response = TestClient(app).get('/consola/exportar.csv?ciudad=Bogot%C3%A1&operacion=venta'
                                   '&moneda=COP&orden=precio_desc&limit=2&offset=2')
    assert response.status_code == 200
    assert 'attachment' in response.headers['content-disposition']
    filas = list(csv.DictReader(io.StringIO(response.content.decode('utf-8-sig')), delimiter=';'))
    assert len(filas) == 13
    assert filas[0]['ID'] == '13-M13' and filas[-1]['ID'] == '1-M1'
    assert all(f['Ciudad'] == 'Bogotá' and f['Moneda'] == 'COP' and f['Operación'] == 'venta' for f in filas)
    assert len(list(csv.DictReader(io.StringIO(TestClient(app).get(
        '/consola/exportar.csv?texto=sin-coincidencias').content.decode('utf-8-sig')), delimiter=';'))) == 0
    assert TestClient(app).get('/consola/exportar.csv?precio_min=1').status_code == 422


def test_csv_neutraliza_formulas_y_preserva_doble_oferta(escenario_consola):
    datos = escenario_consola
    doc = datos['documentos']['1-M1']
    doc['normalized']['neighborhood'] = '=HYPERLINK("https://externo.test")'
    datos['store'].result(datos['run'], '1-M1', 'success', doc)
    response = TestClient(app).get('/consola/exportar.csv', params={'texto': 'Casa con jardín 01'})
    filas = list(csv.DictReader(io.StringIO(response.content.decode('utf-8-sig')), delimiter=';'))
    assert len(filas) == 2
    assert {f['Operación'] for f in filas} == {'venta', 'arriendo'}
    assert all(f['Barrio'].startswith("'=") for f in filas)


def test_enlaces_publicos_validos_y_mapa_sin_coordenadas_inventadas(escenario_consola):
    inmueble = servicio().obtener(identificar_inmueble('metrocuadrado', '1-M1'))
    enlace = enlace_mapa(inmueble)
    assert enlace == inmueble.portal_map_url == inmueble.origen.url + '#location-section'
    assert enlace_mapa(replace(inmueble, ciudad=None, direccion=None, barrio=None)) == enlace
    assert enlace_mapa(replace(inmueble, portal_map_url=None)) is None
    for valor in ('javascript:alert(1)', 'https://usuario:clave@www.metrocuadrado.com/inmueble/x',
                  'https://externo.test/#location-section', inmueble.origen.url,
                  inmueble.origen.url.replace('1-M1', 'otro') + '#location-section',
                  'https://www.metrocuadrado.com:incorrecto/inmueble/x#location-section'):
        assert enlace_mapa(replace(inmueble, portal_map_url=valor)) is None
    pagina = BeautifulSoup(TestClient(app).get('/consola/').text, 'html.parser')
    assert not pagina.select('img, iframe, video, source')
    enlaces = pagina.select('a[target="_blank"]')
    assert enlaces and all('noopener' in a['rel'] and 'noreferrer' in a['rel'] for a in enlaces)
    assert all(urlsplit(a['href']).scheme in ('https', 'http') for a in enlaces)


def test_un_precio_prioriza_venta_y_respeta_arriendo_con_ficha_completa(escenario_consola):
    client = TestClient(app)
    for parametros, precio, operacion in [
        ({}, '101.000.000', 'Venta'),
        ({'operacion': 'venta'}, '101.000.000', 'Venta'),
        ({'operacion': 'arriendo'}, '1.000.000', 'Arriendo'),
    ]:
        pagina = BeautifulSoup(client.get('/consola/', params={'texto': 'Casa con jardín 01', **parametros}).text, 'html.parser')
        celda = pagina.select_one('td.prices')
        assert len(celda.select(':scope > span')) == 1
        assert celda.get_text(' ', strip=True) == f'${precio} · {operacion}'
        ficha = BeautifulSoup(client.get(pagina.select_one('.property-link')['href']).text, 'html.parser')
        assert len(ficha.select('.offers > span')) == 2
        assert '101.000.000' in ficha.select_one('.offers').text and '1.000.000' in ficha.select_one('.offers').text


def test_iconos_accesibles_y_precision_del_mapa_original(escenario_consola):
    client = TestClient(app)
    pagina = BeautifulSoup(client.get('/consola/', params={'texto': 'Casa con jardín 01'}).text, 'html.parser')
    links = pagina.select_one('.external-links')
    assert len(links.select('svg[aria-hidden="true"]')) == 3
    controles = links.select(':scope > a, :scope > details > summary')
    assert len(controles) == 3 and all(c.get('aria-label') and c.get('title') for c in controles)
    mapa = links.select_one('a[href$="#location-section"]')
    assert 'Ubicación aproximada' in mapa['title'] and 'Google' not in pagina.text
    ficha = BeautifulSoup(client.get(pagina.select_one('.property-link')['href']).text, 'html.parser')
    assert 'Ubicación aproximada' in ficha.text
    sin_mapa = BeautifulSoup(client.get('/consola/', params={'texto': 'Casa con jardín 03'}).text, 'html.parser')
    assert sin_mapa.select_one('[aria-label="Mapa original no disponible"][aria-disabled="true"]')
    assert not sin_mapa.select('a[href*="maps"], a[href$="#location-section"]')


def test_prioridad_venta_independiente_del_orden_de_las_ofertas(escenario_consola):
    from catalogo.filtros import FiltrosCatalogo
    from consola.presentacion import tarjeta
    inmueble = servicio().obtener(identificar_inmueble('metrocuadrado', '1-M1'))
    invertido = replace(inmueble, ofertas=tuple(reversed(inmueble.ofertas)))
    assert tarjeta(invertido, FiltrosCatalogo(), '/consola/')['oferta_principal']['operacion'] == 'Venta'


def test_area_desconocida_no_sustituye_el_tipo_seleccionado(escenario_consola):
    inmueble = replace(servicio().listar()[0], area_construida_m2=None, area_privada_m2=Decimal('90'))
    assert area_principal(inmueble, TipoArea.CONSTRUIDA) == 'No especifica'
    assert area_principal(inmueble) == '90 m² (privada)'


def test_una_lectura_por_catalogo_y_enlaces_sin_sql(escenario_consola, monkeypatch):
    original = servicio()
    lecturas = []
    listar = original.listar

    def contar():
        lecturas.append(True)
        return listar()

    monkeypatch.setattr(original, 'listar', contar)
    app.dependency_overrides[servicio] = lambda: original
    try:
        assert TestClient(app).get('/consola/').status_code == 200
        assert len(lecturas) == 1
    finally:
        app.dependency_overrides.pop(servicio, None)
