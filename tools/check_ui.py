import asyncio
from pathlib import Path
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser=await p.chromium.launch()
        page=await browser.new_page(viewport={'width':1440,'height':1000})
        errors=[]
        page.on('pageerror',lambda e:errors.append(str(e)))
        await page.goto('http://127.0.0.1:8000/',wait_until='domcontentloaded')
        await page.get_by_role('heading',name='Tu inventario de inmuebles').wait_for()
        Path('data/verification').mkdir(parents=True,exist_ok=True)
        await page.screenshot(path='data/verification/dashboard.png',full_page=True)
        await page.locator('tbody a').first.click()
        await page.get_by_role('heading',name='Datos normalizados').wait_for()
        await page.screenshot(path='data/verification/detail.png',full_page=True)
        await page.set_viewport_size({'width':390,'height':844})
        await page.goto('http://127.0.0.1:8000/',wait_until='domcontentloaded')
        await page.screenshot(path='data/verification/mobile.png',full_page=True)
        print({'page_errors':errors,'title':await page.title(),'mobile_width':await page.evaluate('document.documentElement.scrollWidth')})
        assert not errors
        await browser.close()

asyncio.run(main())
