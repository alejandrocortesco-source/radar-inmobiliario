import asyncio
import json
from pathlib import Path
from urllib.parse import urlsplit
from playwright.async_api import async_playwright
from inspect_site import URL

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        captures = []
        async def response(r):
            if 'metrocuadrado.com' in urlsplit(r.url).netloc and 'json' in r.headers.get('content-type',''):
                try:
                    data = await r.json()
                    # Sólo respuestas de resultados públicos, sin cabeceras ni credenciales.
                    if isinstance(data,dict) and ('results' in data or 'propertyId' in data):
                        captures.append({'path':urlsplit(r.url).path,'data':data})
                except Exception:
                    pass
        page.on('response',response)
        await page.goto(URL,wait_until='domcontentloaded')
        await page.evaluate('window.scrollTo(0, document.body.scrollHeight / 2)')
        await page.locator('.rc-pagination-item-active').wait_for(state='attached',timeout=60000)
        print('BEFORE',await page.locator('.rc-pagination-item-active').inner_text())
        await page.locator('.rc-pagination-next').click(force=True)
        await page.wait_for_function("document.querySelector('.rc-pagination-item-active')?.textContent === '2'")
        await page.wait_for_timeout(3000)
        print('AFTER',page.url,await page.locator('.rc-pagination-item-active').inner_text())
        out=Path(__file__).resolve().parents[1]/'data/inspection'
        out.mkdir(parents=True,exist_ok=True)
        (out/'pagination.json').write_text(json.dumps(captures,ensure_ascii=False,indent=2),encoding='utf-8')
        print([(x['path'], list(x['data']),len(x['data'].get('results',[]))) for x in captures])
        await browser.close()

asyncio.run(main())
