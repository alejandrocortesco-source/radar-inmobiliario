"""Comprueba el nuevo campo y el botón del mapa sobre la interfaz local."""
import asyncio
import json
from pathlib import Path

from playwright.async_api import async_playwright


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        try:
            page = await browser.new_page(viewport={'width':1366,'height':900})
            response = await page.request.get('http://127.0.0.1:8000/api/properties/3312-M7166280')
            assert response.status == 200
            data = (await response.json())['data']
            await page.goto('http://127.0.0.1:8000/properties/3312-M7166280',wait_until='domcontentloaded')
            link = page.get_by_role('link',name='Ver ubicación en mapa ↗',exact=True)
            assert await link.get_attribute('href') == data['normalized']['map_url']
            assert data['fields']['map_url']['derived'] is True
            assert data['normalized']['portal_map_url'].endswith('/3312-M7166280#location-section')
            listing = await page.request.get('http://127.0.0.1:8000/api/properties?limit=1')
            assert 'map_url' in (await listing.json())['items'][0]
            await link.scroll_into_view_if_needed()
            output = Path(__file__).resolve().parents[1]/'data/verification/location.png'
            await page.screenshot(path=str(output))
            print(json.dumps({'status':response.status,'map_url':data['normalized']['map_url'],
                              'portal_map_url':data['normalized']['portal_map_url']},ensure_ascii=True))
        finally:
            await browser.close()


if __name__ == '__main__':
    asyncio.run(main())
