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


def seleccionar_barrio(page, javascript):
    if javascript:
        page.locator('[data-location-picker] > summary').click()
        page.locator('[data-location-row][data-city="bogota"][data-key="barrio:la carolina"] input').check()
        page.locator('[data-location-done]').click()
    else:
        page.locator('#crm_ubicaciones').select_option('barrio:La Carolina')


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
    mapa = pagina.get_by_role('link', name='Mapa en OpenStreetMap de Casa con jardín 01. Centro de una zona aproximada; no es una dirección exacta')
    expect(mapa).to_have_attribute('href', 'https://www.openstreetmap.org/?mlat=4.7&mlon=-74.04#map=16/4.7/-74.04')
    expect(mapa).to_have_attribute('target', '_blank')
    pagina.locator('.property-link').click()
    expect(pagina.locator('.offers > span')).to_have_count(2)
    expect(pagina.get_by_text('Centro de una zona aproximada; no es una dirección exacta', exact=True)).to_be_visible()
    pagina.get_by_role('link', name='← Volver al catálogo').click()
    pagina.goto(servidor + '/consola/?operacion=arriendo')
    expect(pagina.locator('td.prices')).to_have_text('$1.000.000 · Arriendo')
    expect(pagina.locator('td.prices > span')).to_have_count(1)


@pytest.mark.parametrize('javascript,ancho', [(True, 1440), (True, 390), (False, 768)])
def test_v03_ciclo_captura_edicion_y_matching(chromium, servidor, tmp_path, javascript, ancho):
    contexto = chromium.new_context(java_script_enabled=javascript, viewport={'width': ancho, 'height': 1000})
    page = contexto.new_page()
    errores = []
    page.on('pageerror', lambda e: errores.append(str(e)))
    try:
        page.goto(servidor + '/consola/')
        page.locator('#crm_nombre').fill('Ana de prueba')
        page.locator('#crm_telefono').fill('3001234567')
        page.locator('#crm_tipo').select_option('casa')
        page.locator('#crm_ciudad').select_option('Bogotá')
        if not javascript:
            page.get_by_role('button', name='Actualizar barrios', exact=True).click()
        page.locator('#crm_presupuesto').fill('110000000')
        seleccionar_barrio(page, javascript)
        page.get_by_role('button', name='Guardar oportunidad', exact=True).click()
        if javascript:
            assert page.locator('#crm_nombre').input_value() == 'Ana de prueba'
            assert not page.locator('#crm_habitaciones_min').evaluate('(e) => e.checkValidity()')
        else:
            expect(page.get_by_role('alert')).to_contain_text('habitaciones mínimas o área mínima')
        page.locator('#crm_habitaciones_min').fill('3')
        page.get_by_role('button', name='Guardar oportunidad', exact=True).click()
        expect(page.get_by_role('status')).to_contain_text('Guardado correctamente')
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        page.screenshot(path=str(tmp_path / f'captura-v03-{ancho}.png'), full_page=True)
        page.locator('#crm-form').get_by_role('link', name='Buscar coincidencias', exact=True).click()
        expect(page.locator('.matching-table tbody tr')).to_have_count(10)
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        page.screenshot(path=str(tmp_path / f'matching-v03-{ancho}.png'), full_page=True)
        page.get_by_role('link', name='Modificar oportunidad').click()
        page.locator('#crm_presupuesto').fill('103000000')
        page.get_by_role('button', name='Guardar cambios').click()
        page.locator('#crm-form').get_by_role('link', name='Buscar coincidencias', exact=True).click()
        expect(page.locator('.matching-table tbody tr')).to_have_count(3)
        page.get_by_role('link', name='Modificar oportunidad').click()
        page.get_by_role('button', name='Preparar nueva oportunidad').click()
        expect(page.locator('#crm_nombre')).to_have_value('Ana de prueba')
        page.locator('#crm_tipo').select_option('casa')
        page.locator('#crm_ciudad').select_option('Bogotá')
        if not javascript:
            page.get_by_role('button', name='Actualizar barrios', exact=True).click()
        page.locator('#crm_presupuesto').fill('110000000')
        seleccionar_barrio(page, javascript)
        page.locator('#crm_area_min_m2').fill('82')
        page.get_by_role('button', name='Guardar oportunidad', exact=True).click()
        expect(page.locator('.crm-records > summary')).to_contain_text('Clientes (1) y oportunidades (2)')
        assert not errores
    finally:
        contexto.close()


@pytest.mark.parametrize('javascript,ancho', [(True, 1440), (True, 390), (False, 768)])
def test_correccion_guardar_buscar_metricas_y_explica_cero(chromium, servidor, tmp_path, javascript, ancho):
    contexto = chromium.new_context(java_script_enabled=javascript, viewport={'width': ancho, 'height': 900})
    page = contexto.new_page()
    errores = []
    page.on('pageerror', lambda e: errores.append(str(e)))
    try:
        page.goto(servidor + '/consola/')
        expect(page.locator('[data-match-total]')).to_have_text('26')
        expect(page.locator('[data-match-confirmed]')).to_have_text('—')
        page.locator('#crm_nombre').fill('Prueba de corrección')
        page.locator('#crm_tipo').select_option('casa')
        page.locator('#crm_ciudad').select_option('Bogotá')
        if not javascript:
            page.get_by_role('button', name='Actualizar barrios', exact=True).click()
        seleccionar_barrio(page, javascript)
        page.locator('#crm_presupuesto').fill('110000000')
        page.locator('#crm_habitaciones_min').fill('3')
        page.get_by_role('button', name='Guardar y buscar coincidencias', exact=True).click()
        expect(page.locator('[data-match-confirmed]')).to_have_text('10')
        expect(page.locator('[data-match-pending]')).to_have_text('0')
        expect(page.locator('.matching-table tbody tr')).to_have_count(10)
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        page.screenshot(path=str(tmp_path / f'matching-corregido-{ancho}.png'))
        page.locator('.matching-diagnostics > summary').click()
        expect(page.locator('.diagnostic-table tbody tr')).to_have_count(6)
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        page.locator('#crm_habitaciones_min').fill('100')
        page.get_by_role('button', name='Guardar y buscar coincidencias', exact=True).click()
        expect(page.locator('[data-match-confirmed]')).to_have_text('0')
        expect(page.locator('.matching-table tbody tr')).to_have_count(0)
        expect(page.locator('.match-empty')).to_contain_text('Habitaciones mínimas: 26 inmuebles no cumplen')
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        assert not errores
        page.screenshot(path=str(tmp_path / f'sin-coincidencias-{ancho}.png'))
    finally:
        contexto.close()


def test_selector_barrios_busqueda_etiquetas_cambio_y_guardado(pagina, servidor, escenario_consola):
    for id, doc in escenario_consola['documentos'].items():
        if doc['normalized']['city'] == 'Medellín':
            doc['normalized']['neighborhood'] = 'El Poblado'
            escenario_consola['store'].result(escenario_consola['run'], id, 'success', doc)
    pagina.goto(servidor + '/consola/')
    pagina.locator('#crm_ciudad').select_option('Bogotá')
    pagina.locator('[data-location-picker] > summary').click()
    pagina.locator('#crm_buscar_barrio').fill('  CAROLÍNA  ')
    expect(pagina.locator('[data-location-row]:visible')).to_have_count(1)
    pagina.locator('[data-location-row][data-city="bogota"][data-key="barrio:la carolina"] input').check()
    expect(pagina.locator('[data-location-picker]')).to_have_attribute('open', '')
    expect(pagina.locator('.location-tag')).to_have_count(1)

    pagina.get_by_role('button', name='Quitar La Carolina', exact=True).click()
    expect(pagina.locator('.location-tag')).to_have_count(0)
    pagina.locator('[data-location-row][data-city="bogota"][data-key="barrio:la carolina"] input').check()
    pagina.locator('#crm_ciudad').select_option('Medellín')
    expect(pagina.locator('.location-tag')).to_have_count(0)
    expect(pagina.locator('[data-location-notice]')).to_contain_text('Se retiraron')
    pagina.locator('[data-location-picker] > summary').click()
    # La semilla controlada todavía no incluye Medellín: el nombre extraído no
    # se convierte por sí solo en un barrio confirmado. Su zona sí está disponible.
    expect(pagina.locator('[data-location-row][data-city="medellin"][data-key="barrio:el poblado"]')).to_have_count(0)
    expect(pagina.locator('[data-location-row][data-city="medellin"][data-key="zona:norte"]')).to_be_visible()
    pagina.locator('#crm_ciudad').select_option('Bogotá')
    pagina.locator('[data-location-picker] > summary').click()
    pagina.locator('[data-location-row][data-city="bogota"][data-key="barrio:la carolina"] input').check()
    pagina.locator('[data-location-done]').click()
    pagina.locator('#crm_nombre').fill('Prueba selector')
    pagina.locator('#crm_tipo').select_option('casa')
    pagina.locator('#crm_presupuesto').fill('110000000')
    pagina.locator('#crm_habitaciones_min').fill('3')
    pagina.get_by_role('button', name='Guardar y buscar coincidencias', exact=True).click()
    expect(pagina.locator('[data-match-confirmed]')).to_have_text('10')
    expect(pagina.locator('.location-tag')).to_have_count(1)


@pytest.mark.parametrize('ancho', [1440, 390])
def test_tabla_matching_orden_pagina_y_ficha(pagina, servidor, ancho):
    pagina.set_viewport_size({'width': ancho, 'height': 900})
    pagina.goto(servidor + '/consola/')
    pagina.locator('#crm_nombre').fill('Comparación de inmuebles')
    pagina.locator('#crm_tipo').select_option('casa')
    pagina.locator('#crm_ciudad').select_option('Bogotá')
    seleccionar_barrio(pagina, True)
    pagina.locator('#crm_presupuesto').fill('200000000')
    pagina.locator('#crm_habitaciones_min').fill('3')
    pagina.get_by_role('button', name='Guardar y buscar coincidencias', exact=True).click()
    expect(pagina.locator('.matching-table tbody tr')).to_have_count(13)
    pagina.get_by_role('link', name='Mostrar 12 resultados por página').click()
    expect(pagina.locator('.matching-table tbody tr')).to_have_count(12)
    # Primera pulsación ascendente y segunda descendente; se ordena todo antes de paginar.
    pagina.get_by_role('link', name='Ordenar matching por Precio', exact=True).click()
    pagina.get_by_role('link', name='Ordenar matching por Precio', exact=True).click()
    expect(pagina.locator('.matching-table tbody tr').first).to_have_attribute('data-match-id', '13-M13')
    assert pagina.evaluate('document.documentElement.scrollWidth <= innerWidth')
    if ancho == 390:
        assert pagina.locator('[data-match-scroll]').evaluate('(e) => e.scrollWidth > e.clientWidth')
    pagina.locator('.matching-pagination').get_by_role('link', name='Siguiente →').click()
    expect(pagina.locator('.matching-table tbody tr')).to_have_count(1)
    pagina.locator('.match-property-link').click()
    expect(pagina.get_by_role('heading', level=1)).to_have_text('Casa con jardín 01')
    pagina.get_by_role('link', name='← Volver al catálogo').click()
    expect(pagina.locator('.matching-table tbody tr')).to_have_count(1)
    expect(pagina.locator('[data-match-confirmed]')).to_have_text('13')
