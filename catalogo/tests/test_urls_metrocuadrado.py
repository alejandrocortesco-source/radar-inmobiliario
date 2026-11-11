"""Rutas alternativas conservan filtros sin aceptar fichas ni dominios hostiles."""
import pytest
from catalogo.fuentes.metrocuadrado import validar_url


def test_rutas_compatibles_y_parametros_intactos():
    for url in (
        'https://www.metrocuadrado.com/apartamento-casa/arriendo/bogota/la-carolina?search=form',
        'https://metrocuadrado.com/apartamento/venta/bogota?preciomax=500000000',
        'https://www.metrocuadrado.com/inmuebles/venta/bogota/la-carolina',
    ):
        assert validar_url(' '+url+' ') == url


def test_rechazo_sin_navegacion_ni_reescritura():
    for url in (
        'https://metrocuadrado.com.evil.test/apartamento-casa/arriendo/bogota',
        'https://usuario:clave@metrocuadrado.com/apartamento/arriendo/bogota',
        'https://metrocuadrado.com:99/apartamento/arriendo/bogota',
        'https://metrocuadrado.com:incorrecto/apartamento/arriendo/bogota',
        'https://www.metrocuadrado.com/inmueble/apartamento/arriendo/bogota/123',
        'https://www.metrocuadrado.com/apartamento-casa/arriendo',
        'https://www.metrocuadrado.com/apartamento-casa/arriendo/bogo\nta',
        'javascript:alert(1)',
    ):
        with pytest.raises(ValueError, match='URL de búsqueda'):
            validar_url(url)
