"""Reubicación visual con snapshots y portales sintéticos; nunca captura real."""
from types import SimpleNamespace
from pathlib import Path
from fastapi.testclient import TestClient
from google.api_core.exceptions import PreconditionFailed
import pytest
from playwright.sync_api import expect
from metro.web import app
from metro.storage import Store
from consola.durable import WebDurable
from consola.ejecuciones import resumen_dashboard
from ejecuciones.control import now
from test_ejecuciones import execution


def test_resumen_prioriza_curso_y_nueva_y_muestra_estado_real(monkeypatch, tmp_path):
    rows = [dict(fuente='metrocuadrado',id_busqueda=str(i),nombre=f'Búsqueda {i}',activa=i!=3) for i in range(5)]
    doc={'runs':[{'id':'run','status':'running','created':now(),'updated':now(),
                 'searches':[dict(rows[0],status='running',started=now())]}]}
    monkeypatch.setattr('consola.ejecuciones._control_dashboard',lambda:doc)
    def previous(folder,b):
        if b['id_busqueda']=='1':
            return None,[]
        return {'status':'completed','started':f'2026-11-0{int(b["id_busqueda"])+1}T10:00:00+00:00'},[]
    monkeypatch.setattr('ejecuciones.mediciones.previous',previous)
    catalogo=SimpleNamespace(listar_busquedas=lambda:rows,busquedas=SimpleNamespace(ruta=tmp_path/'crm.sqlite'))
    recent,warning=resumen_dashboard(catalogo)
    assert [b['id_busqueda'] for b in recent]==['0','1','4']
    assert [b['estado'] for b in recent]==['En ejecución','Sin ejecutar','Completada']
    assert recent[0]['href'].endswith('?run=run') and warning is None
    doc['runs'][0]['updated']='2020-01-01T00:00:00+00:00'
    assert resumen_dashboard(catalogo)[0][0]['estado']=='Por verificar'


def test_formulario_de_radar_central_conserva_bloqueo_de_snapshot(tmp_path):
    called=[]
    def busy():
        called.append(True)
        raise PreconditionFailed('synthetic busy')
    c=TestClient(WebDurable(app,estado_factory=busy,data_dir=str(tmp_path)))
    response=c.get('/v0.6/ejecuciones/busquedas')
    assert response.status_code==503 and called==[True]
    assert 'Radar Central' in response.text


@pytest.mark.parametrize('width,height',[(1440,900),(768,1024),(390,844)])
def test_dashboard_radar_agregar_y_volver_sin_scraping(execution,chromium,width,height):
    from urllib.parse import urlsplit
    svc,_,_,factory,tmp=execution
    with factory() as state:
        state.cargar(tmp/'setup')
        Store(tmp/'setup'/'metro.sqlite')
        state.guardar(tmp/'setup')
    client=TestClient(WebDurable(app,estado_factory=factory,data_dir=str(tmp/'requests')))
    context=chromium.new_context(viewport={'width':width,'height':height})
    page=context.new_page()
    def request(route):
        req=route.request;url=urlsplit(req.url)
        response=client.request(req.method,url.path+('?' + url.query if url.query else ''),
            content=req.post_data_buffer,headers={k:v for k,v in req.headers.items() if k.lower() in {'origin','content-type'}},follow_redirects=False)
        # Chromium no vuelve a interceptar el destino de un redirect cumplido por route.fulfill.
        # El cliente ASGI sigue el 303 con el mismo snapshot sintético.
        if response.is_redirect:
            response=client.get(response.headers['location'],follow_redirects=True)
        route.fulfill(status=response.status_code,headers={k:v for k,v in response.headers.items() if k.lower() not in {'content-length','content-encoding'}},body=response.content)
    page.route('**/*',request)
    out=Path.cwd()/'.tmp'/'radar-central-visual';out.mkdir(parents=True,exist_ok=True)
    def screenshot(name):
        page.wait_for_load_state('networkidle')
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
        page.locator('h1').click()
        page.screenshot(path=str(out/f'{name}-{width}.png'),full_page=True)
    try:
        page.goto('http://127.0.0.1/v0.6/')
        assert page.locator('[data-dashboard-section]').count()==4
        expect(page.locator('[data-dashboard-section="radar-central"] h2')).to_have_text('Radar Central')
        assert page.locator('.source-form').count()==0
        assert page.locator('.radar-recent li').count()==2
        screenshot('dashboard')
        page.get_by_role('link',name='Abrir Radar Central').click()
        expect(page.get_by_role('heading',name='Radar Central',exact=True)).to_be_visible()
        screenshot('radar')
        page.get_by_role('link',name='Agregar búsquedas',exact=False).click()
        expect(page.get_by_role('heading',name='Agregar búsquedas',exact=True)).to_be_visible()
        page.locator('[name=nombre]').fill('Nueva para Radar Central')
        page.locator('[name=url]').fill('https://www.metrocuadrado.com/inmuebles/venta/bogota/centro')
        screenshot('formulario')
        page.get_by_role('button',name='Guardar fuente').click()
        expect(page.get_by_role('status')).to_contain_text('Fuente guardada')
        page.get_by_role('link',name='Volver a Radar Central').click()
        expect(page.locator('table')).to_contain_text('Nueva para Radar Central')
        assert not svc.cloud.launched
        page.get_by_role('link',name='Inicio',exact=True).click()
        expect(page.locator('.radar-recent')).to_contain_text('Nueva para Radar Central')
        assert page.locator('[data-dashboard-section]').count()==4
        assert not svc.cloud.launched
    finally:
        context.close()
