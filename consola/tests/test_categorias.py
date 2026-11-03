"""Clasificaciones persistidas, última ejecución por búsqueda y UX progresivo."""
from dataclasses import replace
from bs4 import BeautifulSoup
from fastapi.testclient import TestClient
from metro.web import app, servicio
from catalogo.consultas import contar_categorias, seleccionar
from catalogo.filtros import FiltrosCatalogo
from catalogo.modelos import CategoriaActualizacion as C, Inmueble, Origen, PresenciaBusqueda
from test_browser import servidor
from playwright.sync_api import expect
from urllib.parse import unquote
import pytest


def counts(response):
    soup = BeautifulSoup(response.text, 'html.parser')
    return {a['data-category']: int(a.span.text) for a in soup.select('[data-category]')}


def completed(data):
    data['store'].update_run(data['run'], status='completed')


def test_conteos_filtrado_paginacion_exportacion_y_no_escritura(escenario_consola):
    data = escenario_consola
    completed(data)
    c = TestClient(app)
    before = data['ruta'].read_bytes()
    expected = {'todos': 26, 'nuevos': 26, 'cambio_precio': 0, 'revision_conservadora': 0}
    assert counts(c.get('/v0.4/')) == expected
    response = c.get('/v0.4/?categoria=nuevos&ciudad=Bogot%C3%A1&limit=12&offset=12')
    assert counts(response) == dict(expected, todos=13, nuevos=13)
    soup = BeautifulSoup(response.text, 'html.parser')
    assert len(soup.select('tbody tr')) == 1
    assert 'categoria=nuevos' in unquote(soup.select_one('.property-link')['href'])
    assert soup.select_one('[data-category=nuevos]')['aria-current'] == 'true'
    assert all('offset=0' in a['href'] for a in soup.select('[data-category]'))
    assert counts(c.get('/v0.4/?categoria=nuevos&texto=Casa+con+jard%C3%ADn+01')) == dict(expected, todos=1, nuevos=1)
    price = c.get('/v0.4/?categoria=nuevos&operacion=venta&moneda=COP&precio_max=103000000&orden=precio_desc')
    assert counts(price) == dict(expected, todos=3, nuevos=3)
    assert len(BeautifulSoup(price.text, 'html.parser').select('tbody tr')) == 3
    empty = c.get('/v0.4/?categoria=revision_conservadora')
    assert 'No hay inmuebles en esta categoría' in empty.text
    assert c.get('/v0.4/exportar.csv?categoria=cambio_precio').text.count('\n') == 1
    assert c.get('/v0.4/?categoria=incorrecta').status_code == 422
    assert c.get('/api/catalog?categoria=nuevos').json()['total'] == 26
    assert data['ruta'].read_bytes() == before


def test_ultima_exitosa_por_busqueda_solapamiento_e_historial(escenario_consola):
    data = escenario_consola; store = data['store']; completed(data)
    from conftest import A
    r = store.new_run(A, {'urls': [A], 'listing_currency': 'COP'})
    link = {'id': '1-M1', 'url': 'https://www.metrocuadrado.com/inmueble/1-M1',
            'raw': {'mtiponegocio': 'venta', 'mvalorventa': 99000000}}
    store.save_page(r, 1, '1', A, 'updated', [link], None, search_url=A)
    store.plan_incremental(r)
    # Revisión y cambio pueden coexistir; ambas son evidencia persistida.
    with store.connect() as db:
        db.execute("UPDATE jobs SET classification='review' WHERE run_id=?", (r,))
    c = TestClient(app)
    for status in ['running', 'incomplete', 'failed', 'interrupted', 'blocked']:
        store.update_run(r, status=status)
        assert counts(c.get('/v0.4/'))['nuevos'] == 26
    store.update_run(r, status='completed')
    global_counts = counts(c.get('/v0.4/'))
    # B conserva su última ejecución: el primer inmueble sigue siendo nuevo allí.
    assert global_counts == {'todos':26, 'nuevos':1, 'cambio_precio':1, 'revision_conservadora':1}
    scoped = counts(c.get('/v0.4/', params={'fuente':'metrocuadrado','id_busqueda':A}))
    assert scoped == dict(global_counts, nuevos=0)
    items = servicio().listar()
    assert len(items) == len({i.id_interno for i in items}) == 26
    with store.connect() as db:
        history = [tuple(row) for row in db.execute('SELECT * FROM price_changes')]
        jobs = [tuple(row) for row in db.execute('SELECT * FROM jobs')]
    # Una ejecución completa vacía reinicia las categorías de A sin borrar evidencia.
    empty = store.new_run(A, {'urls':[A]}); store.update_run(empty, status='completed')
    assert counts(c.get('/v0.4/')) == dict(global_counts, cambio_precio=0, revision_conservadora=0)
    with store.connect() as db:
        assert history == [tuple(row) for row in db.execute('SELECT * FROM price_changes')]
        assert jobs == [tuple(row) for row in db.execute('SELECT * FROM jobs')]


def test_categorias_independientes_de_fuente_y_uuid_unico():
    a = Inmueble(origen=Origen(fuente='otro', id_original='1', busquedas=(
        PresenciaBusqueda(id_busqueda='s', categorias_actualizacion=(C.NUEVOS, C.CAMBIO_PRECIO)),)))
    b = replace(a, origen=replace(a.origen, fuente='metrocuadrado'))
    filtros = FiltrosCatalogo(categoria=C.NUEVOS)
    assert contar_categorias([a,a,b], filtros) == {'todos':2,'nuevos':2,'cambio_precio':2,'revision_conservadora':0}
    assert seleccionar([a,a,b], replace(filtros, fuente='otro')) == [a]


@pytest.mark.parametrize('width,javascript', [(1440,True),(390,True),(390,False)])
def test_filtros_browser(servidor, chromium, escenario_consola, width, javascript):
    completed(escenario_consola)
    context = chromium.new_context(viewport={'width':width,'height':900}, java_script_enabled=javascript)
    page = context.new_page()
    page.goto(servidor+'/v0.4/?ciudad=Bogot%C3%A1&limit=12&offset=12')
    if javascript: page.evaluate('window.pruebaSinRecarga = 42')
    page.locator('[data-category=nuevos]').click()
    expect(page.locator('tbody tr')).to_have_count(12)
    expect(page.locator('[data-category=nuevos]')).to_have_attribute('aria-current','true')
    assert 'offset=0' in page.url
    page.locator('[data-filters] > summary').click()
    # El panel general no debe tapar los accesos rápidos, ni siquiera en móvil.
    assert page.locator('.category-heading').inner_text() == 'Categorías de actualización'
    assert page.evaluate("""[...document.querySelectorAll('[data-category]')].every(a => {
        const r = a.getBoundingClientRect();
        return a.contains(document.elementFromPoint(r.x + r.width/2, r.y + r.height/2));
    })""")
    page.locator('[data-filters] > summary').click()
    if javascript:
        assert page.evaluate('window.pruebaSinRecarga') == 42
        page.locator('[data-auto-submit]').select_option('24')
        expect(page.locator('tbody tr')).to_have_count(13)
    page.locator('[data-category=cambio_precio]').click()
    expect(page.locator('.empty-state')).to_contain_text('No hay inmuebles en esta categoría')
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    page.locator('[data-category=todos]').click()
    expect(page.locator('tbody tr')).to_have_count(13 if javascript else 12)
    if javascript:
        page.go_back()
        expect(page.locator('.empty-state')).to_be_visible()
        # Una red fallida en fetch conserva la navegación GET como alternativa.
        page.route('**/v0.4/?**', lambda route: route.abort() if route.request.resource_type == 'fetch' else route.continue_())
        page.locator('[data-category=todos]').click()
        expect(page.locator('tbody tr')).to_have_count(13)
    context.close()
