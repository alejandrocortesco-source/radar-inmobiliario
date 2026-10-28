"""Capturas y paridad HTTP sobre el servidor indicado; no modifica registros."""
import argparse
import hashlib
import json
from pathlib import Path
from urllib.parse import urlencode
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', default='http://127.0.0.1:8040')
    parser.add_argument('--oportunidad', required=True)
    parser.add_argument('--salida', default='consola/docs/evidencia-v04')
    args = parser.parse_args()
    out = Path(args.salida)
    out.mkdir(parents=True, exist_ok=True)
    root = Path(__file__).resolve().parents[2]
    bases = [root / 'scraper/data/metro.sqlite', root / 'scraper/data/metro-consola.sqlite']
    def huellas():
        return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in bases if p.exists()}
    antes = huellas()
    evidence = {'url': args.url, 'oportunidad': args.oportunidad, 'densidad': [], 'errores_js': []}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.on('pageerror', lambda error: evidence['errores_js'].append(str(error)))
        for context, path in [('catalogo', '/v0.4/'), ('matching', '/v0.4/?oportunidad=' + args.oportunidad)]:
            for w, h in [(1366, 768), (1440, 900), (390, 844)]:
                page.set_viewport_size({'width': w, 'height': h})
                assert page.goto(args.url + path).status == 200
                page.screenshot(path=str(out / f'{context}-{w}x{h}.png'))
                measure = page.evaluate('''() => ({ancho:document.documentElement.scrollWidth,
                  tablas:document.querySelectorAll('main table.catalog-table').length,
                  filas:[...document.querySelectorAll('.catalog-table tbody tr')].filter(r=>{
                    const b=r.getBoundingClientRect();return b.top>=0&&b.bottom<=innerHeight}).length,
                  fuenteTabla:getComputedStyle(document.querySelector('.catalog-table td')).fontSize})''')
                assert measure['ancho'] <= w and measure['tablas'] == 1
                evidence['densidad'].append(dict(contexto=context, viewport_ancho=w, alto=h, **measure))
        page.goto(args.url + '/v0.4/?panel=nueva')
        page.screenshot(path=str(out / 'editor-390x844.png'))
        page.locator('#editor [data-close]').click()
        page.locator('.property-link').first.click()
        page.locator('#surface .detail').wait_for()
        page.screenshot(path=str(out / 'detalle-390x844.png'))
        page.goto(args.url + '/consola/?oportunidad=' + args.oportunidad)
        # Abrir todos los apartados para contrastar contenido y acciones con el código.
        inventory = page.locator('details').evaluate_all('''ds=>ds.map(d=>{d.open=true;
          return {seccion:d.querySelector('summary').textContent.trim(),
            campos:[...d.querySelectorAll('input,select,textarea')].map(c=>c.name),
            acciones:[...d.querySelectorAll('button')].map(c=>c.textContent.trim())}})''')
        (out / 'inventario-v03.json').write_text(json.dumps(inventory, ensure_ascii=False, indent=2), encoding='utf-8')
        matching = page.request.get(args.url + '/api/oportunidades/' + args.oportunidad + '/coincidencias').json()
        evidence['matching'] = {'candidatos': len(matching),
            'confirmados': sum(not r['pendientes'] for r in matching)}
        sequences = []
        for version in ['consola', 'v0.4']:
            seq = []
            for offset in range(0, len(matching), 48):
                query = urlencode(dict(oportunidad=args.oportunidad, match_limit=48, match_offset=offset))
                response = page.request.get(f'{args.url}/{version}/?{query}')
                assert response.status == 200
                soup = BeautifulSoup(response.text(), 'html.parser')
                seq += [r['data-match-id'] for r in soup.select('[data-match-id]')]
            sequences.append(seq)
        assert sequences[0] == sequences[1] and len(sequences[0]) == len(matching)
        evidence['secuencia_completa_igual'] = True
        evidence['sha256_secuencia'] = hashlib.sha256(json.dumps(sequences[0]).encode()).hexdigest()
        a = page.request.get(args.url + '/consola/exportar.csv').body()
        b = page.request.get(args.url + '/v0.4/exportar.csv').body()
        assert a == b
        evidence['exportacion_identica_sha256'] = hashlib.sha256(a).hexdigest()
        browser.close()
    assert antes == huellas()
    evidence['huellas_originales_sin_cambios'] = antes
    assert not evidence['errores_js']
    (out / 'verificacion.json').write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(evidence, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
