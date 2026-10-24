import json
import pytest
from fastapi.testclient import TestClient
from metro.storage import Store
from metro.web import app

@pytest.fixture
def seeded(tmp_path,monkeypatch):
    path=tmp_path/'test.sqlite'
    monkeypatch.setenv('METRO_DB',str(path))
    s=Store(path)
    run=s.new_run('https://www.metrocuadrado.com/inmuebles/venta/bogota',{})
    item={'id':'1-M1','url':'https://www.metrocuadrado.com/inmueble/casa/1-M1'}
    s.save_page(run,1,'1','https://www.metrocuadrado.com/inmuebles/venta/bogota','fp1',[item],{'kind':'click'})
    s.save_page(run,2,'2','https://www.metrocuadrado.com/inmuebles/venta/bogota','fp2',[item],None)
    return s,run

def test_atomic_dedupe_resume_and_snapshot(seeded):
    s,run=seeded
    assert s.summary(run)['unique']==1
    assert s.summary(run)['duplicates']==1
    s.attempt(run,'1-M1')
    s.result(run,'1-M1','failed',error='timeout')
    assert len(s.pending(run,3))==1
    assert not s.pending(run,1)
    with pytest.raises(Exception): s.save_page(run,3,'3','url','fp2',[],None)
    assert len(s.pages(run))==2
    data={'normalized':{'title':'Casa <script>alert(1)</script>','price':123,'city':'Bogotá','property_type':'Casa'},'features':[],'photos':[],'fields':{},'sources':{},'media':{},'visible_text':'','errors':[]}
    s.result(run,'1-M1','success',data)
    assert not s.pending(run,3)
    assert json.loads(s.run(run)['config_json'])=={}

def test_web_empty_and_results(seeded):
    s,run=seeded
    client=TestClient(app)
    assert client.get('/health').json()=={'status':'ok'}
    assert client.get('/').status_code==200
    assert client.get('/api/properties').json()['total']==1
    assert client.get('/properties/1-M1').status_code==200
    assert client.get(f'/api/runs/{run}/export').json()['summary']['duplicates']==1
    assert client.get('/api/properties/unknown').status_code==404
    assert client.get('/api/properties?limit=0').status_code==422
    assert client.get('/?q=%27%20OR%201=1--').status_code==200

def test_web_escapes_public_data(seeded):
    test_atomic_dedupe_resume_and_snapshot(seeded)
    client=TestClient(app)
    response=client.get('/properties/1-M1')
    assert response.status_code==200
    assert '<script>alert(1)</script>' not in response.text
    assert '&lt;script&gt;' in response.text
