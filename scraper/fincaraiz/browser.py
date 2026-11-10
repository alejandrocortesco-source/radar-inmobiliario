"""Navegación normal del portal; validación conservadora de cobertura."""
import json
from urllib.parse import urlsplit, parse_qsl
from playwright.async_api import async_playwright
from catalogo.fuentes.fincaraiz import validar_url, criterios
from metro.scraper import check_access
from metro.extraction import ExtractionError
from .extraction import enlace


async def leer(page):
    await check_access(page)
    try:
        return json.loads(await page.locator('#__NEXT_DATA__').inner_text(timeout=10000))['props']['pageProps']
    except (ValueError, KeyError) as exc:
        raise ExtractionError('Datos públicos Next.js ausentes o incompatibles') from exc


def listado(pp):
    try:
        filtros = dict(pp['params']['filters'])
        batch = pp['fetchResult']['searchFast']
        info = batch['paginatorInfo']
        page_filter = filtros.pop('page', None)
        if page_filter is not None and page_filter.get('value') != info['currentPage']:
            raise ValueError('Filtro de página contradictorio')
        links = [enlace(p) for p in batch['data']]
        for k in ('currentPage', 'total', 'lastPage'):
            if type(info[k]) is not int or info[k] < 0:
                raise ValueError(k)
        if not isinstance(info['hasMorePages'], bool) or len({i['id'] for i in links}) != len(links):
            raise ValueError('Duplicados o fin ambiguo')
        if (not links and info['total'] != 0) or (links and info['total'] == 0):
            raise ValueError('Listado incompleto')
        return filtros, links, info
    except (KeyError, TypeError, ValueError) as exc:
        raise ExtractionError('Respuesta Fincaraíz incompleta: no se confirma búsqueda vacía') from exc


async def siguiente(page, base, info):
    if not info['hasMorePages']:
        return None
    # Solo enlaces efectivamente publicados por el portal, con alcance idéntico.
    urls = await page.locator('a[href]').evaluate_all('(els)=>els.map(e=>e.href)')
    p = urlsplit(base)
    expected = p.path.rstrip('/') + '/pagina' + str(info['currentPage'] + 1)
    matches = {u for u in urls if urlsplit(u).hostname == p.hostname and urlsplit(u).path == expected
               and sorted(parse_qsl(urlsplit(u).query, keep_blank_values=True)) == sorted(parse_qsl(p.query, keep_blank_values=True))}
    if len(matches) != 1:
        raise ExtractionError('No existe un enlace siguiente inequívoco que conserve los filtros')
    return matches.pop()


async def verificar(url, expected=None):
    original = url
    url = validar_url(url)
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        try:
            context = await browser.new_context(locale='es-CO')
            await context.route('**/*', lambda route: route.abort() if route.request.resource_type in ('image', 'font', 'media') else route.continue_())
            page = await context.new_page()
            r = await page.goto(url, wait_until='domcontentloaded', timeout=45000)
            await check_access(page, r)
            pp = await leer(page)
            filtros, _, info = listado(pp)
            effective = validar_url(page.url)
            if info['currentPage'] != 1:
                raise ExtractionError('La URL no representa la primera página de resultados')
            if expected is not None and filtros != expected:
                raise ExtractionError('El portal cambió los criterios guardados; revisa la URL filtrada')
            try:
                cr = criterios(filtros)
            except ValueError:
                cr = None  # El modo URL admite otras combinaciones explícitas.
            return {'version': 1, 'url_original': original, 'url_efectiva': effective, 'filtros': filtros, 'criterios': cr}
        finally:
            await browser.close()
