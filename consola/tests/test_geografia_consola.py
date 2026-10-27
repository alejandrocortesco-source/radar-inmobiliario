"""Normalización integrada: fuente → catálogo → selector → oportunidad → matching."""
from copy import deepcopy
import hashlib

from bs4 import BeautifulSoup
from fastapi.testclient import TestClient
from catalogo.identidad import identificar_inmueble
from catalogo.persistencia.sqlite import CatalogoSQLite
from consola.ubicaciones import opciones_ubicacion
from oportunidades.modelos import Necesidades
from oportunidades.matching import comparar
from metro.extraction import normalize_detail
from metro.web import app


def test_fuente_y_json_originales_conservados_al_normalizar():
    raw = dict(propertyId='real-ejemplo', neighborhood='LA CAROLINA   EDIF CRIXTAL',
               commonNeighborhood='LA CAROLINA', city={'nombre':'Bogotá'},
               zone={'nombre':'Norte'}, sector={'nombre':'Country'})
    copia = deepcopy(raw)
    doc = normalize_detail(raw, 'https://www.metrocuadrado.com/inmueble/real-ejemplo')
    assert raw == copia
    assert doc['normalized']['neighborhood'] == raw['neighborhood']
    assert doc['normalized']['common_neighborhood'] == raw['commonNeighborhood']
    assert doc['fields']['neighborhood']['raw'] == raw['neighborhood']


def test_selector_matching_y_filtro_comparten_normalizacion(escenario_consola):
    datos = escenario_consola
    for id, barrio, comun in [
        ('1-M1', 'LA CAROLINA EDIF CRIXTAL', 'La Carolina'),
        ('2-M2', 'LA CAROLINA EDIF TORRE DE ALCALA', 'BARRIO LA CAROLINA'),
        ('3-M3', 'LAGUNETA', 'LA CAROLINA'),
        ('4-M4', 'RINCON DEL CHICO EDIF CAROLINA', 'Rincón del Chicó'),
    ]:
        doc = datos['documentos'][id]
        doc['normalized'].update(neighborhood=barrio, common_neighborhood=comun)
        datos['store'].result(datos['run'], id, 'success', doc)
    huella = hashlib.sha256(datos['ruta'].read_bytes()).hexdigest()
    todos = CatalogoSQLite(datos['ruta']).listar()
    opciones = opciones_ubicacion(todos, {})['ubicaciones_crm']
    barrios = [o['nombre'] for o in opciones if o['tipo']=='barrio']
    assert barrios.count('La Carolina') == 1
    assert 'Rincón del Chicó' in barrios and not any('EDIF' in o for o in barrios)
    n = Necesidades(operacion='compra', tipo='casa', ciudad='Bogotá, D.C.',
                    barrios=['La Carolina'], presupuesto_max=110000000, habitaciones_min=3, area_min_m2=80)
    por_id = {i.origen.id_original:i for i in todos}
    assert comparar(n, por_id['1-M1']).confirmada
    assert comparar(n, por_id['2-M2']).confirmada
    assert not comparar(n, por_id['3-M3']).confirmada
    assert comparar(n, por_id['4-M4']) is None  # Edificio Carolina, barrio distinto.
    legado = n.model_copy(update={'barrios':['LA CAROLINA EDIF CRIXTAL']})
    assert comparar(legado, por_id['1-M1']).confirmada
    desconocida = n.model_copy(update={'barrios':['Santa Carolina']})
    r = comparar(desconocida, por_id['1-M1'])
    assert not r.confirmada and any('solicitud sin equivalencia controlada' in p for p in r.pendientes)
    client = TestClient(app)
    c = client.post('/api/clientes', json={'nombre':'Geografía prueba'}).json()
    o = client.post('/api/oportunidades', json={'cliente_id':c['id'], 'necesidades':n.model_dump(mode='json')}).json()
    d = client.get(f"/api/oportunidades/{o['id']}/diagnostico").json()
    assert any(r['inmueble']['origen']['id_original']=='1-M1' and not r['pendientes'] for r in d['resultados'])
    assert any(r['inmueble']['origen']['id_original']=='3-M3' and r['pendientes'] for r in d['resultados'])
    filtrado = client.get('/api/catalog', params={'barrios':'La Carolina', 'limit':100}).json()
    assert '1-M1' in {r['id'] for r in filtrado['items']} and '3-M3' not in {r['id'] for r in filtrado['items']}
    assert all(r['neighborhood']=='La Carolina' for r in filtrado['items'])
    ficha = client.get('/consola/inmuebles/' + identificar_inmueble('metrocuadrado','1-M1')).text
    assert 'LA CAROLINA EDIF CRIXTAL' in ficha and 'CRIXTAL' in ficha
    pagina = BeautifulSoup(client.get('/consola/').text, 'html.parser')
    assert not any('EDIF' in row.text for row in pagina.select('[data-location-row]'))
    assert hashlib.sha256(datos['ruta'].read_bytes()).hexdigest() == huella
