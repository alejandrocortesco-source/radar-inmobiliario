"""Inspección explícita; no guarda cookies, cabeceras ni estado de sesión."""
import asyncio
import json
import re
from pathlib import Path
from urllib.parse import urlsplit
from playwright.async_api import async_playwright

URL = 'https://www.metrocuadrado.com/inmuebles/venta/bogota/la-carolina?search=form'

async def main():
    out = Path('data/inspection')
    out.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        try:
            response = await page.goto(URL, wait_until='domcontentloaded', timeout=60000)
            await page.wait_for_timeout(5000)  # Solo diagnóstico, no condición del scraper.
            text = await page.locator('body').inner_text()
            await page.evaluate('window.scrollTo(0, document.body.scrollHeight / 2)')
            await page.wait_for_timeout(4000)
            result = {'url': page.url, 'status': response.status if response else None,
                      'title': await page.title(), 'text': text[:14000],
                      'links': await page.locator('a[href]').evaluate_all('(els)=>els.map(e=>({text:e.innerText,href:e.href}))'),
                      'scripts': await page.locator('script').evaluate_all('(els)=>els.map(e=>({id:e.id,type:e.type,src:e.src,length:e.textContent.length}))')}
            result['scripts'] = [{**s,'src':urlsplit(s['src']).path} for s in result['scripts']
                                 if not s['src'] or urlsplit(s['src']).hostname == 'www.metrocuadrado.com']
            (out/'listing.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
            def clean(v):
                if isinstance(v, dict):
                    return {k: clean(x) for k, x in v.items() if not re.search(r'token|cookie|session|secret|password|api.?key|authorization|recaptcha|nonce', k, re.I)}
                if isinstance(v, list):
                    return [clean(x) for x in v]
                return v
            async def structured():
                scripts = await page.locator('script:not([src])').all_text_contents()
                records = []
                for script in scripts:
                    if 'self.__next_f.push(' not in script:
                        continue
                    for chunk in script.split('self.__next_f.push(')[1:]:
                        try:
                            arr, _ = json.JSONDecoder().raw_decode(chunk)
                            if len(arr) > 1 and isinstance(arr[1], str):
                                for line in arr[1].splitlines():
                                    payload = line.partition(':')[2]
                                    try:
                                        records.append(clean(json.loads(payload)))
                                    except ValueError:
                                        pass
                        except ValueError:
                            pass
                return records
            records = await structured()
            (out/'next.json').write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding='utf-8')
            dom = await page.evaluate('''()=>({cards:[...document.querySelectorAll('a[href*="/inmueble/"]')].slice(0,6).map(e=>e.parentElement.outerHTML),buttons:[...document.querySelectorAll('button, [aria-current], [class*="pagination"], [class*="Pagination"]')].map(e=>e.outerHTML)})''')
            (out/'dom.json').write_text(json.dumps(dom, ensure_ascii=False, indent=2), encoding='utf-8')
            links = [x['href'] for x in result['links'] if '/inmueble/' in x['href']][:3]
            def walk(v):
                if isinstance(v,dict):
                    yield v
                    for x in v.values():
                        yield from walk(x)
                elif isinstance(v,list):
                    for x in v:
                        yield from walk(x)
            for kind in ('Oficina','Consultorio'):
                item = next((v for v in walk(records) if isinstance(v.get('mtipoinmueble'),dict) and v['mtipoinmueble'].get('nombre') == kind and v.get('link')),None)
                if item:
                    links.append('https://www.metrocuadrado.com'+item['link'])
            for i, url in enumerate(links):
                await page.goto(url, wait_until='domcontentloaded', timeout=60000)
                await page.wait_for_timeout(3000)
                detail = {'url': page.url, 'text': await page.locator('body').inner_text(),
                          'next': await structured(),
                          'ld': await page.locator('script[type="application/ld+json"]').all_text_contents(),
                          'headings': await page.locator('h1,h2,h3').all_text_contents()}
                (out/f'detail-{i}.json').write_text(json.dumps(detail, ensure_ascii=False, indent=2), encoding='utf-8')
            await page.screenshot(path=str(out/'listing.png'), full_page=True)
            print(json.dumps({'status':result['status'],'title':result['title'],'inspected_details':len(links)}, ensure_ascii=False))
        finally:
            await browser.close()

if __name__ == '__main__':
    asyncio.run(main())
