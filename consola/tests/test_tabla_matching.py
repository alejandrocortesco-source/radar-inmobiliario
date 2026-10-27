"""Orden real por columnas, desconocidos al final y paginación estable."""
from dataclasses import replace
from decimal import Decimal
from urllib.parse import parse_qs, urlsplit

from bs4 import BeautifulSoup
from fastapi.testclient import TestClient
import pytest
from starlette.datastructures import QueryParams

from consola.resultados import ordenar_resultados, presentar_resultados, COLUMNAS
from oportunidades.matching import diagnosticar
from oportunidades.modelos import ClienteDatos
from oportunidades.servicio import servicio_oportunidades
from oportunidades.persistencia import SQLite
from test_v03 import inmueble, necesidades
from metro.web import app


@pytest.mark.parametrize('campo', [c for c, _ in COLUMNAS])
def test_ordenes_columnas_deterministas_y_mismo_conjunto(campo):
    a = inmueble()
    b = inmueble(origen=replace(a.origen, id_original='b'), habitaciones=None, banos=None,
                 area_construida_m2=None, barrio=None, tipo=None, ofertas=())
    resultados = diagnosticar(necesidades(), [a, b])['resultados']
    for d in ('asc', 'desc'):
        ordenados = ordenar_resultados(resultados, campo + '_' + d)
        assert len(ordenados) == 2 and {r.inmueble.id_interno for r in ordenados} == {a.id_interno, b.id_interno}
        if campo in ('tipo', 'precio', 'area', 'habitaciones', 'banos'):
            assert ordenados[-1].inmueble == b


def test_orden_precio_decimal_y_cero_no_son_textos():
    a = inmueble()
    b = inmueble(origen=replace(a.origen, id_original='b'), ofertas=(replace(a.ofertas[0], precio=Decimal('9000000')),))
    r = diagnosticar(necesidades(), [a, b])['resultados']
    assert ordenar_resultados(r, 'precio_asc')[0].inmueble == b
    assert ordenar_resultados(r, 'precio_desc')[0].inmueble == a
    with pytest.raises(ValueError):
        ordenar_resultados(r, 'inventado')


def test_paginacion_limites_orden_y_regreso_conservan_filtros(tmp_path):
    from oportunidades.servicio import ServicioOportunidades
    crm = ServicioOportunidades(SQLite(tmp_path / 'crm.sqlite'))
    o = crm.capturar(ClienteDatos(nombre='Tabla'), necesidades())
    items = [inmueble(origen=replace(inmueble().origen, id_original=str(k))) for k in range(31)]
    d = diagnosticar(o.necesidades, items)
    query = QueryParams('oportunidad=' + o.id + '&match_limit=12&match_offset=12&match_orden=precio_desc&barrios=uno&barrios=dos')
    vista = presentar_resultados(o, d, query)
    assert len(vista['resultados']) == 12 and vista['pagina_match']['total'] == 31
    assert vista['match_pagina'] == 2 and vista['match_paginas'] == 3
    assert parse_qs(urlsplit(vista['match_siguiente']).query)['barrios'] == ['uno', 'dos']
    assert ('barrios', 'uno') in vista['match_extras'] and ('barrios', 'dos') in vista['match_extras']
    volver = parse_qs(urlsplit(vista['resultados'][0][1]['url']).query)['volver'][0]
    assert parse_qs(urlsplit(volver).query)['match_offset'] == ['12']
    assert parse_qs(urlsplit(volver).query)['barrios'] == ['uno', 'dos']
    for invalido in ('match_limit=0&match_offset=-1', 'match_limit=no&match_offset=oops'):
        v = presentar_resultados(o, d, QueryParams(invalido))
        assert v['pagina_match']['limit'] == 24 and v['pagina_match']['offset'] == 0
    assert presentar_resultados(o, d, QueryParams('match_limit=12&match_offset=9999'))['match_pagina'] == 3


def test_tabla_http_pagina_orden_y_diagnostico_no_paginar(escenario_consola):
    crm = servicio_oportunidades()
    o = crm.capturar(ClienteDatos(nombre='Comparar'), necesidades().model_copy(update={'presupuesto_max': Decimal('200000000')}))
    client = TestClient(app)
    url = f'/consola/?oportunidad={o.id}&match_limit=12&match_orden=precio_desc'
    pagina = BeautifulSoup(client.get(url).text, 'html.parser')
    assert len(pagina.select('.matching-table tbody tr')) == 12
    assert len(pagina.select('.matching-table thead th')) == 10
    assert pagina.select_one('.matching-table tbody tr')['data-match-id'] == '13-M13'
    assert pagina.select_one('[data-match-confirmed]').text == '13'
    siguiente = pagina.select_one('.matching-pagination a[rel="next"]')['href']
    pagina2 = BeautifulSoup(client.get(siguiente).text, 'html.parser')
    assert len(pagina2.select('.matching-table tbody tr')) == 1
    assert pagina2.select_one('.matching-table tbody tr')['data-match-id'] == '1-M1'
    assert not pagina.select('article.match-result, .match-grid')
    assert '$113.000.000' in pagina.select_one('.match-price-cell').text
    assert pagina.select_one('.matching-table th[aria-sort="descending"]')
    assert len(client.get(f'/api/oportunidades/{o.id}/coincidencias').json()) == 13
    assert client.get(f'/api/oportunidades/{o.id}/diagnostico').json()['compatibles'] == 13
    assert client.get(f'/consola/oportunidades/{o.id}/coincidencias?orden=area_desc&match_limit=12').status_code == 200
