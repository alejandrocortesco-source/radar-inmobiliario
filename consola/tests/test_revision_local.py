"""Ensayo de entrega: navegador real, proveedor falso, reinicio y bases aisladas."""
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from contextlib import contextmanager
from uuid import uuid4

import httpx
from playwright.sync_api import expect


RAIZ = Path(__file__).resolve().parents[2]


@contextmanager
def revision(datos):
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    url = f'http://127.0.0.1:{port}'
    entorno = dict(os.environ)
    for k in ('K_SERVICE', 'K_REVISION', 'K_CONFIGURATION'):
        entorno.pop(k, None)
    with (datos.parent / f'servidor-{port}.log').open('w', encoding='utf-8') as log:
        proceso = subprocess.Popen([sys.executable, str(RAIZ / 'consola/tools/revision_local.py'),
            '--datos', str(datos), '--port', str(port)], cwd=RAIZ, env=entorno,
            stdout=log, stderr=log, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        try:
            for _ in range(150):
                assert proceso.poll() is None, 'El servidor terminó: consultar log sintético'
                try:
                    if httpx.get(url+'/health', timeout=1).status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                time.sleep(.1)
            else:
                raise AssertionError('La instancia aislada no inició')
            yield url, json.loads((datos / 'manifest.json').read_text(encoding='utf-8'))
        finally:
            proceso.terminate()
            try:
                proceso.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proceso.kill()
                proceso.wait(timeout=5)


def catalogos(datos):
    return {p.name:hashlib.sha256(p.read_bytes()).hexdigest()
            for p in datos.glob('*.sqlite') if p.name != 'crm.sqlite'}


def test_entrega_navegador_integraciones_y_reinicio(tmp_path, chromium):
    datos = tmp_path / 'revision'
    if not datos.resolve().is_relative_to(RAIZ / '.tmp'):
        datos = RAIZ / '.tmp' / ('revision-test-'+str(uuid4())) / 'datos'
        datos.parent.mkdir(parents=True)
        (tmp_path / 'ruta-revision.txt').write_text(str(datos), encoding='utf-8')
    errores, fallidas, externas, consola = [], [], [], []
    contexto = chromium.new_context(viewport={'width':1440, 'height':900}, reduced_motion='reduce')
    page = contexto.new_page()
    page.on('pageerror', lambda e: errores.append(str(e)))
    page.on('requestfailed', lambda r: fallidas.append(r.url))
    page.on('console', lambda m: consola.append(m.text) if m.type == 'error' else None)
    def offline(route):
        if not route.request.url.startswith('http://127.0.0.1:'):
            externas.append(route.request.url)
            route.abort()
        else:
            route.continue_()
    contexto.route('**/*', offline)
    try:
        with revision(datos) as (url, m), httpx.Client(base_url=url, headers={'Origin':url}) as api:
            antes = catalogos(datos)
            # Guardar y navegar no autoriza ninguna evaluación externa.
            page.goto(url+'/v0.6/nuevo')
            page.locator('#crm_nombre').fill('Lucía Prueba Local')
            page.locator('#crm_telefono').fill('TEST-001')
            page.locator('#crm_tipo').select_option('apartamento')
            page.locator('#crm_ciudad').select_option(label='Bogotá')
            page.locator('#crm_presupuesto').fill('450000000')
            page.locator('#crm_presupuesto_min').fill('350000000')
            page.locator('#crm_habitaciones_min').fill('2')
            page.locator('#crm_habitaciones_max').fill('3')
            page.locator('[data-location-picker] > summary').click()
            page.locator('[data-location-row][data-city="bogota"][data-key="barrio:la carolina"] input').check()
            page.locator('[data-location-done]').click()
            page.get_by_role('button', name='Confirmar y guardar oportunidad').click()
            expect(page.locator('h1')).to_have_text('Lucía Prueba Local')
            expect(page.locator('[data-candidate]')).to_have_count(5)
            page.get_by_text('Editar cliente', exact=True).click()
            page.locator('.client-edit input[name=nombre]').fill('Lucía Prueba Editada')
            page.locator('.client-edit input[name=telefono]').fill('TEST-002')
            page.get_by_role('button', name='Guardar cliente', exact=True).click()
            expect(page.locator('h1')).to_have_text('Lucía Prueba Editada')
            assert not (datos / 'simulaciones.jsonl').exists()
            diag = api.get('/api/oportunidades/'+m['clientes'][0]['oportunidad']+'/diagnostico').json()
            assert {k:diag[k] for k in ('total_catalogo','compatibles','pendientes','incompatibles')} == {
                'total_catalogo':36, 'compatibles':3, 'pendientes':2, 'incompatibles':31}
            assert {r['inmueble']['titulo'][5] for r in diag['resultados']} == set('ABCJL')
            assert any(d['id_original']=='004' and 'Presupuesto en COP' in d['motivos'] for d in diag['descartes'])
            # La misma captura verifica filtros, orden global, CSV y nombres literales.
            params = '?ciudad=Bogot%C3%A1&operacion=venta&precio_min=350000000&precio_max=450000000&orden=precio_desc&limit=12'
            page.goto(url+'/v0.4/'+params)
            rows = list(csv.DictReader(io.StringIO(api.get('/v0.4/exportar.csv'+params).text.lstrip('\ufeff')), delimiter=';'))
            assert len(rows) == 7 and all(r['Moneda']=='COP' for r in rows)
            assert [int(r['Precio']) for r in rows] == sorted([int(r['Precio']) for r in rows], reverse=True)
            page.locator('[data-advertiser]').first.click()
            expect(page.locator('[data-advertiser-content]')).to_contain_text('Agencia Demo')
            expect(page.locator('[data-advertiser-content]')).to_contain_text('No hay datos de contacto disponibles.')
            # Renombrar y desactivar una búsqueda conserva capturas y revisiones.
            page.goto(url+'/v0.6/')
            page.locator('.registered-sources > summary').click()
            fr = page.locator('[data-registered-source]').filter(has_text='Demo Fincaraíz')
            fr.get_by_role('link', name='Editar búsqueda').click()
            page.locator('.source-form input[name=nombre]').fill('Demo Fincaraíz revisada')
            page.get_by_role('button', name='Guardar fuente').click()
            fr = page.locator('[data-registered-source]').filter(has_text='Demo Fincaraíz revisada')
            fr.get_by_role('button', name='Desactivar', exact=True).click()
            page.locator('.registered-sources > summary').click()
            fr.get_by_role('button', name='Activar', exact=True).click()
            assert catalogos(datos) == antes
            assert not (datos / 'simulaciones.jsonl').exists()
            # REST real del adaptador: cuerpo JSON simulado, validación local y caché.
            bien = m['clientes'][1]
            page.goto(url+'/v0.6/clientes/'+bien['cliente'])
            page.get_by_role('button', name='Evaluar con Gemini', exact=True).click()
            expect(page.locator('.ai-explanation')).to_have_count(5, timeout=15000)
            expect(page.locator('.ai-explanation').first).to_contain_text('SIMULADO')
            page.get_by_role('button', name='Evaluar con Gemini', exact=True).click()
            expect(page.locator('[data-match-status]')).to_contain_text('sin nuevas llamadas', timeout=15000)
            assert len((datos/'simulaciones.jsonl').read_text().splitlines()) == 1
            mal = m['clientes'][2]
            page.goto(url+'/v0.6/clientes/'+mal['cliente'])
            page.get_by_role('button', name='Evaluar con Gemini', exact=True).click()
            expect(page.locator('[data-match-status]')).to_contain_text('límite de uso', timeout=15000)
            expect(page.locator('[data-candidate]')).to_have_count(5)
            expect(page.locator('.ai-explanation')).to_have_count(0)
            eventos = [json.loads(x) for x in (datos/'simulaciones.jsonl').read_text().splitlines()]
            assert [e['http'] for e in eventos] == [200, 429]
            # Escrituras rechazadas, vacíos y entradas maliciosas sin efectos laterales.
            assert api.post('/api/clientes', json={'nombre':'Intruso'}, headers={'Origin':'https://evil.test'}).status_code == 403
            assert api.post('/api/clientes', json={'nombre':''}).status_code == 422
            vacio = '/v0.6/clientes/'+m['clientes'][3]['cliente']
            page.goto(url+vacio)
            expect(page.get_by_text('No hay candidatos con estos criterios.', exact=False)).to_be_visible()
            for ancho, alto in [(1440,900), (768,1024), (390,844)]:
                page.set_viewport_size({'width':ancho, 'height':alto})
                for ruta in ['/v0.6/', '/v0.6/nuevo', '/v0.6/clientes/'+bien['cliente'], '/v0.4/']:
                    page.goto(url+ruta)
                    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), (ancho, ruta)
                    expect(page.locator('[data-revision-local]')).to_be_visible()
                page.screenshot(path=str(tmp_path / f'catalogo-{ancho}.png'), full_page=True)
            assert catalogos(datos) == antes
            creado = next(c for c in api.get('/api/clientes').json() if c['nombre']=='Lucía Prueba Editada')
            assert creado['telefono'] == 'TEST-002'
        # Proceso nuevo, mismas cuatro bases: cliente, decisiones, búsqueda y caché siguen.
        with revision(datos) as (url, mismo), httpx.Client(base_url=url) as api:
            assert mismo == m and catalogos(datos) == antes
            assert api.get('/api/clientes/'+creado['id']).json()['telefono'] == 'TEST-002'
            ficha = api.get('/v0.6/clientes/'+bien['cliente']).text
            assert 'SIMULADO: ciudad documentada' in ficha
            assert 'Demo Fincaraíz revisada' in api.get('/v0.6/').text
            page.goto(url+'/v0.6/clientes/'+creado['id'])
            expect(page.locator('h1')).to_have_text('Lucía Prueba Editada')
        assert not errores and not fallidas and not externas and not consola, (errores, fallidas, externas, consola)
    finally:
        contexto.close()
