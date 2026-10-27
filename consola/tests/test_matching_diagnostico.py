"""Regresión del caso real Bogotá, D.C. y diagnóstico sin cambiar requisitos."""
from dataclasses import replace

from fastapi.testclient import TestClient
from bs4 import BeautifulSoup
import pytest

from metro.web import app
from oportunidades.matching import diagnosticar, buscar, comparar, normalizar_ciudad
from oportunidades.modelos import ClienteDatos, Necesidades
from oportunidades.servicio import servicio_oportunidades
from test_v03 import inmueble, necesidades


@pytest.mark.parametrize('ciudad', ['Bogotá', 'BOGOTA', 'Bogotá D.C.', 'Bogotá, D.C.', 'Bogota DC', '  Bogotá, d. c. '])
def test_grafias_ciudad_no_descartan_mismo_inmueble(ciudad):
    n = Necesidades.model_validate(necesidades().model_dump() | {'ciudad': ciudad})
    assert comparar(n, inmueble(ciudad='Bogotá D.C.')).confirmada
    assert normalizar_ciudad(ciudad) == 'bogota'


def test_normalizacion_no_convierte_lugares_distintos_ni_barrios_parecidos():
    assert comparar(necesidades(), inmueble(ciudad='Bogotá del Norte')) is None
    assert comparar(necesidades(), inmueble(ciudad='Medellín')) is None
    assert comparar(necesidades(), inmueble(barrio='LA CAROLINA EDIF TORRE')).confirmada
    assert not comparar(necesidades(), inmueble(ciudad=None)).confirmada


def test_diagnostico_acumulativo_contabiliza_fallos_y_desconocidos():
    def anuncio(id, **datos):
        return inmueble(origen=replace(inmueble().origen, id_original=id), **datos)
    items = [anuncio('bueno'), anuncio('otra-ciudad', ciudad='Medellín'),
             anuncio('sin-ciudad', ciudad=None), anuncio('pocas-habitaciones', habitaciones=1),
             anuncio('sin-habitaciones', habitaciones=None)]
    d = diagnosticar(necesidades(), items)
    assert (d['total_catalogo'], d['compatibles'], d['pendientes'], d['incompatibles']) == (5, 1, 2, 2)
    assert d['total_resultados'] == d['compatibles'] + d['pendientes']
    etapas = {p['codigo']: p for p in d['etapas']}
    assert etapas['ciudad'] == dict(codigo='ciudad', criterio='Ciudad', antes=5, descartados=1, restantes=4, sin_dato=1)
    assert etapas['habitaciones_min']['restantes'] == 3
    assert etapas['habitaciones_min']['sin_dato'] == 1
    assert sum(p['descartados'] for p in d['etapas']) == d['incompatibles']
    assert {r.inmueble.id_interno for r in d['resultados']} == {r.inmueble.id_interno for r in buscar(necesidades(), items)}
    assert len(d['descartes']) == 2 and all(r['motivos'] for r in d['descartes'])
    assert diagnosticar(necesidades(), [])['total_catalogo'] == 0


def test_preferencias_no_eliminan_en_etapas_ni_se_cuentan_como_fallos():
    d = diagnosticar(necesidades(banos_min=4, preferencias=['banos_min']), [inmueble()])
    assert d['compatibles'] == 1 and d['motivos'] == []
    assert 'banos_min' not in {p['codigo'] for p in d['etapas']}
    assert d['resultados'][0].preferencias_no_cumplidas


def test_api_diagnostico_usa_catalogo_global_y_mismas_coincidencias(escenario_consola):
    s = servicio_oportunidades()
    o = s.capturar(ClienteDatos(nombre='Diagnóstico'), Necesidades.model_validate(necesidades().model_dump() | {'ciudad': 'Bogotá, D.C.'}))
    client = TestClient(app)
    d = client.get(f'/api/oportunidades/{o.id}/diagnostico')
    assert d.status_code == 200
    informe = d.json()
    assert informe['total_catalogo'] == 26 and informe['compatibles'] == 10
    assert informe['pendientes'] == 0
    assert informe['almacenamiento']['catalogo'] == str(escenario_consola['ruta'])
    resultados = client.get(f'/api/oportunidades/{o.id}/coincidencias').json()
    assert informe['resultados'] == resultados
    assert client.get('/api/oportunidades/no-existe/diagnostico').status_code == 404
    assert client.get(f'/api/oportunidades/{o.id}/diagnostico?orden=incorrecto').status_code == 422
    pagina = BeautifulSoup(client.get(f'/consola/?oportunidad={o.id}&ciudad=Medellín').text, 'html.parser')
    assert pagina.select_one('[data-total]').text == '13'  # Tabla filtrada.
    assert pagina.select_one('[data-match-total]').text == '26'  # Matching global.
    assert pagina.select_one('[data-match-confirmed]').text == '10'
    assert len(pagina.select('.matching-table tbody tr')) == 10
    assert len(pagina.select('#crm_ubicaciones option[selected]')) == 1
    assert pagina.select_one('#filtros input[name="oportunidad"]')['value'] == o.id


def test_flujo_guardar_buscar_y_sin_resultados_explica_criterios(escenario_consola):
    client = TestClient(app)
    datos = dict(nombre='Prueba', operacion='compra', tipo='casa', ciudad='Bogotá, D.C.',
                 ubicaciones=['barrio:La Carolina'], presupuesto_max='110000000', habitaciones_min='3', accion='buscar')
    guardada = client.post('/consola/oportunidades', data=datos, follow_redirects=False)
    assert guardada.status_code == 303 and guardada.headers['location'].endswith('#matching-resumen')
    pagina = BeautifulSoup(client.get(guardada.headers['location']).text, 'html.parser')
    assert pagina.select_one('[data-match-confirmed]').text == '10'
    assert pagina.select_one('[data-match-total]').text == '26'
    o = client.get('/api/oportunidades').json()[0]
    datos.update(oportunidad_id=o['id'], cliente_id=o['cliente_id'], habitaciones_min='100')
    sin = client.post('/consola/oportunidades', data=datos)
    assert sin.status_code == 200
    pagina = BeautifulSoup(sin.text, 'html.parser')
    assert pagina.select_one('[data-match-confirmed]').text == '0'
    assert not pagina.select('.matching-table tbody tr')
    assert 'Habitaciones mínimas: 26 inmuebles no cumplen' in pagina.select_one('.match-empty').text
    assert 'Diagnóstico' in pagina.select_one('.matching-diagnostics').text
