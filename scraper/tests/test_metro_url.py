"""Descubrimiento real del motor con ruta por tipos y transporte Chromium interceptado."""
import asyncio
from dataclasses import asdict
import json
from unittest.mock import AsyncMock

from playwright.async_api import async_playwright
from metro.prices import search_identity
from metro.scraper import Config, Scraper


def test_descubrimiento_url_tipos_con_respuesta_sintetica(tmp_path):
    async def prueba():
        url = 'https://www.metrocuadrado.com/apartamento-casa/arriendo/bogota/la-carolina?search=form'
        cfg = Config(db=str(tmp_path/'metro.sqlite'), urls=[url], delay=.5, retries=0)
        motor = Scraper(cfg)
        motor.pace = AsyncMock()
        motor.run_id = motor.store.new_run(url, asdict(cfg))
        item = {'midinmueble':'1-M1', 'link':'/inmueble/apartamento/1-M1',
                'mtiponegocio':'arriendo', 'mvalorarriendo':2500000}
        batch = {'results':[item], 'highlights':[], 'totalHits':1, 'totalEntries':1}
        stream = '0:'+json.dumps({'initialResults':batch})+'\n'
        html = ('<html><body><div class="property-list__results">'
                '<a href="/inmueble/apartamento/1-M1">Apartamento sintético</a></div>'
                '<span class="rc-pagination-item-active">1</span>'
                '<button class="rc-pagination-next" aria-disabled="true">Siguiente</button>'
                '<script>self.__next_f=[];self.__next_f.push('+json.dumps([1,stream])+')</script></body></html>')
        solicitudes = []
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            context = await browser.new_context()
            async def responder(route):
                solicitudes.append(route.request.url)
                assert route.request.url == url
                await route.fulfill(body=html, content_type='text/html')
            await context.route('**/*', responder)
            try:
                await motor.discover(context, url)
                resumen = motor.store.summary(motor.run_id)
                assert resumen['pages'] == 1 and resumen['unique'] == 1 and resumen['listing_complete']
                pagina = motor.store.pages(motor.run_id)[0]
                assert pagina['search_url'] == search_identity(url)
                assert json.loads(pagina['links_json'])[0]['raw']['mvalorarriendo'] == 2500000
                assert solicitudes == [url]  # No reescribir filtros ni navegar a /inmuebles/.
            finally:
                await browser.close()
    asyncio.run(prueba())
