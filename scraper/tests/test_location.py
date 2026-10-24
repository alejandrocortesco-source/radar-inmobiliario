import json
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi.testclient import TestClient

from metro.extraction import add_location_fields, normalize_detail
from metro.paths import COMPONENT_ROOT
from metro.storage import Store
from metro.web import app


def test_real_coordinates_and_original_map_section():
    fixture = json.loads((COMPONENT_ROOT/'tests/fixtures/consultorio.json').read_text(encoding='utf-8'))
    data = normalize_detail(fixture['raw'], fixture['url'], fixture['text'])
    query = parse_qs(urlsplit(data['normalized']['map_url']).query)
    assert float(query['mlat'][0]) == fixture['raw']['coordinates']['lat']
    assert float(query['mlon'][0]) == fixture['raw']['coordinates']['lon']
    assert data['normalized']['portal_map_url'] == fixture['url']+'#location-section'
    assert data['fields']['map_url']['derived'] is True
    assert data['fields']['map_url']['raw']['coordinates'] == fixture['raw']['coordinates']


@pytest.mark.parametrize('coords',[None,{}, {'lat':None,'lon':-74}, {'lat':4}])
def test_absent_coordinates_do_not_create_location(coords):
    document = {'sources':{'flight_property':{'coordinates':coords}}}
    data = add_location_fields(document,'/inmueble/consultorio/1-M1')
    assert data['normalized']['map_url'] is None
    assert data['normalized']['portal_map_url'] is None
    assert data['fields']['map_url']['status'] == 'absent'


@pytest.mark.parametrize('coords',[{'lat':999,'lon':-74},{'lat':'NaN','lon':-74},{'lat':True,'lon':-74},'unresolved'])
def test_invalid_coordinates_are_extraction_errors(coords):
    data = add_location_fields({'extra':{'coordinates':coords}},'/inmueble/consultorio/1-M1')
    assert data['fields']['map_url']['status'] == 'error'
    assert data['normalized']['map_url'] is None


def test_stored_links_in_detail_list_and_export(tmp_path,monkeypatch):
    database = tmp_path/'location.sqlite'
    monkeypatch.setenv('METRO_DB',str(database))
    store = Store(database)
    url = 'https://www.metrocuadrado.com/inmueble/consultorio/1-M1'
    run_id = store.new_run('https://www.metrocuadrado.com/inmuebles/',{})
    store.save_page(run_id,1,'1','search','fp',[{'id':'1-M1','url':url}],None)
    data = normalize_detail({'propertyId':'1-M1','businessType':'venta','coordinates':{'lat':4.7,'lon':-74},'ubicacionaproximada':'S'},url)
    store.result(run_id,'1-M1','success',data)
    client = TestClient(app)
    result = client.get('/properties/1-M1')
    assert result.status_code == 200
    assert 'Ver ubicación en mapa' in result.text
    assert 'la ubicación es aproximada' in result.text
    assert client.get('/api/properties').json()['items'][0]['map_url'] == data['normalized']['map_url']
    exported = client.get(f'/api/runs/{run_id}/export').json()
    assert exported['properties'][0]['data']['normalized']['map_url'] == data['normalized']['map_url']


def test_enrichment_is_idempotent_and_preserves_originals():
    document = {'extra':{'coordinates':{'lat':4.7,'lon':-74}},'visible_text':'Original','errors':[],'quality':'success'}
    add_location_fields(document,'/inmueble/consultorio/1-M1')
    snapshot = json.loads(json.dumps(document))
    add_location_fields(document,'/inmueble/consultorio/1-M1')
    assert document == snapshot
