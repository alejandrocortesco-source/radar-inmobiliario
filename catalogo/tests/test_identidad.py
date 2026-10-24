from uuid import UUID

import pytest

from catalogo.identidad import identificar_inmueble
from catalogo.modelos import Inmueble, Origen


def test_identidad_persistente_con_vector_fijo():
    # Detecta cambios accidentales del namespace, normalización o codificación.
    resultado = identificar_inmueble('metrocuadrado', '1-M1')
    assert resultado == '6d60db22-46b5-5438-ab2b-fba81883c607'
    assert UUID(resultado).version == 5
    assert identificar_inmueble(' Metrocuadrado ', ' 1-M1 ') == resultado


def test_fuente_e_id_forman_la_identidad_sin_fusionar_anuncios():
    ids = {
        identificar_inmueble('portal_a', '001'),
        identificar_inmueble('portal_b', '001'),
        identificar_inmueble('portal_a', '1'),
        identificar_inmueble('portal_a', 'A'),
        identificar_inmueble('portal_a', 'a'),
    }
    assert len(ids) == 5
    assert identificar_inmueble('a', 'b:c') != identificar_inmueble('a-b', 'c')


def test_identidad_no_depende_de_url_titulo_o_fechas():
    primero = Inmueble(origen=Origen(fuente='portal', id_original='123', url='https://a.test/123'))
    actualizado = Inmueble(
        origen=Origen(fuente='portal', id_original='123', url='https://a.test/nueva/123'),
        titulo='Título actualizado',
    )
    assert primero.id_interno == actualizado.id_interno


@pytest.mark.parametrize('fuente', ['', ' ', 'portal.com', 'portal con espacios', 'pórtal'])
def test_fuente_debe_ser_clave_tecnica(fuente):
    with pytest.raises(ValueError):
        identificar_inmueble(fuente, '123')


@pytest.mark.parametrize('original', ['', '   '])
def test_rechaza_id_vacio(original):
    with pytest.raises(ValueError):
        identificar_inmueble('portal', original)


@pytest.mark.parametrize('fuente,original', [(None, '123'), ('portal', 123), ('portal', True)])
def test_rechaza_identificadores_no_textuales(fuente, original):
    with pytest.raises(TypeError):
        identificar_inmueble(fuente, original)


def test_identidad_admite_id_original_unicode_y_no_pierde_delimitadores():
    assert identificar_inmueble('portal', 'á:001/二') == identificar_inmueble('portal', 'á:001/二')
    assert identificar_inmueble('a', 'b_c') != identificar_inmueble('a_b', 'c')
