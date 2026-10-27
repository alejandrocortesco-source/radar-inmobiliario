"""Ciclo real en Chromium, escritorio/móvil; CRM aislado, catálogo de solo lectura.

Ejecutar desde raíz: python consola/tools/validar_geografia_navegador.py
"""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from urllib.request import urlopen
from hashlib import sha256

from validar_matching_real import main as validar_api, RAIZ
from playwright.sync_api import sync_playwright, expect


def main():
    evidencia = validar_api()
    salida = Path(evidencia['crm_pruebas']).parent
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    url = f'http://127.0.0.1:{port}'
    entorno = dict(os.environ, METRO_DB=evidencia['catalogo'], RADAR_CRM_DB=evidencia['crm_pruebas'],
                   PYTHONPATH=os.pathsep.join((str(RAIZ), str(RAIZ/'scraper'))))
    resultados, errores = [], []
    with (salida/'servidor.log').open('w', encoding='utf-8') as log:
        proceso = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'metro.web:app', '--host','127.0.0.1',
            '--port',str(port),'--log-level','warning'], cwd=RAIZ, env=entorno, stdout=log, stderr=log,
            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        try:
            limite = time.monotonic()+15
            while True:
                try:
                    with urlopen(url+'/health',timeout=1):
                        break
                except OSError:
                    if time.monotonic()>limite or proceso.poll() is not None:
                        raise RuntimeError('El servidor de validación no inició')
                    time.sleep(.1)
            with sync_playwright() as pw:
                browser = pw.chromium.launch(headless=True)
                try:
                    for ancho in (1440,390):
                        contexto = browser.new_context(viewport={'width':ancho,'height':1000})
                        page = contexto.new_page()
                        page.on('pageerror',lambda e:errores.append(str(e)))
                        page.goto(url+'/consola/')
                        assert page.locator('#crm_ciudad').input_value()=='Bogotá D.C.'
                        page.locator('[data-location-picker] > summary').click()
                        page.locator('#crm_buscar_barrio').fill('carolína')
                        expect(page.locator('[data-location-row]:visible')).to_have_count(1)
                        assert 'EDIF' not in page.locator('[data-location-options]').inner_text()
                        page.locator('[data-key="barrio:la carolina"] input').check()
                        page.locator('[data-location-done]').click()
                        for campo, valor in {'nombre':f'Validación geográfica {ancho}',
                            'presupuesto':'1650000000','habitaciones_min':'3','area_min_m2':'270'}.items():
                            page.locator('#crm_'+campo).fill(valor)
                        page.locator('#crm_tipo').select_option('apartamento')
                        page.locator('.capture-extra > summary').click()
                        page.locator('#crm_banos_min').fill('4')
                        page.locator('#crm_parqueaderos_min').fill('2')
                        page.get_by_role('button',name='Guardar y buscar coincidencias',exact=True).click()
                        expect(page.locator('[data-match-total]')).to_have_text('427')
                        expect(page.locator('[data-match-confirmed]')).to_have_text('5')
                        expect(page.locator('[data-match-pending]')).to_have_text('70')
                        fila = page.locator('[data-match-id="3147-M5621082"]')
                        expect(fila.locator('.match-status')).to_have_text('Confirmada')
                        expect(fila.locator('.match-property-link')).to_have_text('La Carolina')
                        page.locator('#matching-resumen').scroll_into_view_if_needed()
                        page.screenshot(path=str(salida/f'geografia-{ancho}.png'))
                        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
                        fila.locator('.match-property-link').click()
                        page.get_by_text('Más datos y características',exact=True).click()
                        expect(page.locator('.metadata').filter(has_text='Barrio publicado')).to_contain_text('LA CAROLINA   EDIF CRIXTAL')
                        page.go_back()
                        page.locator('#crm_habitaciones_min').fill('999')
                        page.get_by_role('button',name='Guardar y buscar coincidencias',exact=True).click()
                        expect(page.locator('[data-match-confirmed]')).to_have_text('0')
                        expect(page.locator('.match-empty')).to_contain_text('Habitaciones mínimas')
                        assert page.locator('.matching-table tbody tr').count()==0
                        resultados.append({'ancho':ancho,'inmueble_real_confirmado':True,'sin_coincidencias_explicado':True,'sin_desborde':True})
                        contexto.close()
                finally:
                    browser.close()
            assert not errores
            assert all(sha256(Path(p).read_bytes()).hexdigest()==h for p,h in evidencia['huellas_originales_sin_cambios'].items())
            resumen = {'validaciones':resultados,'errores_js':errores,'evidencia_api':str(salida/'evidencia.json')}
            (salida/'navegador.json').write_text(json.dumps(resumen,ensure_ascii=False,indent=2),encoding='utf-8')
            print(json.dumps(resumen,ensure_ascii=True,indent=2))
        finally:
            proceso.terminate()
            proceso.wait(timeout=15)


if __name__=='__main__':
    main()
