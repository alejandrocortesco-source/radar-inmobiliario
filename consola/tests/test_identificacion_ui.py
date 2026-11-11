"""Integración HTTP y Chromium con bases exclusivamente sintéticas."""
from copy import deepcopy
from pathlib import Path
import hashlib

from bs4 import BeautifulSoup
from fastapi.testclient import TestClient
import pytest

from metro.storage import Store
from metro.web import app, servicio
from oportunidades.servicio import servicio_oportunidades
from oportunidades.seguimiento import SeguimientoSQLite
from oportunidades.modelos import ClienteDatos, Necesidades
from catalogo.persistencia.asociaciones import AsociacionesSQLite
from test_browser import servidor


@pytest.fixture
def identidad_catalogo(escenario_consola):
    datos = escenario_consola
    for fuente in ('wasi','fincaraiz'):
        store = Store(datos['ruta'].with_name(fuente+'.sqlite'))
        url = 'https://example.test/'+fuente
        run = store.new_run(url, {'urls':[url]})
        link = {'id':'42', 'url':url+'/42', 'raw':{'mtiponegocio':'venta','mvalorventa':101000000}}
        store.save_page(run,1,'1',url,'synthetic',[link],None,search_url=url)
        store.plan_incremental(run)
        doc = deepcopy(datos['documentos']['1-M1'])
        doc['normalized'].update(url=url+'/42', operation='venta')
        if fuente=='wasi':
            doc['normalized']['zone']='Usaquén'
        store.result(run,'42','success',doc)
    return datos


def test_http_confirmacion_catalogo_matching_y_reversion(identidad_catalogo):
    client=TestClient(app)
    catalogo=servicio()
    s=servicio_oportunidades()
    repo=AsociacionesSQLite(s.repositorio.ruta)
    originales={p:hashlib.sha256(p.read_bytes()).hexdigest() for p in (identidad_catalogo['ruta'],identidad_catalogo['ruta'].with_name('wasi.sqlite'),identidad_catalogo['ruta'].with_name('fincaraiz.sqlite'))}
    items=catalogo.listar()
    a=next(i for i in items if i.origen.fuente=='metrocuadrado' and i.origen.id_original=='1-M1')
    b=next(i for i in items if i.origen.fuente=='wasi')
    assert b.barrio=='La Carolina' and b.geografia.estado=='confirmada'
    assert client.get('/v0.6/identificacion').status_code==200
    assert client.post('/v0.6/identificacion/analizar').status_code==200
    vista=client.get('/v0.6/identificacion').text
    assert 'Similitud' in vista and 'Sin datos comparables' in vista
    revision=repo.revisar(a.id_interno,b.id_interno,items)
    datos={'a':a.id_interno,'b':b.id_interno,'accion':'confirmado','firma':revision['firma']}
    assert client.post('/v0.6/identificacion/decision',data=datos).status_code==409
    datos['aceptar']='si'
    assert client.post('/v0.6/identificacion/decision',data=datos).status_code==200
    html=client.get('/v0.4/?fuente=wasi').text
    assert '2 publicaciones' in html
    api=client.get('/api/catalog?fuente=wasi').json()
    assert api['total']==1 and len(api['items'][0]['publicaciones'])==2
    csv=client.get('/v0.4/exportar.csv?fuente=wasi').text
    assert len(csv.strip().splitlines())==2
    csv=client.get('/v0.4/exportar.csv').text
    assert len(csv.strip().splitlines())==30  # 28 publicaciones, una oferta dual, más cabecera.
    dashboard=BeautifulSoup(client.get('/v0.6/').text,'html.parser')
    assert dashboard.select_one('.metric-total dd').text=='27'
    n=Necesidades(operacion='compra',tipo='casa',ciudad='Bogotá',barrios=['La Carolina'],presupuesto_max=101000000)
    o=s.capturar(ClienteDatos(nombre='Cliente sintético'),n)
    seguimiento=SeguimientoSQLite(s.repositorio.ruta)
    seguimiento.decision(o.id,a.id_interno,'descartado')
    seguimiento.decision(o.id,b.id_interno,'preseleccionado')
    respuesta=client.get('/v0.6/clientes/'+o.cliente_id)
    assert respuesta.status_code==200
    assert 'decisiones comerciales distintas' in respuesta.text
    informe=client.get('/api/oportunidades/'+o.id+'/diagnostico').json()
    assert informe['total_catalogo']==27 and informe['total_publicaciones']==28
    assert informe['total_resultados']==2
    historica=BeautifulSoup(client.get('/consola/?oportunidad='+o.id).text,'html.parser')
    assert historica.select_one('[data-match-total]').text=='27'
    assert 'sobre publicaciones' in historica.text
    revision=repo.revisar(a.id_interno,b.id_interno,catalogo.listar())
    datos.update(accion='deshacer',firma=revision['firma'])
    assert client.post('/v0.6/identificacion/decision',data=datos).status_code==200
    assert len(seguimiento.decisiones(o.id))==2
    assert not repo.miembros()
    assert all(hashlib.sha256(p.read_bytes()).hexdigest()==firma for p,firma in originales.items())


@pytest.mark.parametrize('ancho',[1440,768,390])
def test_revision_visual_responsive(identidad_catalogo,servidor,chromium,ancho):
    repo=AsociacionesSQLite(servicio_oportunidades().repositorio.ruta)
    repo.analizar(servicio().listar())
    context=chromium.new_context(viewport={'width':ancho,'height':900})
    page=context.new_page()
    page.goto(servidor+'/v0.6/identificacion')
    assert page.locator('h1').inner_text()=='¿Es el mismo inmueble?'
    assert page.locator('.identity-review').count()>0
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    page.keyboard.press('Tab')
    assert page.evaluate('document.activeElement.tagName')=='A'
    page.locator('.identity-review').first.locator('input[name=aceptar]').check()
    destino=Path('.tmp/identificacion-20261110/visual')
    destino.mkdir(parents=True,exist_ok=True)
    page.screenshot(path=str(destino/f'revision-{ancho}.png'),full_page=True)
    page.screenshot(path=str(destino/f'revision-viewport-{ancho}.png'))
    page.locator('.identity-review').first.get_by_role('button',name='Confirmar mismo inmueble').click()
    assert page.locator('button[value=deshacer]').count()>0
    context.close()


def test_integracion_postcaptura_y_fallo_no_revierte_catalogo(identidad_catalogo,monkeypatch):
    from oportunidades.automatizacion import despues_scraper
    from unittest.mock import Mock
    import oportunidades.automatizacion as automatico
    callback=Mock()
    monkeypatch.setattr(automatico,'recalcular_abiertas',callback)
    despues_scraper(identidad_catalogo['ruta'])
    repo=AsociacionesSQLite(servicio_oportunidades().repositorio.ruta)
    assert repo.ejecucion()['estado']=='correcto'
    assert len(repo.pares())>0
    total=len(servicio().listar())
    monkeypatch.setattr(AsociacionesSQLite,'analizar',Mock(side_effect=RuntimeError('fallo sintético')))
    despues_scraper(identidad_catalogo['ruta'])
    assert callback.call_count==2
    assert len(servicio().listar())==total


def test_wasi_localidad_contradictoria_no_infiere_barrio(identidad_catalogo):
    import json
    store=Store(identidad_catalogo['ruta'].with_name('wasi.sqlite'))
    with store.connect() as db:
        dato=json.loads(db.execute("SELECT data_json FROM properties WHERE id='42'").fetchone()[0])
        dato['normalized']['zone']='Chapinero'
        db.execute("UPDATE properties SET data_json=? WHERE id='42'",(json.dumps(dato),))
    i=next(i for i in servicio().listar() if i.origen.fuente=='wasi')
    assert i.barrio is None and i.geografia.estado=='pendiente'
