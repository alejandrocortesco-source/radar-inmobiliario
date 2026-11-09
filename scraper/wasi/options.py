"""Lectura de opciones del portal, sin buscar ni capturar anuncios."""
from catalogo.fuentes.wasi import SELECTS, GEO, clave_opciones
from .auth import autenticar, acceso
from .browser import seleccionar, control


async def actualizar_opciones(repo, padres, headed=False):
    from playwright.async_api import async_playwright
    from .auth import RED
    registros = {}
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=not headed)
        try:
            context = await browser.new_context(locale='es-CO')
            async def recursos(route):
                if route.request.resource_type in ('image', 'font', 'media'):
                    await route.abort()
                else:
                    await route.fallback()
            await context.route('**/*', recursos)
            await autenticar(context)
            page = await context.new_page()
            await page.goto(RED, wait_until='domcontentloaded')
            await acceso(page)
            for campo in GEO:
                await page.wait_for_function('''c=>{const e=document.querySelector('.advanced-search #'+c);return e && ![...e.options].some(o=>/Cargando/.test(o.text))}''', arg=campo)
                items = await page.locator(control(campo)).locator('option').evaluate_all('es=>es.filter(e=>e.value).map(e=>({value:e.value,label:e.text.trim()}))')
                registros[clave_opciones(campo, padres)] = items
                if campo in GEO:
                    if campo in padres:
                        if not padres[campo]:
                            await seleccionar(page, campo, '', None, 45000)
                            continue
                        elegido = next((o for o in items if o['value'] == padres[campo]), None)
                        if not elegido:
                            raise ValueError('Opción padre no disponible: ' + campo)
                        await seleccionar(page, campo, elegido['value'], elegido['label'], 45000)
                    else:
                        # No guardar descendientes bajo padres que no se eligieron.
                        break
            # Los criterios no geográficos no dependen de los padres elegidos.
            for campo in SELECTS[len(GEO):]:
                registros[clave_opciones(campo, {})] = await page.locator(control(campo)).locator('option').evaluate_all('es=>es.filter(e=>e.value).map(e=>({value:e.value,label:e.text.trim()}))')
            registros['business_type_id:'] = [o for o in registros['business_type_id:'] if o['value'] in ('1', '2', '5')]
            repo.guardar_opciones_wasi(registros)
        finally:
            await browser.close()
    return {'opciones_actualizadas': len(registros), 'capturas': 0}
