"""Ambas fuentes en servicios, matching, exportación y UI con datos sintéticos."""
import copy
import csv
import io
import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from bs4 import BeautifulSoup
from fastapi.testclient import TestClient
from playwright.sync_api import expect

from catalogo.fuentes.wasi import configurar, identidad, opciones_iniciales
from catalogo.identidad import identificar_inmueble
from catalogo.filtros import FiltrosCatalogo
from catalogo.modelos import Operacion
from metro.web import app, servicio
from wasi.scraper import WasiStore
from oportunidades.modelos import ClienteDatos
from oportunidades.servicio import servicio_oportunidades
from oportunidades.seguimiento import SeguimientoSQLite
from oportunidades.automatizacion import despues_scraper
from test_v03 import necesidades
from test_browser import servidor

FILTROS={'fuente':'wasi','nombre':'Wasi sintética','id_pais':'1','id_dpto':'15','id_ciudad':'794','id_localidad':'1','business_type_id':'1'}


@pytest.fixture
def ambas(escenario_consola, monkeypatch):
    datos=escenario_consola
    ruta=datos['ruta'].with_name('wasi.sqlite')
    monkeypatch.setenv('WASI_DB',str(ruta))
    config=configurar(FILTROS,opciones_iniciales());key=identidad(config)
    store=WasiStore(ruta)
    run=store.new_run(key,{'urls':[key],'listing_currency':'COP','searches':{key:config}})
    link={'id':'001','url':'wasi:001','raw':{'businessType':'venta','mvalorventa':101_000_000,'currency':'COP'}}
    store.save_page(run,1,'1','https://wasi.co/usuario/inmuebles/red','page',[link],None,search_url=key)
    store.plan_incremental(run)
    doc=copy.deepcopy(datos['documentos']['2-M2'])
    doc['normalized'].update(id='001',url=None,title='Casa Wasi sintética',price=101_000_000,advertiser='Empresa sintética',
                            phone='+573001234567',whatsapp='https://wa.me/573001234567',bathrooms=None,private_area=None)
    doc['fields']={'bathrooms':{'status':'absent'},'private_area':{'status':'error'}}
    store.result(run,'001','success',doc)
    store.update_search(run,key,complete=True)
    store.update_run(run,status='completed',finished='2026-11-08T05:00:00+00:00')
    # Un código idéntico en Metrocuadrado no colisiona ni fusiona anuncios físicos.
    m=datos['store'];mr=m.new_run('https://www.metrocuadrado.com/inmuebles/venta/bogota/test',{})
    ml={'id':'001','url':'https://www.metrocuadrado.com/inmueble/casa/001','raw':{'mtiponegocio':'venta','mvalorventa':101_000_000}}
    m.save_page(mr,1,'1','https://www.metrocuadrado.com/inmuebles/venta/bogota/test','page',[ml],None)
    md=copy.deepcopy(doc);md['normalized'].update(title='Casa Metro sintética',url=ml['url'],phone='6011234567')
    m.result(mr,'001','success',md)
    return datos,store,key


def test_catalogo_unico_identidad_api_filtros_y_csv(ambas):
    datos,store,key=ambas
    originales=(datos['ruta'].read_bytes(),Path(store.path).read_bytes())
    s=servicio(); assert len(s.listar())==28
    assert identificar_inmueble('wasi','001') != identificar_inmueble('metrocuadrado','001')
    assert len(s.consultar(FiltrosCatalogo(fuente='wasi'))['items'])==1
    client=TestClient(app)
    assert client.get('/api/properties/001').status_code==422
    for fuente in ('wasi','metrocuadrado'):
        iid=identificar_inmueble(fuente,'001')
        assert client.get('/api/properties/'+iid).json()['fuente']==fuente
        assert client.get('/api/properties/'+fuente+':001').json()['id_interno']==iid
    assert client.get('/api/catalog',params={'search_url':key}).json()['total']==1
    assert client.get('/api/catalog',params={'fuente':'wasi','operacion':'venta','precio_max':101000000}).json()['total']==1
    rows=list(csv.DictReader(io.StringIO(client.get('/v0.4/exportar.csv').text.lstrip('\ufeff')),delimiter=';'))
    # La publicación dual histórica se exporta una fila por oferta.
    assert len(rows)==29 and {r['Fuente'] for r in rows}=={'metrocuadrado','wasi'}
    i=s.obtener(identificar_inmueble('wasi','001'))
    assert i.origen.url is None and i.banos is None
    page=client.get('/v0.4/inmuebles/'+i.id_interno)
    assert 'Información no disponible en esta fuente' in page.text and 'Pendiente por error de captura' in page.text
    panel=client.get('/consola/anunciante',params={'inmueble':i.id_interno})
    assert panel.status_code==200 and '6011234567' in panel.text and '573001234567' in panel.text
    dashboard=BeautifulSoup(client.get('/v0.6/').text,'html.parser')
    assert dashboard.select_one('.metric-total dd').text=='28'
    assert len(dashboard.select('[data-dashboard-section]'))==4
    assert datos['ruta'].read_bytes()==originales[0]
    assert Path(store.path).read_bytes()==originales[1]


def test_matching_y_decisiones_independientes_con_ambas_fuentes(ambas,monkeypatch):
    datos,store,key=ambas
    s=servicio_oportunidades()
    o=s.capturar(ClienteDatos(nombre='Cliente sintético'),necesidades())
    despues_scraper(datos['ruta'])
    resultados=s.coincidencias(o.id,servicio())
    ids={r.inmueble.id_interno for r in resultados}
    wasi=identificar_inmueble('wasi','001');metro=identificar_inmueble('metrocuadrado','001')
    assert {wasi,metro} <= ids
    seguimiento=SeguimientoSQLite(s.repositorio.ruta)
    seguimiento.decision(o.id,wasi,'preseleccionado')
    seguimiento.decision(o.id,metro,'descartado')
    despues_scraper(datos['ruta'])
    assert seguimiento.decisiones(o.id)[wasi]['estado']=='preseleccionado'
    assert seguimiento.decisiones(o.id)[metro]['estado']=='descartado'
    antes=Path(store.path).read_bytes()
    monkeypatch.setenv('RADAR_CRM_DB',store.path)
    with pytest.raises(ValueError):
        despues_scraper(datos['ruta'])
    assert Path(store.path).read_bytes()==antes


def test_guardar_editar_filtros_dependientes_no_captura(escenario_consola):
    client=TestClient(app); antes=escenario_consola['ruta'].read_bytes()
    assert client.post('/v0.6/fuentes',data=FILTROS|{'title':'La Carolina'}).status_code==200
    registro=servicio().listar_busquedas()[0]
    key=registro['id_busqueda']
    assert servicio().busquedas.configuracion_wasi(key)['filtros']['title']=='La Carolina'
    assert client.get('/v0.6/',params={'editar_wasi':key}).status_code==200
    editado=FILTROS|{'id_zona':'137161','reemplazar':key}
    assert client.post('/v0.6/fuentes',data=editado).status_code==200
    assert len(servicio().listar_busquedas())==1
    assert servicio().busquedas.configuracion_wasi(key)
    assert client.post('/v0.6/fuentes',data=FILTROS|{'id_localidad':''}).status_code==422
    assert client.post('/v0.6/fuentes',data=FILTROS|{'id_localidad':'2','id_zona':'137161'}).status_code==422
    assert escenario_consola['ruta'].read_bytes()==antes
    assert not escenario_consola['ruta'].with_name('wasi.sqlite').exists()


def test_actualizar_opciones_es_accion_separada_sin_capturas(escenario_consola,monkeypatch):
    import wasi.options
    from wasi.auth import AuthBlocked
    actualizar=AsyncMock(return_value={'opciones_actualizadas':3,'capturas':0})
    monkeypatch.setattr(wasi.options,'actualizar_opciones',actualizar)
    client=TestClient(app)
    assert client.post('/v0.6/fuentes/wasi/opciones',data=FILTROS).status_code==200
    assert actualizar.await_count==1
    assert servicio().listar_busquedas()==()
    assert not escenario_consola['ruta'].with_name('wasi.sqlite').exists()
    actualizar.side_effect=AuthBlocked('auth_failed')
    r=client.post('/v0.6/fuentes/wasi/opciones',data=FILTROS)
    assert r.status_code==503 and 'No se pudieron actualizar' in r.text


@pytest.mark.parametrize('width,javascript',[(1440,True),(768,True),(390,True),(390,False)])
def test_formulario_wasi_responsivo_dependiente_y_sin_js(servidor,chromium,tmp_path,width,javascript):
    context=chromium.new_context(viewport={'width':width,'height':900},java_script_enabled=javascript)
    page=context.new_page()
    try:
        page.goto(servidor+'/v0.6/')
        page.locator('[name=fuente]').select_option('wasi')
        if not javascript:
            page.get_by_role('button',name='Actualizar formulario').click()
        expect(page.locator('[name=id_ciudad]')).to_be_visible()
        page.locator('[name=nombre]').fill('Búsqueda Wasi sintética')
        page.locator('[name=id_ciudad]').select_option('794')
        if not javascript:
            page.get_by_role('button',name='Actualizar formulario').click()
        page.locator('[name=id_localidad]').select_option('1')
        if not javascript:
            page.get_by_role('button',name='Actualizar formulario').click()
        page.locator('[name=id_zona]').select_option('137161')
        page.locator('[name=business_type_id]').select_option('1')
        page.locator('[name=title]').fill('La Carolina')
        page.get_by_role('button',name='Guardar fuente').focus()
        assert page.evaluate("document.activeElement.textContent.includes('Guardar fuente')")
        page.get_by_role('button',name='Guardar fuente').click()
        expect(page.locator('[data-registered-source]')).to_have_count(1)
        assert page.locator('[data-dashboard-section]').count()==4
        page.wait_for_load_state('load')
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
        page.locator('[data-registered-source] a',has_text='Editar filtros').click()
        expect(page.locator('[name=id_zona]')).to_have_value('137161')
        page.locator('[name=id_localidad]').select_option('2')
        if javascript:
            expect(page.locator('[name=id_zona]')).to_have_value('')
        else:
            page.get_by_role('button',name='Actualizar formulario').click()
        assert page.locator('[name=id_zona] option[value="137161"]').count()==0
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
        page.screenshot(path=str(tmp_path/f'wasi-form-{width}-{javascript}.png'),full_page=True)
    finally:
        context.close()
