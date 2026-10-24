"""Inspecciona enlaces públicos del mapa de una ficha, sin contactar al anunciante."""
import asyncio
import json
from pathlib import Path
import sys

from playwright.async_api import async_playwright

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from metro.extraction import sanitize

URL = 'https://www.metrocuadrado.com/inmueble/venta-consultorio-bogota-la-carolina-1-banos-1-garajes/3312-M7166280'


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        try:
            page = await browser.new_page(locale='es-CO')
            errors=[]
            page.on('pageerror',lambda e:errors.append(str(e)))
            await page.goto(URL, wait_until='domcontentloaded', timeout=45000)
            section = page.locator('#location-section')
            await section.wait_for(state='attached', timeout=45000)
            await section.scroll_into_view_if_needed()
            await section.click()
            try:
                await section.locator('.leaflet-container').wait_for(state='attached',timeout=20000)
            except Exception:
                pass
            data = await section.evaluate('''el=>({
                text:el.innerText,
                html:el.outerHTML,
                links:[...el.querySelectorAll('a[href]')].map(a=>({text:a.innerText,href:a.href,html:a.outerHTML})),
                buttons:[...el.querySelectorAll('button')].map(a=>({text:a.innerText,html:a.outerHTML})),
                markers:[...el.querySelectorAll('.leaflet-marker-icon')].map(a=>a.outerHTML),
                embeds:[...el.querySelectorAll('iframe[src]')].map(a=>a.src)
            })''')
            data['errors']=errors
            data['map_links']=await page.locator('a[href]').evaluate_all("els=>els.filter(e=>/mapa|maps|openstreet/i.test(e.href)).map(e=>({text:e.innerText,href:e.href}))")
            out = Path(__file__).resolve().parents[1]/'data/inspection/location.json'
            out.write_text(json.dumps(sanitize(data),ensure_ascii=False,indent=2),encoding='utf-8')
            print(json.dumps(sanitize(data),ensure_ascii=True,indent=2))
        finally:
            await browser.close()


if __name__ == '__main__':
    asyncio.run(main())
