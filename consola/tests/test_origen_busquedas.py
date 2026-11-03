"""Fecha global y nombres elegidos por la usuaria, sin cambiar la geografía."""
import csv
import io
from bs4 import BeautifulSoup
from fastapi.testclient import TestClient
from metro.web import app, servicio
from catalogo.persistencia.busquedas import BusquedasSQLite
from catalogo.servicio import ServicioCatalogo
from catalogo.modelos import Inmueble, Origen, PresenciaBusqueda
from conftest import A, B
from test_browser import servidor
from playwright.sync_api import expect
import pytest


def test_fecha_exitosa_global_no_depende_de_filtros(escenario_consola):
    store = escenario_consola['store']; c = TestClient(app)
    assert 'Sin actualización exitosa registrada' in c.get('/v0.4/').text
    store.update_run(escenario_consola['run'], status='completed', finished='2026-11-03T16:11:51+00:00')
    other = store.new_run(A, {})
    store.update_run(other, status='failed', finished='2026-11-04T18:00:00+00:00')
    for route in ['/v0.4/','/v0.4/?categoria=cambio_precio&texto=sin-resultados','/consola/?limit=12&offset=12']:
        soup = BeautifulSoup(c.get(route).text,'html.parser')
        assert soup.select_one('[data-catalog-update] time').text == '03/11/2026 · 11:11'
    store.update_run(other,status='completed',finished='2026-11-04T18:00:00+00:00')
    assert '04/11/2026 · 13:00' in c.get('/v0.4/').text


def test_guardar_renombrar_varias_busquedas_ficha_csv_y_persistencia(escenario_consola):
    data = escenario_consola; c = TestClient(app)
    before = data['ruta'].read_bytes()
    old = servicio().listar()
    for url, name in [(A+'/?utm_source=prueba','En la Carolina'),(B,'Zona Country Club')]:
        response = c.post('/v0.4/busquedas', data={'fuente':'metrocuadrado','url':url,'nombre':name,'volver':'/v0.4/?limit=12'},follow_redirects=False)
        assert response.status_code == 303
        assert response.headers['location'] == '/v0.4/?limit=12#busquedas-origen'
    page = BeautifulSoup(c.get('/v0.4/?texto=Casa+con+jard%C3%ADn+01').text,'html.parser')
    names = page.select('tbody .origin-searches li')
    assert len(names) == 2
    assert {li.a.text.removesuffix(' ↗') for li in names} == {'En la Carolina','Zona Country Club'}
    link = page.select_one('.property-link')['href']
    detail = BeautifulSoup(c.get(link).text,'html.parser')
    assert 'En la Carolina' in detail.select_one('.metadata .origin-searches').text
    exported = c.get('/v0.4/exportar.csv?texto=Casa+con+jard%C3%ADn+01')
    rows = list(csv.DictReader(io.StringIO(exported.content.decode('utf-8-sig')),delimiter=';'))
    assert all('En la Carolina' in row['Búsquedas de origen'] and 'Zona Country Club' in row['Búsquedas de origen'] for row in rows)
    assert c.post('/v0.4/busquedas',data={'fuente':'metrocuadrado','url':A,'nombre':'Carolina revisada'}).status_code == 200
    fresh = servicio().listar()
    assert any(p.nombre == 'Carolina revisada' for i in fresh for p in i.origen.busquedas)
    assert [(i.id_interno,i.barrio,i.zona,i.geografia) for i in old] == [(i.id_interno,i.barrio,i.zona,i.geografia) for i in fresh]
    assert data['ruta'].read_bytes() == before
    assert len(servicio().listar_busquedas()) == 2


@pytest.mark.parametrize('source,url,name', [('metrocuadrado','javascript:alert(1)','Nombre'),('metrocuadrado','https://otro.test/','Nombre'),('metrocuadrado',A,''),('metrocuadrado',A,'x'*121)])
def test_registro_invalido_no_escribe(escenario_consola,source,url,name):
    c = TestClient(app)
    assert c.post('/v0.4/busquedas',data={'fuente':source,'url':url,'nombre':name}).status_code == 422
    assert servicio().listar_busquedas() == ()


def test_futuras_fuentes_separadas_y_lectura_no_crea_archivos(tmp_path):
    repo = BusquedasSQLite(tmp_path/'nombres.sqlite')
    assert repo.listar() == () and not repo.ruta.exists()
    class Catalogo:
        def listar(self):
            return tuple(Inmueble(origen=Origen(fuente=f,id_original='1',busquedas=(PresenciaBusqueda(id_busqueda='https://busqueda.test/s',url='https://busqueda.test/s'),))) for f in ['fuente_a','fuente_b'])
    s = ServicioCatalogo(Catalogo(),busquedas=repo)
    s.guardar_busqueda('fuente_a','https://busqueda.test/s','Zona Country Club')
    assert [i.origen.busquedas[0].nombre for i in s.listar()] == ['Zona Country Club',None]
    assert len(ServicioCatalogo(Catalogo(),busquedas=BusquedasSQLite(repo.ruta)).listar_busquedas()) == 1


def test_configuracion_auxiliar_invalida_no_escribe_catalogo(escenario_consola, monkeypatch):
    ruta = escenario_consola['ruta']; antes = ruta.read_bytes()
    monkeypatch.setenv('RADAR_CRM_DB', str(ruta))
    c = TestClient(app)
    assert c.get('/v0.4/').status_code == 200
    assert c.post('/v0.4/busquedas',data={'fuente':'metrocuadrado','url':A,'nombre':'En la Carolina'}).status_code == 503
    assert ruta.read_bytes() == antes


@pytest.mark.parametrize('width,javascript',[(1440,True),(390,True),(390,False)])
def test_mon_puede_nombrar_busqueda_y_registrar_url(servidor,chromium,width,javascript):
    context = chromium.new_context(viewport={'width':width,'height':900}, java_script_enabled=javascript)
    page = context.new_page();page.goto(servidor+'/v0.4/')
    page.locator('#busquedas-origen > summary').click()
    form = page.locator('.search-name-form').first
    form.locator('[name=nombre]').fill('En la Carolina')
    form.get_by_role('button',name='Guardar nombre').click()
    expect(page.locator('tbody .origin-searches').first).to_contain_text('En la Carolina')
    page.locator('#busquedas-origen > summary').click()
    page.get_by_text('Registrar otra URL con nombre',exact=True).click()
    page.locator('[data-new-search] [name=url]').fill('https://www.metrocuadrado.com/inmuebles/venta/bogota/country-club')
    page.locator('[data-new-search] [name=nombre]').fill('Zona Country Club')
    page.get_by_role('button',name='Guardar búsqueda',exact=True).click()
    page.locator('#busquedas-origen > summary').click()
    expect(page.locator('.search-name-form input[value="Zona Country Club"]')).to_have_count(1)
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    context.close()
