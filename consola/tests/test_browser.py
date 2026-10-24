"""Navegación real en Chromium sobre el mismo FastAPI y datos sintéticos."""

import os
import socket
import subprocess
import sys
import time
from urllib.request import urlopen

import pytest
from playwright.sync_api import sync_playwright, expect
from catalogo.identidad import identificar_inmueble


@pytest.fixture(scope='session')
def chromium():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        yield browser
        browser.close()


@pytest.fixture
def servidor(escenario_consola, tmp_path):
    datos = escenario_consola
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    url = f'http://127.0.0.1:{port}'
    entorno = dict(os.environ, METRO_DB=str(datos['ruta']),
                   PYTHONPATH=os.pathsep.join((str(datos['raiz']), str(datos['raiz'] / 'scraper'))))
    with (tmp_path / 'servidor.log').open('w', encoding='utf-8') as log:
        proceso = subprocess.Popen(
            [sys.executable, '-m', 'uvicorn', 'metro.web:app', '--host', '127.0.0.1',
             '--port', str(port), '--log-level', 'warning'],
            cwd=datos['raiz'], env=entorno, stdout=log, stderr=log,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
        )
        try:
            limite = time.monotonic() + 15
            while time.monotonic() < limite:
                if proceso.poll() is not None:
                    pytest.fail('El servidor de prueba terminó; revisar servidor.log')
                try:
                    with urlopen(url + '/health', timeout=1) as respuesta:
                        if respuesta.status == 200:
                            break
                except OSError:
                    time.sleep(.1)
            else:
                pytest.fail('El servidor de prueba no inició')
            yield url
        finally:
            proceso.terminate()
            try:
                proceso.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proceso.kill()
                proceso.wait(timeout=5)


@pytest.fixture
def pagina(chromium):
    contexto = chromium.new_context(viewport={'width': 1440, 'height': 1000},
                                    reduced_motion='reduce')
    def imagen(route):
        if route.request.url.endswith('rota.jpg'):
            route.abort()
        else:
            color = '#d8e0cc' if route.request.url.endswith('uno.jpg') else '#c9d5db'
            route.fulfill(content_type='image/svg+xml', body=(
                f'<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="800">'
                f'<rect width="1200" height="800" fill="{color}"/></svg>'))
    contexto.route('https://images.test/**', imagen)
    page = contexto.new_page()
    errores = []
    page.on('pageerror', lambda exc: errores.append(str(exc)))
    yield page
    contexto.close()
    assert not errores


def test_navegacion_paginacion_y_regreso(pagina, servidor):
    pagina.goto(servidor + '/consola/?orden=id&limit=2')
    expect(pagina.locator('.property-card')).to_have_count(2)
    expect(pagina.locator('[data-total]')).to_have_text('26')
    pagina.get_by_role('link', name='Siguiente →').click()
    expect(pagina).to_have_url(__import__('re').compile('offset=2'))
    titulo = pagina.locator('.property-card h3 a').first.inner_text()
    pagina.locator('.property-card h3 a').first.click()
    expect(pagina.get_by_role('heading', level=1)).to_have_text(titulo)
    pagina.get_by_role('link', name='← Volver al catálogo').click()
    expect(pagina).to_have_url(__import__('re').compile('offset=2'))
    expect(pagina.locator('#orden')).to_have_value('id')


def test_formulario_moneda_precio_y_orden(pagina, servidor):
    pagina.goto(servidor + '/consola/')
    pagina.get_by_label('Ciudad', exact=True).select_option('Bogotá')
    pagina.get_by_label('Operación', exact=True).select_option('venta')
    pagina.get_by_label('Moneda', exact=True).select_option('COP')
    pagina.locator('#precio_max').fill('103000000')
    pagina.get_by_role('button', name='Buscar inmuebles').click()
    expect(pagina.locator('[data-total]')).to_have_text('3')
    pagina.get_by_label('Ordenar por', exact=False).select_option('precio_desc')
    expect(pagina.locator('.property-card h3 a').first).to_have_text('Casa con jardín 03')
    expect(pagina.locator('#precio_max')).to_have_value('103000000')
    expect(pagina.locator('#moneda')).to_have_value('COP')


def test_galeria_lazy_fallo_y_recuperacion(pagina, servidor):
    id = identificar_inmueble('metrocuadrado', '1-M1')
    pagina.goto(servidor + '/consola/inmuebles/' + id)
    principal = pagina.locator('[data-gallery-main]')
    expect(principal).to_have_attribute('loading', 'lazy')
    pagina.get_by_role('button', name='Ver fotografía 2', exact=True).click()
    expect(pagina.locator('[data-gallery-count]')).to_have_text('2 / 3')
    expect(principal).to_have_attribute('src', 'https://images.test/dos.jpg')
    pagina.get_by_role('button', name='Fotografía siguiente', exact=True).click()
    expect(principal).to_be_hidden()
    expect(pagina.locator('[data-gallery-count]')).to_have_text('3 / 3')
    pagina.get_by_role('button', name='Ver fotografía 1', exact=True).click()
    expect(principal).to_be_visible()
    expect(principal).to_have_attribute('src', 'https://images.test/uno.jpg')


def test_movil_sin_desbordamiento_y_filtros(pagina, servidor, tmp_path):
    pagina.set_viewport_size({'width': 390, 'height': 844})
    pagina.goto(servidor + '/consola/')
    expect(pagina.locator('[data-filters]')).not_to_have_attribute('open', '')
    assert pagina.evaluate('document.documentElement.scrollWidth <= innerWidth')
    pagina.locator('[data-filters] summary').click()
    pagina.get_by_label('Ciudad', exact=True).select_option('Medellín')
    pagina.get_by_role('button', name='Buscar inmuebles').click()
    expect(pagina.locator('[data-total]')).to_have_text('13')
    assert pagina.evaluate('document.documentElement.scrollWidth <= innerWidth')
    pagina.locator('.property-card h3 a').first.click()
    expect(pagina.get_by_role('heading', name='Lo esencial')).to_be_visible()
    assert pagina.evaluate('document.documentElement.scrollWidth <= innerWidth')
    pagina.screenshot(path=str(tmp_path / 'ficha-movil.png'), full_page=True)


def test_error_de_precio_y_vacio_se_muestran_en_pantalla(pagina, servidor):
    pagina.goto(servidor + '/consola/?precio_max=100')
    expect(pagina.get_by_role('alert')).to_contain_text('Elige una operación y una moneda')
    pagina.goto(servidor + '/consola/?texto=sin-coincidencias')
    expect(pagina.get_by_role('heading', name='No encontramos inmuebles con estos filtros')).to_be_visible()
