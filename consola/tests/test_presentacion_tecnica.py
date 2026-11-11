"""Riesgo de regresión al compartir estilos con las rutas técnicas conservadas."""
import pytest
from playwright.sync_api import expect
from test_browser import servidor, pagina


@pytest.mark.parametrize('ancho', [1440, 820, 390])
def test_tablas_tecnicas_y_ficha_desplazan_sin_desbordar_pagina(servidor, pagina, ancho):
    pagina.set_viewport_size({'width': ancho, 'height': 900})
    for ruta in ['/', '/catalog', '/properties/3-M3?run_id=1']:
        respuesta = pagina.goto(servidor + ruta)
        assert respuesta.status == 200
        expect(pagina.locator('main')).to_be_visible()
        assert pagina.evaluate('document.documentElement.scrollWidth <= innerWidth')
        # Los enlaces largos y columnas deben quedar en una región desplazable.
        assert pagina.locator('.tablewrap, .panel:has(> table)').count()
        if ancho == 390:
            assert pagina.locator('.tablewrap, .panel:has(> table)').evaluate_all(
                '(regiones) => regiones.some(r => r.scrollWidth > r.clientWidth)')
        pagina.locator('body').press('Tab')
        assert pagina.evaluate('document.activeElement.tagName') == 'A'
