"""Anunciantes v0.7: solo catálogo y CRM sintéticos."""
import csv
import hashlib
import io
import json
from urllib.parse import urlsplit, parse_qs

import pytest
from bs4 import BeautifulSoup
from fastapi.testclient import TestClient
from playwright.sync_api import expect

from catalogo.consultas import inmuebles_anunciante
from catalogo.persistencia.sqlite import CatalogoSQLite
from consola.anunciantes import enlace_contacto
from metro.web import app
from oportunidades.modelos import ClienteDatos
from oportunidades.servicio import servicio_oportunidades
from test_v03 import necesidades
from test_browser import servidor, pagina


@pytest.fixture
def anunciantes(escenario_consola):
    datos = escenario_consola
    with datos['store'].connect() as db:
        for n in range(1, 27):
            doc = datos['documentos'][f'{n}-M{n}']
            if n < 25:
                doc['normalized'].update(advertiser='AGENCIA' if n < 23 else 'Agencia',
                    phone='+57 310 123 4567' if n != 2 else '3009998888',
                    local_phone='601 234 5678', whatsapp='+57 310 123 4567',
                    advertiser_address='Calle pública 1')
            db.execute('UPDATE properties SET data_json=? WHERE id=?',
                       (json.dumps(doc), f'{n}-M{n}'))
    return datos, CatalogoSQLite(datos['ruta']).listar()


@pytest.mark.parametrize('valor,tel,wa', [
    ('+57 310 123 4567','tel:+573101234567','https://wa.me/573101234567'),
    ('573101234567','tel:573101234567','https://wa.me/573101234567'),
    ('3101234567','tel:3101234567',None),
    ('601 234 5678','tel:6012345678',None),
    ('javascript:alert(1)',None,None), ('+1234567?x=1',None,None),
    ('123/456789',None,None), ('',None,None), (None,None,None),
    ('0000000000',None,None), ('+0123456789','tel:+0123456789',None)])
def test_enlaces(valor, tel, wa):
    assert enlace_contacto(valor) == tel
    assert enlace_contacto(valor, whatsapp=True) == wa


def test_lectura_literal_antiguos_y_origen(anunciantes):
    datos, items = anunciantes
    assert len(inmuebles_anunciante(items, 'AGENCIA')) == 22
    assert len(inmuebles_anunciante(items, 'Agencia')) == 2
    assert inmuebles_anunciante(items, None) == []
    assert inmuebles_anunciante(items, '') == []
    assert inmuebles_anunciante(items, ' AGENCIA') == []
    i = next(i for i in items if i.origen.id_original == '25-M25')
    assert i.anunciante is i.telefono is None
    # Captura histórica con originales públicos, incluso nombre con doble espacio.
    doc = datos['documentos']['25-M25']
    doc['sources'] = {'flight_property': {'companyName':'A  B ', 'companyAddress':'Sede',
                                         'contactPhone':'3101234567','localPhone':'6012345678',
                                         'whatsapp':'573101234567'}}
    with datos['store'].connect() as db:
        db.execute('UPDATE properties SET data_json=? WHERE id=?', (json.dumps(doc), '25-M25'))
    i = CatalogoSQLite(datos['ruta']).obtener(i.id_interno)
    assert (i.anunciante,i.anunciante_direccion,i.telefono,i.telefono_fijo,i.whatsapp) == (
        'A  B ', 'Sede', '3101234567','6012345678','573101234567')


def test_panel_global_csv_y_ausentes(anunciantes):
    datos, items = anunciantes
    i = next(i for i in items if i.origen.id_original == '1-M1')
    antes = hashlib.sha256(datos['ruta'].read_bytes()).hexdigest()
    with TestClient(app) as c:
        soup = BeautifulSoup(c.get('/v0.4/?ciudad=Bogotá&limit=12').text, 'html.parser')
        assert soup.select_one('th:-soup-contains("Anunciante")')
        link = soup.select_one('[data-advertiser]')['href']
        origen_id = parse_qs(urlsplit(link).query)['inmueble'][0]
        r = c.get(link)
        assert r.status_code == 200
        panel = BeautifulSoup(r.text,'html.parser').select_one('[data-advertiser-content]')
        assert '21 inmueble(s)' in panel.text
        assert panel.select('a[href="tel:3009998888"]')
        assert panel.select('a[href="https://wa.me/573101234567"]')
        assert not panel.select(f'.advertiser-properties a[href$="{origen_id}"]')
        siguiente = panel.select_one('[data-advertiser-page]')['href']
        assert 'Medellín' in c.get(siguiente).text
        assert c.get(link+'&pagina=0').status_code == 422
        assert c.get('/consola/anunciante?inmueble=no-existe').status_code == 404
        sin = next(i for i in items if i.origen.id_original == '25-M25')
        assert c.get('/consola/anunciante',params={'inmueble':sin.id_interno}).status_code == 404
        rows = list(csv.DictReader(io.StringIO(c.get('/v0.4/exportar.csv?ciudad=Bogotá').text.lstrip('\ufeff')),delimiter=';'))
        assert len(rows) == 14
        assert rows[0]['Anunciante'] == 'AGENCIA'
        assert rows[0]['Teléfono móvil'] == "'+57 310 123 4567"
        assert rows[0]['Dirección del anunciante'] == 'Calle pública 1'
        assert set(r['Moneda'] for r in rows) == {'COP'}
    assert hashlib.sha256(datos['ruta'].read_bytes()).hexdigest() == antes


@pytest.fixture
def servidor_anunciantes(anunciantes, request):
    return request.getfixturevalue('servidor')


@pytest.mark.parametrize('w,h', [(1440,900),(820,1180),(390,844)])
def test_panel_navegador(servidor_anunciantes, pagina, anunciantes, tmp_path, w,h):
    page=pagina; url=servidor_anunciantes
    page.set_viewport_size({'width':w,'height':h})
    page.goto(url+'/v0.4/?ciudad=Bogotá&limit=12&orden=id')
    original=page.url
    assert page.locator('#advertiser-panel').count() == 1
    link=page.locator('[data-advertiser]').first
    link.click()
    panel=page.locator('#advertiser-panel')
    expect(panel).to_be_visible()
    expect(panel.locator('h1')).to_have_text('AGENCIA')
    page.screenshot(path=str(tmp_path/f'anunciante-{w}.png'))
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
    assert panel.evaluate('(e)=>e.scrollWidth<=e.clientWidth')
    panel.locator('[data-advertiser-page]').click()
    expect(panel.locator('.advertiser-properties')).to_contain_text('Medellín')
    page.keyboard.press('Escape');expect(panel).not_to_be_visible()
    expect(link).to_be_focused(); assert page.url==original
    # El panel de contacto se abre sobre la ficha histórica y vuelve a ella.
    page.locator('.property-link').first.click()
    expect(page.locator('#surface')).to_be_visible()
    page.locator('#surface [data-advertiser]').click()
    expect(panel).to_be_visible()
    panel.get_by_role('button',name='Cerrar anunciante').click()
    expect(page.locator('#surface [data-advertiser]')).to_be_focused()
    page.locator('#surface [data-advertiser]').click()
    panel.locator('.advertiser-properties a').first.click()
    expect(panel).not_to_be_visible()
    expect(page.locator('#surface')).to_be_visible()
    page.keyboard.press('Escape')
    s=servicio_oportunidades();o=s.capturar(ClienteDatos(nombre='Prueba anunciante'),necesidades())
    page.goto(url+f'/v0.4/?oportunidad={o.id}')
    page.locator('[data-advertiser]').first.click();expect(panel).to_be_visible()
    page.keyboard.press('Escape')
    page.goto(url+f'/v0.6/clientes/{o.cliente_id}?orden=precio_desc')
    original=page.url
    page.locator('[data-advertiser]').first.click();expect(panel).to_be_visible()
    expect(panel.locator('h1')).to_have_text('AGENCIA')
    # Tab permanece dentro del modal nativo.
    for _ in range(15): page.keyboard.press('Tab')
    assert page.evaluate('document.activeElement.closest("#advertiser-panel") !== null')
    page.keyboard.press('Escape');expect(panel).not_to_be_visible()
    assert page.url==original


def test_solo_nombre_contactos_invalidos_y_csv_seguro(anunciantes):
    datos, items = anunciantes
    i = next(i for i in items if i.origen.id_original == '25-M25')
    doc = datos['documentos']['25-M25']
    doc['normalized']['advertiser'] = '=AGENCIA <script>alert(1)</script>'
    def guardar():
        with datos['store'].connect() as db:
            db.execute('UPDATE properties SET data_json=? WHERE id=?',(json.dumps(doc),'25-M25'))
    guardar()
    with TestClient(app) as c:
        params={'inmueble':i.id_interno}
        r=c.get('/consola/anunciante',params=params)
        assert 'No hay datos de contacto disponibles.' in r.text
        assert 'No hay otros inmuebles capturados' in r.text
        assert '<script>alert(1)</script>' not in r.text
        doc['normalized'].update(phone='javascript:alert(1)',whatsapp='3101234567')
        guardar()
        panel=BeautifulSoup(c.get('/consola/anunciante',params=params).text,'html.parser')
        assert not panel.select('[href^="tel:"], [href^="https://wa.me/"]')
        rows=list(csv.DictReader(io.StringIO(c.get('/v0.4/exportar.csv?texto=25-M25').text.lstrip('\ufeff')),delimiter=';'))
        assert len(rows)==1 and rows[0]['Anunciante'].startswith("'=AGENCIA")
