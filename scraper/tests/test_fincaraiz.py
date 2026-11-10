"""Fincaraíz sintético: nunca navega al portal real en las pruebas."""
import asyncio
import copy
import json
from dataclasses import asdict
from unittest.mock import AsyncMock

import pytest
from playwright.async_api import async_playwright
from catalogo.fuentes.fincaraiz import REFERENCIA, identidad, validar_url, resolver, opciones_iniciales
from catalogo.identidad import identificar_inmueble
from catalogo.persistencia.busquedas import BusquedasSQLite
from fincaraiz.extraction import normalizar, enlace
from fincaraiz.browser import listado, siguiente, verificar
from fincaraiz.scraper import FincaraizStore, FincaraizConfig, FincaraizScraper
from metro.extraction import ExtractionError


def config():
    return copy.deepcopy(opciones_iniciales()[0])


def property(codigo=123, precio=800000000):
    return {'id': codigo, 'link': '/apartamento-en-venta-en-la-carolina-bogota/' + str(codigo),
            'title': 'Apartamento sintético', 'description': 'Descripción sintética completa',
            'operation_type': {'id': 1, 'name': 'Venta'}, 'property_type': {'id': 2, 'name': 'Apartamento'},
            'price': {'amount': precio}, 'commonExpenses': {'amount': 0},
            'locations': {'location_main': {'id': 'principal', 'name': 'La Carolina', 'location_type': 'neighbourhood'},
                          'city': [{'name': 'Bogotá'}], 'neighbourhood': [{'name': 'Cedritos'}, {'name': 'La Carolina'}]},
            'm2': 78, 'm2Built': 72.12, 'm2apto': 72.12, 'bedrooms': 2, 'bathrooms': 0, 'garage': 0,
            'antiquity': 3, 'technicalSheet': [{'field': 'constructionYear', 'text': 'Antigüedad', 'value': '9 a 15 años'}],
            'images': [{'image': 'https://example.invalid/foto.jpg'}],
            'owner': {'name': 'Empresa exacta ', 'masked_phone': '+5760', 'whatsapp_phone': None,
                      'inmoPropsLink': '/inmobiliarias/123-empresa/propiedades'}}


def pp(items, number=1, total=2, more=True):
    return {'params': {'filters': config()['filtros']}, 'fetchResult': {'searchFast': {'data': items,
            'paginatorInfo': {'currentPage': number, 'total': total, 'lastPage': 2 if total else 0, 'hasMorePages': more}}}}


def html(data, next_url=None):
    return '<html><head><title>Portal sintético</title></head><body><script id="__NEXT_DATA__" type="application/json">' + json.dumps({'props': {'pageProps': data}}) + '</script>' + (f'<a href="{next_url}">2</a>' if next_url else '') + '</body></html>'


def test_url_preserva_parametros_y_rechaza_ficha_dominios_y_paginas():
    assert validar_url('https://www.fincaraiz.com.co/venta/bogota') == 'https://www.fincaraiz.com.co/venta/bogota'
    url = REFERENCIA + '?precio=900000000&habitaciones=2&x=&x=3'
    assert validar_url(url) == url
    assert 'precio=900000000' in identidad(url) and 'x=&x=3' in identidad(url)
    assert identidad(url) == identidad(REFERENCIA + '?x=3&habitaciones=2&precio=900000000&x=')
    for bad in ('https://evil.invalid/venta/casas/bogota', 'https://www.fincaraiz.com.co.evil.invalid/venta/casas/bogota',
                'https://www.fincaraiz.com.co/apartamento-en-venta/123', REFERENCIA+'/pagina2',
                REFERENCIA.replace('www.', 'user@www.'), REFERENCIA + ' '):
        with pytest.raises(ValueError): validar_url(bad)


def test_normalizacion_ubicacion_principal_areas_ceros_contactos_y_edad():
    p = property(); d = normalizar(p, enlace(p)['url']); n = d['normalized']
    assert n['area'] == 78 and n['built_area'] == n['private_area'] == 72.12
    assert n['bathrooms'] == n['garages'] == n['administration'] == 0
    assert n['neighborhood'] == 'La Carolina' and n['advertiser'] == 'Empresa exacta '
    assert n['phone'] is n['whatsapp'] is None
    assert d['extra']['area_discrepancy'] and n['age'] == '9 a 15 años'
    assert d['extra']['antiquity_code'] == 3
    p['locations']['location_main'] = {}; p['bathrooms'] = 'fallo'; p['m2Built'] = None
    d = normalizar(p, enlace(p)['url'])
    assert d['normalized']['neighborhood'] is None and d['normalized']['zone'] is None
    assert d['fields']['bathrooms']['status'] == 'error' and d['fields']['built_area']['status'] == 'absent'
    assert d['quality'] == 'partial'
    p['id'] = 456
    with pytest.raises(ExtractionError): enlace(p)


def test_criterios_solo_correspondencias_verificadas():
    c = config()['criterios']
    valores = {'fr_' + k: c[k] for k in ('operacion', 'ciudad', 'ubicacion')}
    valores['fr_tipos'] = ','.join(c['tipos'])
    assert resolver(valores, [config()]) == REFERENCIA
    with pytest.raises(ValueError, match='URL filtrada'):
        resolver(valores | {'fr_ubicacion': 'inventada'}, [config()])


def test_auxiliar_revision_estado_no_crea_catalogo(tmp_path):
    repo = BusquedasSQLite(tmp_path/'crm.sqlite'); c = config()
    key = repo.guardar_fincaraiz('Referencia', c)
    assert repo.configuracion_fincaraiz(key) == c and repo.listar()[0]['activa']
    repo.cambiar_estado('fincaraiz', key, False)
    assert not repo.listar()[0]['activa']
    from fincaraiz.__main__ import configuracion
    assert not configuracion(repo, tmp_path/'fincaraiz.sqlite').searches
    repo.cambiar_estado('fincaraiz', key, True)
    assert key in configuracion(repo, tmp_path/'fincaraiz.sqlite').searches
    c['url_efectiva'] += '?precio=900000000'
    nuevo = repo.guardar_fincaraiz('Editada', c, key)
    assert nuevo != key and len(repo.listar()) == 1
    assert repo.configuracion_fincaraiz(key) and repo.eliminar('fincaraiz', nuevo)
    assert not (tmp_path/'fincaraiz.sqlite').exists()


def test_datos_incompletos_nunca_son_busqueda_vacia():
    page2 = pp([property()], number=2)
    page2['params']['filters']['page'] = {'value': 2, 'text': 'página 2'}
    assert 'page' not in listado(page2)[0]
    for bad in ({}, pp([], total=2), pp([property()], total=0)):
        with pytest.raises(ExtractionError): listado(bad)


def test_motor_incremental_identidad_fallos_y_ausencias(tmp_path):
    store = FincaraizStore(tmp_path/'fincaraiz.sqlite'); c = config(); a = identidad(REFERENCIA); b = identidad(REFERENCIA+'?habitaciones=2')
    item = enlace(property()); doc = normalizar(property(), item['url'])
    def run(mapping, complete=True, status='running'):
        r = store.new_run(a, {'urls': list(mapping), 'listing_currency': 'COP'})
        for key, links in mapping.items():
            store.save_page(r, 1, '1', key, 'page', links, None, search_url=key)
            store.update_search(r, key, complete=complete)
        store.plan_incremental(r); store.update_run(r, status=status)
        return r
    r = run({a: [item], b: [item]}); store.result(r, '123', 'success', doc)
    assert store.summary(r)['unique'] == 1 and store.summary(r)['duplicates'] == 1
    r2 = run({a: [item]}); assert store.summary(r2)['classifications'] == {'unchanged': 1}
    r3 = run({a: [enlace(property(precio=900000000))]}); assert store.summary(r3)['classifications'] == {'modified': 1}
    store.result(r3, '123', 'failed', error='temporal')
    absent = copy.deepcopy(doc); absent['photos'] = []
    store.result(r3, '123', 'success', absent)
    assert store.summary(r3)['statuses'] == {'partial': 1}
    absent = copy.deepcopy(doc); absent['normalized']['built_area'] = None
    store.result(r3, '123', 'success', absent)
    assert store.summary(r3)['statuses'] == {'partial': 1}
    with store.connect() as db:
        assert json.loads(db.execute('SELECT data_json FROM properties').fetchone()[0]) == doc
    for complete, status in ((False,'incomplete'), (True,'blocked'), (True,'interrupted')):
        r = run({a: []}, complete, status); assert not store.finalize_absences(r)
    for _ in range(2):
        r = run({a: []}, True, 'completed'); assert store.finalize_absences(r)
    with store.connect() as db:
        assert dict(db.execute('SELECT search_url,state FROM search_memberships')) == {a: 'removed', b: 'active'}
    assert len({identificar_inmueble(s, '123') for s in ('metrocuadrado','wasi','fincaraiz')}) == 3


def test_chromium_paginacion_filtros_repeticion_checkpoint_y_limite(tmp_path):
    async def prueba():
        cfg = FincaraizConfig(db=str(tmp_path/'fr.sqlite'), url=REFERENCIA, urls=[REFERENCIA], searches={REFERENCIA: config()}, delay=.5, retries=0)
        scraper = FincaraizScraper(cfg); scraper.pace = AsyncMock()
        async with async_playwright() as p:
            browser = await p.chromium.launch(); context = await browser.new_context()
            mode = {'repeat': False, 'filter': False}
            async def route(r):
                second = r.request.url.endswith('/pagina2')
                data = pp([property(123 if not second or mode['repeat'] else 456)], 2 if second else 1, more=not second)
                if mode['filter'] and second: data['params']['filters']['order'] = {'value': 99}
                await r.fulfill(body=html(data, REFERENCIA+'/pagina2' if not second else None), content_type='text/html')
            await context.route('**/*', route)
            try:
                scraper.run_id = scraper.store.new_run(REFERENCIA, asdict(cfg))
                await scraper.discover(context)
                assert scraper.store.summary(scraper.run_id)['listing_complete'] and scraper.store.summary(scraper.run_id)['pages'] == 2
                # Reanudar tras dos páginas no vuelve a insertarlas.
                scraper.store.update_search(scraper.run_id, REFERENCIA, complete=False)
                await scraper.discover(context); assert scraper.store.summary(scraper.run_id)['pages'] == 2
                for mode_key in ('repeat', 'filter'):
                    mode[mode_key] = True
                    scraper.run_id = scraper.store.new_run(REFERENCIA, asdict(cfg))
                    with pytest.raises(ExtractionError): await scraper.discover(context)
                    assert not scraper.store.summary(scraper.run_id)['listing_complete']
                    mode[mode_key] = False
                cfg.max_pages = 1
                scraper.run_id = scraper.store.new_run(REFERENCIA, asdict(cfg)); await scraper.discover(context)
                assert not scraper.store.summary(scraper.run_id)['listing_complete']
            finally: await browser.close()
    asyncio.run(prueba())

def test_ejecucion_completa_reutiliza_fichas_y_dispara_matching(tmp_path):
    async def prueba():
        class PortalSintetico(FincaraizScraper):
            async def create_context(self, browser):
                context = await super().create_context(browser)
                async def route(r):
                    second = r.request.url.endswith('/pagina2')
                    data = pp([property(456 if second else 123)], 2 if second else 1, more=not second)
                    if second: data['params']['filters']['page'] = {'value': 2, 'text': 'página 2'}
                    await r.fulfill(body=html(data, REFERENCIA+'/pagina2' if not second else None), content_type='text/html')
                await context.route('**/*', route)
                return context
        cfg = FincaraizConfig(db=str(tmp_path/'fr.sqlite'), url=REFERENCIA, urls=[REFERENCIA], searches={REFERENCIA: config()}, delay=.5)
        for n in range(2):
            scraper = PortalSintetico(cfg); scraper.pace = AsyncMock(); scraper.update_matching = AsyncMock()
            result = await scraper.run()
            assert result['status'] == 'completed' and result['unique'] == 2 and result['pages'] == 2
            assert result['statuses'] == ({'success': 2} if n == 0 else {'unchanged': 2})
            scraper.update_matching.assert_awaited_once()
    asyncio.run(prueba())


def test_snapshot_incluye_fincaraiz_y_excluye_secretos(tmp_path):
    from wasi.durable import empaquetar, restaurar
    folder = tmp_path/'state'; folder.mkdir()
    FincaraizStore(folder/'fincaraiz.sqlite')
    repo = BusquedasSQLite(folder/'metro-consola.sqlite'); repo.guardar_fincaraiz('Sintética', config())
    (folder/'secret.txt').write_text('no publicar', encoding='utf-8')
    dest = tmp_path/'restored'; restaurar(empaquetar(folder), dest)
    assert (dest/'fincaraiz.sqlite').exists() and not (dest/'secret.txt').exists()
    assert BusquedasSQLite(dest/'metro-consola.sqlite').configuracion_fincaraiz(REFERENCIA) == config()
