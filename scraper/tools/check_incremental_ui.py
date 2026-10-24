"""Verifica las vistas incrementales de la interfaz local con Chromium."""
import asyncio
from pathlib import Path
from playwright.async_api import async_playwright


async def main():
    async with async_playwright() as p:
        browser=await p.chromium.launch()
        try:
            page=await browser.new_page(viewport={'width':1366,'height':900})
            errors=[]
            page.on('pageerror',lambda e:errors.append(str(e)))
            await page.goto('http://127.0.0.1:8000/',wait_until='domcontentloaded')
            await page.get_by_role('heading',name='Actualización incremental').wait_for()
            await page.select_option('select[name="status"]','unchanged')
            await page.get_by_role('button',name='Filtrar',exact=True).click()
            assert await page.locator('tbody tr').count()>0
            out=Path(__file__).resolve().parents[1]/'data/verification'
            await page.screenshot(path=str(out/'incremental-dashboard.png'),full_page=True)
            await page.goto('http://127.0.0.1:8000/catalog',wait_until='domcontentloaded')
            await page.get_by_role('heading',name='Catálogo y disponibilidad').wait_for()
            response=await page.request.get('http://127.0.0.1:8000/api/catalog')
            assert (await response.json())['total']>=427
            await page.locator('tbody a').first.click()
            await page.get_by_role('heading',name='Verificación en listados').wait_for()
            await page.set_viewport_size({'width':390,'height':844})
            await page.goto('http://127.0.0.1:8000/',wait_until='domcontentloaded')
            await page.screenshot(path=str(out/'incremental-mobile.png'),full_page=True)
            assert not errors
            print({'page_errors':errors,'mobile_width':await page.evaluate('document.documentElement.scrollWidth')})
        finally:
            await browser.close()


if __name__=='__main__':
    asyncio.run(main())
