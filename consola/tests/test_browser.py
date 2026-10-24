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
    expect(pagina.locator('.catalog-table tbody tr')).to_have_count(2)
    expect(pagina.locator('[data-total]')).to_have_text('26')
    pagina.get_by_role('link', name='Siguiente →').click()
    expect(pagina).to_have_url(__import__('re').compile('offset=2'))
    enlace = pagina.locator('.property-link').first
    titulo = enlace.get_attribute('aria-label').removeprefix('Ver ficha de ')
    enlace.click()
    expect(pagina.get_by_role('heading', level=1)).to_have_text(titulo)
    pagina.get_by_role('link', name='← Volver al catálogo').click()
    expect(pagina).to_have_url(__import__('re').compile('offset=2'))
    expect(pagina.locator('#orden')).to_have_value('id')


def test_formulario_moneda_precio_y_orden(pagina, servidor):
    pagina.goto(servidor + '/consola/')
    pagina.locator('[data-filters] > summary').click()
    pagina.get_by_label('Ciudad', exact=True).select_option('Bogotá')
    pagina.get_by_role('button', name='Aplicar filtros', exact=True).click()
    pagina.locator('.price-filter > summary').click()
    pagina.get_by_label('Operación', exact=True).select_option('venta')
    pagina.get_by_label('Moneda', exact=True).select_option('COP')
    pagina.locator('#precio_max').fill('103000000')
    pagina.get_by_role('button', name='Aplicar precio').click()
    expect(pagina.locator('[data-total]')).to_have_text('3')
    pagina.get_by_text('Ordenar', exact=True).click()
    pagina.get_by_label('Ordenar por', exact=True).select_option('precio_desc')
    pagina.get_by_role('button', name='Aplicar orden').click()
    expect(pagina.locator('.property-link').first).to_have_attribute('aria-label', 'Ver ficha de Casa con jardín 03')
    expect(pagina.locator('#precio_max')).to_have_value('103000000')
    expect(pagina.locator('#moneda')).to_have_value('COP')
    expect(pagina.locator('#ciudad')).to_have_value('Bogotá')
    pagina.get_by_role('columnheader', name='Precio').get_by_role('link').click()
    expect(pagina.locator('.property-link').first).to_have_attribute('aria-label', 'Ver ficha de Casa con jardín 01')


def test_fotos_solo_enlaces_sin_solicitudes_de_imagenes(pagina, servidor):
    solicitudes = []
    pagina.on('request', lambda req: solicitudes.append(req))
    pagina.goto(servidor + '/consola/?limit=48')
    expect(pagina.locator('img, iframe')).to_have_count(0)
    pagina.locator('.photo-links > summary').first.click()
    expect(pagina.locator('.photo-links[open] a').first).to_have_attribute('target', '_blank')
    id = identificar_inmueble('metrocuadrado', '1-M1')
    pagina.goto(servidor + '/consola/inmuebles/' + id)
    pagina.locator('.detail-photos > summary').click()
    expect(pagina.locator('.photo-list a')).to_have_count(3)
    expect(pagina.locator('.photo-list a').nth(1)).to_have_attribute('href', 'https://images.test/dos.jpg')
    expect(pagina.locator('img, iframe')).to_have_count(0)
    assert not [r for r in solicitudes if r.resource_type == 'image' or 'images.test' in r.url]
    assert all(r.url.startswith(servidor) for r in solicitudes)


@pytest.mark.parametrize('ancho', [390, 768, 1024, 1440])
def test_adaptable_sin_desbordamiento_y_filtros(pagina, servidor, tmp_path, ancho):
    pagina.set_viewport_size({'width': ancho, 'height': 900})
    pagina.goto(servidor + '/consola/')
    expect(pagina.locator('[data-filters]')).not_to_have_attribute('open', '')
    expect(pagina.locator('.catalog-table tbody tr')).to_have_count(24)
    assert pagina.evaluate('document.documentElement.scrollWidth <= innerWidth')
    pagina.locator('[data-filters] > summary').click()
    pagina.get_by_label('Ciudad', exact=True).select_option('Medellín')
    pagina.get_by_role('button', name='Aplicar filtros', exact=True).click()
    expect(pagina.locator('[data-total]')).to_have_text('13')
    assert pagina.evaluate('document.documentElement.scrollWidth <= innerWidth')
    pagina.screenshot(path=str(tmp_path / f'catalogo-{ancho}.png'), full_page=True)
    pagina.locator('.property-link').first.click()
    expect(pagina.get_by_role('heading', name='Descripción')).to_be_visible()
    assert pagina.evaluate('document.documentElement.scrollWidth <= innerWidth')
    pagina.screenshot(path=str(tmp_path / f'ficha-{ancho}.png'), full_page=True)


def test_error_de_precio_y_vacio_se_muestran_en_pantalla(pagina, servidor):
    pagina.goto(servidor + '/consola/?precio_max=100')
    expect(pagina.get_by_role('alert')).to_contain_text('Elige una operación y una moneda')
    pagina.goto(servidor + '/consola/?texto=sin-coincidencias')
    expect(pagina.get_by_role('heading', name='No encontramos inmuebles con estos filtros')).to_be_visible()


def test_busqueda_paginacion_tamano_y_exportacion(pagina, servidor):
    pagina.goto(servidor + '/consola/')
    pagina.get_by_text('Buscar', exact=True).click()
    pagina.get_by_label('Buscar por texto').fill('jardín')
    pagina.get_by_role('button', name='Buscar inmuebles').click()
    expect(pagina.locator('[data-total]')).to_have_text('26')
    pagina.get_by_label('Filas', exact=True).select_option('12')
    expect(pagina.locator('.catalog-table tbody tr')).to_have_count(12)
    pagina.get_by_role('link', name='Siguiente →').click()
    expect(pagina).to_have_url(__import__('re').compile('offset=12'))
    pagina.get_by_text('Exportar', exact=True).click()
    with pagina.expect_download() as descarga:
        pagina.get_by_role('link', name='Descargar CSV').click()
    assert descarga.value.suggested_filename == 'radar-catalogo.csv'
    pagina.get_by_role('link', name='Limpiar', exact=True).click()
    expect(pagina.locator('.catalog-table tbody tr')).to_have_count(24)


def test_regreso_restaura_desplazamiento(pagina, servidor):
    pagina.set_viewport_size({'width': 768, 'height': 500})
    pagina.goto(servidor + '/consola/?limit=48&texto=jardín')
    enlace = pagina.locator('.property-link').nth(14)
    enlace.scroll_into_view_if_needed()
    previo = pagina.evaluate('scrollY')
    enlace.click()
    pagina.get_by_role('link', name='← Volver al catálogo').click()
    pagina.wait_for_function('(y) => Math.abs(scrollY - y) < 5', arg=previo)
    expect(pagina.locator('#texto')).to_have_value('jardín')


def test_formulario_sin_javascript(chromium, servidor):
    contexto = chromium.new_context(java_script_enabled=False)
    page = contexto.new_page()
    try:
        page.goto(servidor + '/consola/')
        page.locator('[data-filters] > summary').click()
        page.get_by_label('Ciudad', exact=True).select_option('Bogotá')
        page.get_by_role('button', name='Aplicar filtros', exact=True).click()
        expect(page.locator('[data-total]')).to_have_text('13')
        page.locator('.property-link').first.click()
        page.get_by_role('link', name='← Volver al catálogo').click()
        expect(page.locator('#ciudad')).to_have_value('Bogotá')
    finally:
        contexto.close()


def test_orden_precio_solicita_operacion_y_moneda(pagina, servidor):
    pagina.goto(servidor + '/consola/')
    pagina.get_by_role('columnheader', name='Precio', exact=True).get_by_role('link').click()
    expect(pagina.locator('.price-filter')).to_have_attribute('open', '')
    expect(pagina.locator('#operacion')).to_be_focused()
    pagina.get_by_label('Operación', exact=True).select_option('venta')
    pagina.get_by_label('Moneda', exact=True).select_option('COP')
    pagina.get_by_role('button', name='Aplicar precio').click()
    expect(pagina.locator('.property-link').first).to_have_attribute('aria-label', 'Ver ficha de Casa con jardín 01')
    expect(pagina.locator('th[aria-sort]')).to_have_attribute('aria-sort', 'ascending')


def test_precio_unico_e_iconos_con_mapa_original(pagina, servidor):
    pagina.goto(servidor + '/consola/?texto=Casa+con+jard%C3%ADn+01')
    expect(pagina.locator('td.prices > span')).to_have_count(1)
    expect(pagina.locator('td.prices')).to_have_text('$101.000.000 · Venta')
    expect(pagina.locator('.external-links svg')).to_have_count(3)
    mapa = pagina.get_by_role('link', name='Mapa original de Casa con jardín 01. Ubicación aproximada')
    expect(mapa).to_have_attribute('href', 'https://www.metrocuadrado.com/inmueble/casa/1-M1#location-section')
    expect(mapa).to_have_attribute('target', '_blank')
    pagina.locator('.property-link').click()
    expect(pagina.locator('.offers > span')).to_have_count(2)
    expect(pagina.get_by_text('Ubicación aproximada', exact=True)).to_be_visible()
    pagina.get_by_role('link', name='← Volver al catálogo').click()
    pagina.goto(servidor + '/consola/?operacion=arriendo')
    expect(pagina.locator('td.prices')).to_have_text('$1.000.000 · Arriendo')
    expect(pagina.locator('td.prices > span')).to_have_count(1)
