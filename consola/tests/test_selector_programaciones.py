"""Selector real sobre registro auxiliar sintético y APIs cloud simuladas."""
import json
from urllib.parse import urlsplit
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from playwright.sync_api import expect
from test_ejecuciones import execution, run_manual, fake_scrapers
from test_calendarios import multi, values, arm, deliver
from selector_fixtures import seed_searches
from ejecuciones.calendarios import Calendarios, FieldError
from catalogo.persistencia.busquedas import BusquedasSQLite
from metro.web import app

URL='/v0.6/ejecuciones/programaciones'

@pytest.fixture
def selector(multi,execution,monkeypatch):
    with execution[3]() as state:
        state.cargar(execution[4]/'selector-seed')
        seed_searches(BusquedasSQLite(execution[4]/'selector-seed'/'metro-consola.sqlite'))
        state.guardar(execution[4]/'selector-seed')
    multi.service.overview(refresh=True)
    monkeypatch.setenv('RADAR_SCHEDULE_TARGET','https://synthetic.run.app')
    monkeypatch.setattr('ejecuciones.scheduler.Scheduler',lambda:multi.scheduler)
    return multi,execution,TestClient(app)


def body(keys,**kw):
    return dict(name='Combinada',frequency='daily',hour='9',minute='0',schedule_search=[json.dumps(k) for k in keys],action='create') | kw


def test_groups_empty_portals_and_no_placeholder_searches(multi,monkeypatch):
    monkeypatch.setenv('RADAR_SCHEDULE_TARGET','https://synthetic.run.app')
    monkeypatch.setattr('ejecuciones.scheduler.Scheduler',lambda:multi.scheduler)
    text=TestClient(app).get(URL+'?nuevo=1').text
    assert all('data-source="'+s+'"' in text for s in ['metrocuadrado','wasi','fincaraiz'])
    assert text.count('Sin búsquedas configuradas')==2 and 'Fincaraíz' in text
    assert 'https://synthetic.invalid' not in text


def test_http_cross_portal_selection_edit_restart_and_empty_guard(selector):
    multi,execution,client=selector
    keys=[['metrocuadrado','compartida'],['wasi','compartida'],['fincaraiz','segunda']]
    assert client.post(URL,data=body(keys)).status_code==200
    plan=next(iter(multi.control.read()[0]['schedules'].values()))
    assert plan['keys']==keys
    assert client.post(URL,data=body([['wasi','segunda'],['fincaraiz','compartida']],action='edit',id=plan['id'],revision=plan['revision'])).status_code==200
    stored=Calendarios(multi.service,multi.scheduler).control.read()[0]['schedules'][plan['id']]
    assert stored['keys']==[['wasi','segunda'],['fincaraiz','compartida']]
    for active in [False,True]:
        invalid=client.post(URL,data=body([],enabled='on' if active else ''))
        assert invalid.status_code==422 and 'Selecciona' in invalid.text
    multi.control.change(lambda d:d['schedules'][plan['id']].update(keys=[]))
    with pytest.raises(FieldError):multi.change('activate',plan['id'],expected=stored['revision'])
    assert not multi.service.cloud.launched


def test_only_selected_portal_searches_processed(selector):
    multi,execution,client=selector
    keys=[['metrocuadrado','compartida'],['wasi','compartida'],['fincaraiz','segunda']]
    plan=multi.change('create',values=values(keys=keys))
    tick=arm(multi,[plan['id']]);run=deliver(multi,tick)['occurrences'][0]
    seen=[];fake=fake_scrapers(['completed']*3,[])
    def factory(repo,folder,b):
        seen.append((b['fuente'],b['id_busqueda']))
        return fake(repo,folder,b)
    assert run_manual(execution[4]/'worker-selector',run['id'],multi.control,execution[3],factory,heartbeat=.001)
    assert seen==[tuple(k) for k in keys]
    assert multi.control.get(run['id'])['persisted']


def test_inactive_and_deleted_preserved_until_explicit_removal(selector):
    multi,execution,client=selector
    plan=multi.change('create',values=values(keys=[['wasi','compartida'],['fincaraiz','segunda']]))
    with execution[3]() as state:
        state.cargar(execution[4]/'changed')
        repo=BusquedasSQLite(execution[4]/'changed'/'metro-consola.sqlite')
        repo.cambiar_estado('wasi','compartida',False);repo.eliminar('fincaraiz','segunda');state.guardar(execution[4]/'changed')
    text=client.get(URL+'?editar='+plan['id']).text
    assert 'Retírala de la selección para guardar' in text and 'Búsqueda eliminada' in text
    assert multi.control.read()[0]['schedules'][plan['id']]['keys']==plan['keys']
    assert client.post(URL,data=body(plan['keys'],action='edit',id=plan['id'],revision=plan['revision'])).status_code==422
    assert client.post(URL,data=body([['wasi','segunda']],action='edit',id=plan['id'],revision=plan['revision'])).status_code==200


@pytest.mark.parametrize('viewport',[(1440,900),(768,1024),(390,844)])
def test_browser_groups_all_clear_persist_and_counter(selector,chromium,viewport):
    multi,execution,client=selector
    ctx=chromium.new_context(viewport=dict(width=viewport[0],height=viewport[1]));page=ctx.new_page();page.set_default_timeout(8000)
    def routed(route):
        req=route.request;u=urlsplit(req.url)
        res=client.request(req.method,u.path+('?' + u.query if u.query else ''),content=req.post_data_buffer)
        route.fulfill(status=res.status_code,headers={k:v for k,v in res.headers.items() if k.lower() not in {'content-length','content-encoding'}},body=res.content)
    page.route('**/*',routed);page.goto('http://127.0.0.1'+URL+'?nuevo=1')
    assert page.locator('.search-source').count()==3
    assert [page.locator('[data-source="'+s+'"] input').count() for s in ['metrocuadrado','wasi','fincaraiz']]==[4,3,2]
    page.get_by_label('Nombre',exact=True).fill('Selección por portal')
    page.get_by_label('Frecuencia',exact=True).select_option('daily')
    page.get_by_role('button',name='Seleccionar todas',exact=True).click()
    expect(page.locator('[data-search-count]')).to_have_text('8 búsquedas seleccionadas')
    assert not page.locator('[data-source="wasi"] input:disabled').is_checked()
    page.get_by_role('button',name='Limpiar selección',exact=True).click()
    expect(page.locator('[data-search-count]')).to_have_text('0 búsquedas seleccionadas')
    expect(page.locator('[data-field-error="keys"]')).not_to_be_empty()
    expect(page.get_by_role('button',name='Guardar programación',exact=True)).to_be_disabled()
    page.get_by_label('Wasi · compartida',exact=True).check()
    page.get_by_label('Wasi · segunda',exact=True).check()
    page.get_by_label('Fincaraíz · compartida',exact=True).check()
    expect(page.locator('[data-search-count]')).to_have_text('3 búsquedas seleccionadas')
    page.get_by_role('button',name='Guardar programación',exact=True).click()
    expect(page.get_by_text('Configuración guardada. No se inició scraping.',exact=True)).to_be_visible()
    page.get_by_role('link',name='Editar',exact=True).click()
    expect(page.get_by_label('Wasi · compartida',exact=True)).to_be_checked()
    expect(page.get_by_label('Fincaraíz · compartida',exact=True)).to_be_checked()
    expect(page.get_by_label('Metrocuadrado · compartida',exact=True)).not_to_be_checked()
    expect(page.locator('[data-search-count]')).to_have_text('3 búsquedas seleccionadas')
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    out=Path('.tmp/selector-20261116');out.mkdir(exist_ok=True,parents=True)
    page.screenshot(path=str(out/f'selector-{viewport[0]}.png'),full_page=True)
    assert not multi.service.cloud.launched
    ctx.close()


@pytest.mark.parametrize('frequency',['daily','weekly'])
def test_empty_selection_error_belongs_to_search_field(selector,frequency):
    multi,execution,client=selector
    response=client.post(URL,data=body([],frequency=frequency))
    assert response.status_code==422
    assert '<p id="error-keys" class="field-error" data-field-error="keys">Selecciona al menos una búsqueda activa.</p>' in response.text
    assert not multi.service.cloud.launched
