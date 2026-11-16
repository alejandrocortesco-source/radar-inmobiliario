"""Listado Metrocuadrado: Chromium con toda la red interceptada y SQLite sintético."""
import asyncio
import json
from dataclasses import asdict
from urllib.parse import urlsplit

import pytest
from playwright.async_api import async_playwright

from metro.extraction import ExtractionError
from metro.scraper import Config, Scraper, is_listing_response_url
from test_incremental import A, listing, member, seed


@pytest.mark.parametrize('path', ['/rest-search/search', '/api/rest-search/search'])
@pytest.mark.parametrize('query', ['', '?size=50&from=50&city=bogota'])
def test_exact_listing_endpoint_accepts_both_paths_and_queries(path, query):
    assert is_listing_response_url('https://www.metrocuadrado.com' + path + query)


@pytest.mark.parametrize('url', [
    'https://example.com/api/rest-search/search',
    'https://www.metrocuadrado.com.example.com/api/rest-search/search',
    'https://metrocuadrado.com/api/rest-search/search',
    'https://www.metrocuadrado.com/api/rest-search/search/seoelements',
    'https://www.metrocuadrado.com/rest-search/search/',
    'https://www.metrocuadrado.com/other?next=/api/rest-search/search',
    'https://www.metrocuadrado.com/prefix/rest-search/search',
])
def test_foreign_host_or_path_is_rejected(url):
    assert not is_listing_response_url(url)


def result(pid):
    return {'midinmueble': pid, 'link': '/inmueble/apartamento/' + pid}


def test_chromium_listing_response_and_coverage(tmp_path):
    """Ejercita el listener real, avance y cobertura; nunca abre fichas ni Internet."""
    cases = [
        ('old', '/rest-search/search', 'valid', None),
        ('new-query', '/api/rest-search/search?size=50&from=50', 'valid', None),
        ('foreign-host', 'https://other.example/api/rest-search/search', 'valid', 'Paginador sin cambio'),
        ('foreign-path', '/api/rest-search/search/seoelements', 'valid', 'Paginador sin cambio'),
        ('invalid-root', '/api/rest-search/search', 'invalid-root', 'Paginador sin cambio'),
        ('invalid-results', '/api/rest-search/search', 'invalid-results', 'Paginador sin cambio'),
        ('invalid-json', '/api/rest-search/search', 'invalid-json', 'Paginador sin cambio'),
        ('same-active', '/api/rest-search/search', 'same-active', 'Paginador sin cambio'),
        ('same-main', '/api/rest-search/search', 'same-main', 'Paginador sin cambio'),
        ('only-highlight-changes', '/api/rest-search/search', 'only-highlight-changes', 'Paginador sin cambio'),
        ('wrong-dom', '/api/rest-search/search', 'wrong-dom', 'DOM y respuesta'),
        ('wrong-count', '/api/rest-search/search', 'wrong-count', 'Cobertura incompleta'),
    ]

    async def exercise(context, case):
        name, endpoint, mode, error = case
        cfg = Config(db=str(tmp_path / (name + '.sqlite')), timeout=1000, delay=0.5)
        scraper = Scraper(cfg)
        assert cfg.max_pages is None and cfg.max_details is None
        # Un inmueble anterior ausente del nuevo listado no puede retirarse si falla cobertura.
        seed(scraper.store, {A: [listing('9-M9')]})
        previous_member = member(scraper.store, pid='9-M9')
        scraper.run_id = scraper.store.new_run(A, asdict(cfg))
        initial = {'results': [result('1-M1')], 'highlights': [result('3-M3')],
                   'totalHits': 3 if mode == 'wrong-count' else 2, 'totalEntries': 2}
        same_main = mode in ('same-main', 'only-highlight-changes')
        second = {**initial, 'results': [result('1-M1' if same_main else '2-M2')],
                  'highlights': [result('4-M4' if mode == 'only-highlight-changes' else '3-M3')]}
        payload = {'invalid-root': [], 'invalid-results': {'results': {}},
                   'invalid-json': 'not JSON'}.get(mode, second)
        body = payload if mode == 'invalid-json' else json.dumps(payload)
        stream = '1:' + json.dumps({'initialResults': initial}) + '\n'
        script = 'self.__next_f.push(' + json.dumps([1, stream]) + ')'
        dom_id = '8-M8' if mode == 'wrong-dom' else ('1-M1' if same_main else '2-M2')
        html = f"""<html><body>
            <script>self.__next_f = []; {script}</script>
            <span class="rc-pagination-item-active">1</span>
            <div class="property-list__results"><a href="/inmueble/apartamento/1-M1">Inicial</a></div>
            <button class="rc-pagination-next" aria-disabled="false">Siguiente</button>
            <script>
            document.querySelector('button').onclick = async () => {{
                await fetch({json.dumps(endpoint)}).then(r => r.text());
                document.querySelector('.rc-pagination-item-active').textContent = {json.dumps('1' if mode == 'same-active' else '2')};
                document.querySelector('a').href = '/inmueble/apartamento/{dom_id}';
                document.querySelector('button').setAttribute('aria-disabled', 'true');
            }};
            </script></body></html>"""
        requests = []

        async def route(request_route):
            url = request_route.request.url
            requests.append(url)
            if url == A:
                await request_route.fulfill(status=200, content_type='text/html', body=html)
            elif urlsplit(url).path in ('/rest-search/search', '/api/rest-search/search',
                                      '/api/rest-search/search/seoelements'):
                await request_route.fulfill(status=200, content_type='application/json', body=body,
                                            headers={'Access-Control-Allow-Origin': '*'})
            else:
                pytest.fail('Solicitud inesperada en prueba aislada: ' + url)

        await context.route('**/*', route)
        try:
            if error:
                with pytest.raises(ExtractionError, match=error):
                    await scraper.discover(context)
                assert not scraper.store.searches(scraper.run_id)[0]['listing_complete'], name
                # Incluso un estado de run mal marcado no evita la guarda de cobertura.
                scraper.store.update_run(scraper.run_id, status='completed')
                assert not scraper.store.finalize_absences(scraper.run_id), name
                assert member(scraper.store, pid='9-M9') == previous_member, name
            else:
                await scraper.discover(context)
                assert scraper.store.searches(scraper.run_id)[0]['listing_complete'], name
                pages = scraper.store.pages(scraper.run_id)
                assert [p['active'] for p in pages] == ['1', '2']
                assert pages[0]['fingerprint'] != pages[1]['fingerprint']
                links = [json.loads(p['links_json']) for p in pages]
                assert [[x['id'] for x in items if x['group'] == 'results'] for items in links] == [['1-M1'], ['2-M2']]
                # Destacado idéntico en ambas páginas: no bloquea el avance ni aumenta totalHits.
                assert [[x['id'] for x in items if x['group'] == 'highlights'] for items in links] == [['3-M3'], ['3-M3']]
            assert len(requests) == 2, (name, requests)
            assert not context.pages  # discover cierra su página también ante errores.
        finally:
            await context.unroute('**/*', route)

    async def run():
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch()
            try:
                for case in cases:
                    context = await browser.new_context(service_workers='block')
                    try:
                        await exercise(context, case)
                    finally:
                        await context.close()
            finally:
                await browser.close()

    asyncio.run(run())
