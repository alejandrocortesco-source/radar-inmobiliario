"""Altas y bajas de fuentes con bases sintéticas, sin scraping real."""
import concurrent.futures
import sqlite3
from unittest.mock import Mock

import pytest
from playwright.sync_api import expect
from metro.web import servicio
from catalogo.persistencia.busquedas import BusquedasSQLite
from catalogo.persistencia.contrato import ErrorLecturaCatalogo
from test_v06 import escenario06
from test_browser import servidor
from conftest import A, B

URL = 'https://www.metrocuadrado.com/inmuebles/venta/bogota/cedritos'


def test_alta_eliminacion_reingreso_y_catalogo_intacto(escenario06, escenario_consola):
    c, _, _, _ = escenario06
    antes = escenario_consola['ruta'].read_bytes()
    originales = servicio().listar()
    for url, nombre in [(A, 'Carolina'), (URL, 'Cedritos')]:
        assert c.post('/v0.6/fuentes', data={'url': url, 'nombre': nombre}).status_code == 200
    fuente = next(b for b in servicio().listar_busquedas() if b['nombre'] == 'Carolina')
    datos = {'fuente': fuente['fuente'], 'id_busqueda': fuente['id_busqueda']}
    assert c.get('/v0.6/fuentes/eliminar').status_code == 405
    assert c.post('/v0.6/fuentes/eliminar', data=datos).status_code == 422
    assert len(servicio().listar_busquedas()) == 2
    datos['confirmar'] = '1'
    assert c.post('/v0.6/fuentes/eliminar', data=datos | {'fuente': 'otra'}).status_code == 404
    assert len(servicio().listar_busquedas()) == 2
    respuesta = c.post('/v0.6/fuentes/eliminar', data=datos)
    assert respuesta.status_code == 200 and 'Búsqueda eliminada' in respuesta.text
    assert [b['nombre'] for b in servicio().listar_busquedas()] == ['Cedritos']
    assert c.post('/v0.6/fuentes/eliminar', data=datos).status_code == 404
    assert servicio().listar() == originales
    assert c.post('/v0.6/fuentes', data={'url': A, 'nombre': 'Carolina de nuevo'}).status_code == 200
    assert len(servicio().listar_busquedas()) == 2
    assert escenario_consola['ruta'].read_bytes() == antes


def test_eliminar_sin_base_no_crea_y_error_almacenamiento(escenario06, tmp_path, monkeypatch):
    repo = BusquedasSQLite(tmp_path / 'ausente.sqlite')
    assert not repo.eliminar('metrocuadrado', URL)
    assert not repo.ruta.exists()
    # Una base auxiliar con otras tablas tampoco se altera.
    with sqlite3.connect(repo.ruta) as db:
        db.execute('CREATE TABLE otra (dato TEXT)')
    assert not repo.eliminar('metrocuadrado', URL)
    with sqlite3.connect(repo.ruta) as db:
        assert db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall() == [('otra',)]
    c, *_ = escenario06
    monkeypatch.setattr(BusquedasSQLite, 'eliminar', Mock(side_effect=ErrorLecturaCatalogo('No se pudo eliminar la búsqueda')))
    r = c.post('/v0.6/fuentes/eliminar', data={'fuente': 'metrocuadrado', 'id_busqueda': URL, 'confirmar': '1'})
    assert r.status_code == 503 and 'No se pudo eliminar' in r.text


def test_cli_omite_eliminadas_y_rechaza_sin_fuentes(escenario06, escenario_consola, monkeypatch):
    import metro.__main__ as cli
    c, *_ = escenario06
    for url in (URL, B):
        c.post('/v0.6/fuentes', data={'url': url, 'nombre': 'Fuente'})
    datos = {'fuente': 'metrocuadrado', 'id_busqueda': URL, 'confirmar': '1'}
    assert c.post('/v0.6/fuentes/eliminar', data=datos).status_code == 200
    capturadas = []
    class ScraperPrueba:
        def __init__(self, config):
            capturadas.append(config.urls)
        async def run(self):
            return {'status': 'completed'}
    monkeypatch.setattr(cli, 'Scraper', ScraperPrueba)
    monkeypatch.setattr('sys.argv', ['metro', '--db', str(escenario_consola['ruta']), 'scrape', '--fuentes-registradas'])
    with concurrent.futures.ThreadPoolExecutor() as executor:
        executor.submit(cli.main).result()
    assert capturadas == [[B]]
    assert c.post('/v0.6/fuentes/eliminar', data=datos | {'id_busqueda': B}).status_code == 200
    with concurrent.futures.ThreadPoolExecutor() as executor:
        with pytest.raises(SystemExit) as exc:
            executor.submit(cli.main).result()
    assert exc.value.code == 2 and len(capturadas) == 1


@pytest.mark.parametrize('ancho,javascript', [(1440, True), (768, True), (390, True), (390, False)])
def test_agregar_y_eliminar_en_chromium(servidor, chromium, escenario_consola, ancho, javascript):
    antes = escenario_consola['ruta'].read_bytes()
    contexto = chromium.new_context(viewport={'width': ancho, 'height': 900}, java_script_enabled=javascript)
    page = contexto.new_page()
    page.goto(servidor + '/v0.6/')
    page.locator('.source-form [name=nombre]').fill('Cedritos de prueba')
    page.locator('.source-form [name=url]').fill(URL + '/?utm_source=prueba#lista')
    page.get_by_role('button', name='Guardar fuente').click()
    expect(page.get_by_role('status')).to_contain_text('Fuente guardada')
    expect(page.locator('[data-registered-source]')).to_have_count(1)
    expect(page.locator('[data-registered-source] > a')).to_have_attribute('href', URL)
    # El segundo alta se normaliza y no duplica ni cambia el nombre.
    page.locator('.source-form [name=nombre]').fill('No reemplazar')
    page.locator('.source-form [name=url]').fill(URL)
    page.get_by_role('button', name='Guardar fuente').click()
    expect(page.get_by_role('status')).to_contain_text('ya está registrada')
    expect(page.locator('[data-registered-source]')).to_have_count(1)
    summary = page.locator('.source-delete > summary')
    summary.focus()
    expect(summary).to_be_focused()
    page.keyboard.press('Enter')
    expect(page.get_by_role('button', name='Confirmar eliminación')).to_be_visible()
    page.wait_for_load_state('load')
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    assert page.locator('[data-dashboard-section]').count() == 4
    page.screenshot(path=str(__import__('pathlib').Path('.tmp') / f'fuentes-{ancho}-{javascript}.png'), full_page=True)
    page.get_by_role('button', name='Confirmar eliminación').click()
    expect(page.get_by_role('status')).to_contain_text('Búsqueda eliminada')
    expect(page.locator('[data-registered-source]')).to_have_count(0)
    expect(page.get_by_text('No hay búsquedas registradas. Agrega una URL para empezar.')).to_be_visible()
    page.reload()
    expect(page.locator('[data-registered-source]')).to_have_count(0)
    page.locator('.source-form [name=nombre]').fill('Cedritos otra vez')
    page.locator('.source-form [name=url]').fill(URL)
    page.get_by_role('button', name='Guardar fuente').click()
    expect(page.get_by_role('status')).to_contain_text('Fuente guardada')
    expect(page.locator('[data-registered-source]')).to_have_count(1)
    contexto.close()
    assert escenario_consola['ruta'].read_bytes() == antes
