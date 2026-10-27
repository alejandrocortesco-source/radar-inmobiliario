"""Opciones del catálogo; normalización, históricos y cambio de ciudad."""
from dataclasses import replace

from bs4 import BeautifulSoup
from fastapi.testclient import TestClient

from consola.ubicaciones import opciones_ubicacion, actualizar_ciudad
from oportunidades.modelos import Necesidades
from test_v03 import inmueble, necesidades
from metro.web import app


def test_ciudad_unica_autoseleccion_y_deduplicacion():
    todos = [inmueble(ciudad='Bogotá D.C.', barrio='LA CAROLINA'),
             inmueble(ciudad='Bogotá, D.C.', barrio='la  carolína')]
    valores = {}
    c = opciones_ubicacion(todos, valores)
    assert c['ciudad_unica_crm'] and len(c['ciudades_crm']) == 1
    assert valores['ciudad'] in ('Bogotá D.C.', 'Bogotá, D.C.')
    assert len([o for o in c['ubicaciones_crm'] if o['tipo'] == 'barrio']) == 1
    assert c['ciudad_clave_crm'] == 'bogota'


def test_historicos_no_se_agregan_al_buscardor_y_no_se_borran():
    valores = {'ciudad': 'Bogotá', 'barrios': ['Barrio guardado sin anuncios']}
    c = opciones_ubicacion([inmueble()], valores)
    historicas = [o for o in c['ubicaciones_crm'] if o['legado']]
    assert len(historicas) == 1 and historicas[0]['seleccionada']
    assert valores['barrios'] == ['Barrio guardado sin anuncios']
    c = opciones_ubicacion([inmueble()], {'ciudad': 'Medellín'})
    assert c['ciudad_historica_crm'] and not c['ciudad_unica_crm']


def test_cambio_ciudad_retira_ubicaciones_ajenas_conserva_compartidas():
    valores = dict(ciudad='Medellín', barrios=['La Carolina', 'Compartido'], zonas=[])
    todos = [inmueble(barrio='La Carolina'), inmueble(ciudad='Medellín', barrio='El Poblado'),
             inmueble(ciudad='Medellín', barrio='COMPARTÍDO')]
    assert actualizar_ciudad(todos, valores) == ['La Carolina']
    assert valores['barrios'] == ['COMPARTÍDO']


def test_modelo_deduplica_tildes_caso_y_espacios():
    n = Necesidades.model_validate(necesidades().model_dump() | {'barrios': ['LA CAROLINA', 'la  carolína', ' La Carolina ']})
    assert n.barrios == ['LA CAROLINA']


def test_formulario_no_usa_datalist_y_fallback_preserva_borrador(escenario_consola):
    client = TestClient(app)
    pagina = BeautifulSoup(client.get('/consola/').text, 'html.parser')
    assert pagina.select_one('select#crm_ciudad')
    assert not pagina.select_one('#crm_ciudades')
    assert pagina.select_one('#crm_buscar_barrio')['autocomplete'] == 'off'
    r = client.post('/consola/ubicaciones', data={'ciudad': 'Bogotá', 'nombre': 'Borrador', 'habitaciones_min': '3'})
    assert r.status_code == 200
    pagina = BeautifulSoup(r.text, 'html.parser')
    assert pagina.select_one('#crm_nombre')['value'] == 'Borrador'
    assert pagina.select_one('#crm_habitaciones_min')['value'] == '3'
    assert 'no se ha guardado' in pagina.text
    assert client.get('/api/clientes').json() == []


def test_catalogo_una_ciudad_campo_fijo_sin_historial(escenario_consola):
    for id, doc in escenario_consola['documentos'].items():
        doc['normalized']['city'] = 'Bogotá D.C.'
        escenario_consola['store'].result(escenario_consola['run'], id, 'success', doc)
    pagina = BeautifulSoup(TestClient(app).get('/consola/').text, 'html.parser')
    ciudad = pagina.select_one('#crm_ciudad')
    assert ciudad.name == 'input' and ciudad.has_attr('readonly')
    assert ciudad['value'] == 'Bogotá D.C.' and ciudad['autocomplete'] == 'off'
    assert not ciudad.has_attr('list')


def test_cambio_ciudad_sin_javascript_no_guarda_seleccion_ajena(escenario_consola):
    for id, doc in escenario_consola['documentos'].items():
        if doc['normalized']['city'] == 'Medellín':
            doc['normalized']['neighborhood'] = 'El Poblado'
            escenario_consola['store'].result(escenario_consola['run'], id, 'success', doc)
    client = TestClient(app)
    respuesta = client.post('/consola/oportunidades', data=dict(
        nombre='Sin JavaScript', ciudad='Medellín', ubicaciones_ciudad='bogota',
        ubicaciones=['barrio:La Carolina'], operacion='compra', tipo='casa',
        presupuesto_max='200000000', habitaciones_min='3'))
    assert respuesta.status_code == 422
    assert 'Se retiraron ubicaciones que no corresponden' in respuesta.text
    assert 'Selecciona al menos un barrio' in respuesta.text
    assert client.get('/api/oportunidades').json() == []
