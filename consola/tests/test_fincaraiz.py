"""Integración de las tres fuentes con datos sintéticos y Chromium."""
import copy
import csv
import io
from unittest.mock import AsyncMock
from pathlib import Path

import pytest
from bs4 import BeautifulSoup
from fastapi.testclient import TestClient
from playwright.sync_api import expect
from catalogo.fuentes.fincaraiz import REFERENCIA, opciones_iniciales
from catalogo.identidad import identificar_inmueble
from catalogo.persistencia.busquedas import BusquedasSQLite
from fincaraiz.scraper import FincaraizStore
from metro.web import app, servicio
from oportunidades.modelos import ClienteDatos
from oportunidades.servicio import servicio_oportunidades
from oportunidades.seguimiento import SeguimientoSQLite
from oportunidades.automatizacion import despues_scraper
from test_v03 import necesidades
from test_browser import servidor


@pytest.fixture
def tercera(escenario_consola, monkeypatch):
    datos = escenario_consola
    ruta = datos['ruta'].with_name('fincaraiz.sqlite'); monkeypatch.setenv('FINCARAIZ_DB', str(ruta))
    store = FincaraizStore(ruta)
    c = copy.deepcopy(opciones_iniciales()[0])
    run = store.new_run(REFERENCIA, {'urls': [REFERENCIA], 'listing_currency': 'COP'})
    url = 'https://www.fincaraiz.com.co/apartamento-en-venta/123'
    link = {'id': '123', 'url': url, 'raw': {'businessType': 'venta', 'mvalorventa': 101000000}}
    store.save_page(run,1,'1',REFERENCIA,'page',[link],None)
    store.plan_incremental(run)
    doc = copy.deepcopy(datos['documentos']['2-M2'])
    doc['normalized'].update(id='123',url=url,title='Apartamento Fincaraíz sintético',advertiser='Empresa sintética',
                            advertiser_url='https://www.fincaraiz.com.co/inmobiliarias/123-empresa/propiedades', phone=None, whatsapp=None)
    store.result(run,'123','success',doc)
    store.update_search(run,REFERENCIA,complete=True)
    store.update_run(run,status='completed',finished='2026-11-09T05:00:00+00:00')
    repo = BusquedasSQLite(servicio_oportunidades().repositorio.ruta)
    repo.guardar_fincaraiz('Búsqueda Fincaraíz sintética', c)
    return datos, store, c


def test_catalogo_api_csv_anunciante_matching_y_decisiones(tercera):
    datos, store, c = tercera; client = TestClient(app)
    iid = identificar_inmueble('fincaraiz','123')
    assert client.get('/api/properties/fincaraiz:123').json()['id_interno'] == iid
    assert client.get('/api/catalog',params={'search_url':REFERENCIA}).json()['total'] == 1
    assert client.get('/api/catalog',params={'fuente':'fincaraiz'}).json()['total'] == 1
    rows = list(csv.DictReader(io.StringIO(client.get('/v0.4/exportar.csv').text.lstrip('\ufeff')), delimiter=';'))
    assert any(r['Fuente']=='fincaraiz' for r in rows)
    panel = client.get('/consola/anunciante', params={'inmueble':iid})
    assert panel.status_code == 200 and 'Perfil público del anunciante' in panel.text
    s = servicio_oportunidades(); o = s.capturar(ClienteDatos(nombre='Sintético'), necesidades())
    despues_scraper(datos['ruta'])
    seguimiento = SeguimientoSQLite(s.repositorio.ruta)
    seguimiento.decision(o.id, iid, 'preseleccionado')
    despues_scraper(datos['ruta'])
    assert seguimiento.decisiones(o.id)[iid]['estado'] == 'preseleccionado'
    assert any(r.inmueble.id_interno == iid for r in s.coincidencias(o.id, servicio()))


def test_registro_por_url_criterios_edicion_estado_y_error_sin_captura(tercera, monkeypatch):
    datos, store, c = tercera; client=TestClient(app)
    from fincaraiz import browser
    verificar=AsyncMock(return_value=c); monkeypatch.setattr(browser, 'verificar', verificar)
    antes=Path(store.path).read_bytes()
    valores={'fuente':'fincaraiz','nombre':'URL verificada','fr_url':REFERENCIA}
    assert client.post('/v0.6/fuentes',data=valores).status_code==200
    cr=c['criterios']; criterios={**valores, 'fr_modo':'criterios','fr_tipos':','.join(cr['tipos']),
            **{'fr_'+k: cr[k] for k in ('operacion','ciudad','ubicacion')}}
    assert client.post('/v0.6/fuentes',data=criterios).status_code==200
    assert verificar.await_args.args==(REFERENCIA,c['filtros'])
    bad=client.post('/v0.6/fuentes',data=criterios|{'fr_ubicacion':'inexistente'})
    assert bad.status_code==422 and 'URL filtrada' in bad.text
    edit=client.get('/v0.6/',params={'editar_fincaraiz':REFERENCIA})
    assert edit.status_code==200 and 'URL verificada' in edit.text
    for activa in ('0','1'):
        assert client.post('/v0.6/fuentes/estado',data={'fuente':'fincaraiz','id_busqueda':REFERENCIA,'activa':activa}).status_code==200
        assert servicio().listar_busquedas()[0]['activa']==(activa=='1')
    assert Path(store.path).read_bytes()==antes
    soup=BeautifulSoup(client.get('/v0.6/').text,'html.parser')
    assert len(soup.select('[data-dashboard-section]'))==4


@pytest.mark.parametrize('width,height', [(1440,900),(768,1024),(390,844)])
def test_chromium_formulario_foco_errores_y_ancho(tercera, chromium, servidor, width, height):
    page=chromium.new_page(viewport={'width':width,'height':height})
    try:
        page.goto(servidor+'/v0.6/');page.wait_for_load_state('networkidle')
        source=page.locator('[data-source-select]');source.select_option('fincaraiz')
        expect(page.locator('[data-fr-fields]')).to_be_visible()
        assert page.locator('input[name=url]').is_disabled()
        page.locator('input[name=nombre]').fill('Prueba visual')
        page.locator('input[name=fr_url]').fill(REFERENCIA)
        page.locator('input[name=fr_url]').focus();assert page.locator('input[name=fr_url]').evaluate('(e)=>e===document.activeElement')
        page.locator('[name=fr_modo]').select_option('criterios')
        page.get_by_role('button',name='Guardar fuente').click();page.wait_for_load_state('networkidle')
        expect(page.locator('#fuente-error')).to_contain_text('URL filtrada')
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        folder=Path('.tmp/fincaraiz-v09/screenshots');folder.mkdir(parents=True,exist_ok=True)
        page.screenshot(path=str(folder/f'form-{width}.png'),full_page=True)
    finally: page.close()

def test_tres_fuentes_mismo_codigo_y_catalogo_unico(tercera):
    from wasi.scraper import WasiStore
    datos, fr, c = tercera
    with fr.connect() as db:
        import json
        doc = json.loads(db.execute("SELECT data_json FROM properties WHERE id='123'").fetchone()[0])
    for fuente, store, key, url in (
        ('wasi', WasiStore(datos['ruta'].with_name('wasi.sqlite')), 'wasi:sintetica', 'wasi:123'),
        ('metrocuadrado', datos['store'], 'https://www.metrocuadrado.com/inmuebles/venta/bogota/test', 'https://www.metrocuadrado.com/inmueble/casa/123')):
        run = store.new_run(key, {'listing_currency': 'COP'})
        link = {'id': '123', 'url': url, 'raw': {'businessType': 'venta', 'mvalorventa': 101000000}}
        store.save_page(run, 1, '1', key, 'sintetica', [link], None)
        store.plan_incremental(run)
        d = copy.deepcopy(doc); d['normalized'].update(url=None if fuente == 'wasi' else url)
        store.result(run, '123', 'success', d)
    client = TestClient(app)
    assert client.get('/api/properties/123').status_code == 422
    ids = set()
    for fuente in ('metrocuadrado', 'wasi', 'fincaraiz'):
        response = client.get('/api/properties/' + fuente + ':123')
        assert response.status_code == 200 and response.json()['fuente'] == fuente
        ids.add(response.json()['id_interno'])
    assert len(ids) == 3 and len(servicio().listar()) == 29
    rows = list(csv.DictReader(io.StringIO(client.get('/v0.4/exportar.csv').text.lstrip('\ufeff')), delimiter=';'))
    assert {r['Fuente'] for r in rows} == {'metrocuadrado', 'wasi', 'fincaraiz'}
