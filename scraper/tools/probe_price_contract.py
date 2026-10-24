"""Revisa cómo el listado público formatea moneda; no abre fichas."""
import asyncio
import json
import re
from pathlib import Path
from playwright.async_api import async_playwright


async def main():
    findings = []
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        try:
            page = await browser.new_page()
            tasks = []
            async def inspect(response):
                if response.request.resource_type == 'script' and '/ecs-results/' in response.url:
                    try:
                        code = await response.text()
                        for match in re.finditer(r'currency:\s*[\"\x27]COP|currency:[^,}]{0,35}|es-CO|mvalorventa', code):
                            findings.append({'script': response.url.split('?')[0],
                                             'excerpt': code[max(0,match.start()-100):match.end()+180]})
                    except Exception:
                        pass
            def capture(response):
                tasks.append(asyncio.create_task(inspect(response)))
            page.on('response',capture)
            await page.goto('https://www.metrocuadrado.com/inmuebles/venta/bogota/la-carolina?search=form',wait_until='domcontentloaded',timeout=45000)
            await page.locator('.property-card__detail-price').first.wait_for(state='attached',timeout=45000)
            await asyncio.gather(*tasks)
            out = Path(__file__).resolve().parents[1]/'data/inspection/price-contract.json'
            out.write_text(json.dumps(findings,ensure_ascii=False,indent=2),encoding='utf-8')
            print(json.dumps(findings,ensure_ascii=True,indent=2))
        finally:
            await browser.close()


if __name__ == '__main__':
    asyncio.run(main())
