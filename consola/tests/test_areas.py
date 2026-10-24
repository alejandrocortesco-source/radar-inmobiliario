"""Área visual prioritaria y comparaciones que conservan el tipo explícito."""
import csv
import io
from dataclasses import replace
from decimal import Decimal

import pytest
from bs4 import BeautifulSoup
from fastapi.testclient import TestClient

from catalogo.consultas import seleccionar
from catalogo.filtros import FiltrosCatalogo, OrdenCatalogo
from catalogo.modelos import Inmueble, Origen, TipoArea
from consola.presentacion import area_principal
from metro.web import app


@pytest.mark.parametrize('construida,privada,publicada,esperado', [
    ('82.5', '70', '100', '82,5 m² (construida)'),
    (None, '70', '100', '70 m² (privada)'),
    (None, None, '100', '100 m² (no especifica)'),
    (None, None, None, 'No especifica'),
])
def test_prioridad_y_etiquetas(construida, privada, publicada, esperado):
    def decimal(valor):
        return Decimal(valor) if valor is not None else None
    i = Inmueble(origen=Origen(fuente='metrocuadrado', id_original='1'),
                 area_construida_m2=decimal(construida), area_privada_m2=decimal(privada),
                 area_publicada_m2=decimal(publicada))
    assert area_principal(i) == esperado


@pytest.mark.parametrize('construida,privada,publicada,esperado', [
    (82.5, 70, 100, '82,5 m² (construida)'),
    (0, 70, 100, '70 m² (privada)'),
    (-1, 0, 100, '100 m² (no especifica)'),
    (None, None, None, 'No especifica'),
    (True, False, 'texto', 'No especifica'),
    ('NaN', 'Infinity', -2, 'No especifica'),
])
def test_tabla_ficha_y_csv_sin_unidades_guardadas(escenario_consola, construida, privada, publicada, esperado):
    datos = escenario_consola
    doc = datos['documentos']['1-M1']
    doc['normalized'].update(built_area=construida, private_area=privada, area=publicada)
    doc['normalized'].pop('built_area_unit', None)
    doc['normalized'].pop('private_area_unit', None)
    datos['store'].result(datos['run'], '1-M1', 'success', doc)
    client = TestClient(app)
    pagina = BeautifulSoup(client.get('/consola/', params={'texto': 'Casa con jardín 01'}).text, 'html.parser')
    assert pagina.select_one('.catalog-table tbody tr').select('td')[3].text.strip() == esperado
    ficha = BeautifulSoup(client.get(pagina.select_one('.property-link')['href']).text, 'html.parser')
    assert 'Área: ' + esperado in ficha.select_one('.essentials').get_text(' ', strip=True)
    filas = list(csv.DictReader(io.StringIO(client.get('/consola/exportar.csv', params={
        'texto': 'Casa con jardín 01'}).content.decode('utf-8-sig')), delimiter=';'))
    assert all(f['Tipo de área'] == (esperado.split('(')[-1][:-1] if '(' in esperado else '') for f in filas)


def test_filtros_y_orden_comparan_solo_el_tipo_seleccionado():
    base = Inmueble(origen=Origen(fuente='portal', id_original='a'),
                    area_construida_m2=Decimal('200'), area_privada_m2=Decimal('70'))
    privada = replace(base, origen=Origen(fuente='portal', id_original='b'),
                      area_construida_m2=None, area_privada_m2=Decimal('90'))
    publicada = replace(base, origen=Origen(fuente='portal', id_original='c'),
                        area_construida_m2=None, area_privada_m2=None, area_publicada_m2=Decimal('80'))
    fichas = (base, privada, publicada)
    filtrados = seleccionar(fichas, FiltrosCatalogo(tipo_area=TipoArea.CONSTRUIDA, area_max_m2=Decimal('100')))
    assert filtrados == []  # No usa las alternativas de 90 y 80 para filtrar construida.
    ordenados = seleccionar(fichas, FiltrosCatalogo(tipo_area=TipoArea.PRIVADA, orden=OrdenCatalogo.AREA_ASC))
    assert ordenados == [base, privada, publicada]  # 70, 90 y desconocida al final.
    assert area_principal(base) == '200 m² (construida)'


def test_comparacion_identificada_en_pantalla(escenario_consola):
    pagina = BeautifulSoup(TestClient(app).get('/consola/?tipo_area=privada&orden=area_asc').text, 'html.parser')
    assert 'Filtros y orden de área: solo privada' in pagina.select_one('.legend').text
    assert pagina.select_one('.catalog-table tbody tr').select('td')[3]['title'].startswith('Filtros y orden por área privada:')
