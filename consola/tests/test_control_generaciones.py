"""Carrera real observada en Cloud: generación reemplazada entre metadata y GET."""
import json
import pytest
from google.api_core.exceptions import NotFound,PreconditionFailed
from test_ejecuciones import Storage
from ejecuciones.control import ControlGCS,Conflict,empty

@pytest.mark.parametrize('error',[NotFound,PreconditionFailed])
def test_replaced_generation_is_reloaded(monkeypatch,error):
    storage=Storage();control=ControlGCS('synthetic',client=storage)
    blob=control.blob;blob.upload_from_string(json.dumps(empty()),if_generation_match=0)
    original=blob.download_as_bytes;calls=[]
    def replace(**kwargs):
        calls.append(kwargs['if_generation_match'])
        if len(calls)==1:
            blob.upload_from_string(json.dumps(dict(empty(),after_migration=True)),if_generation_match=1)
            raise error('Old generation disappeared')
        return original(**kwargs)
    monkeypatch.setattr(blob,'download_as_bytes',replace)
    doc,generation=control.read()
    assert doc['after_migration'] and generation==2 and calls==[1,2]

@pytest.mark.parametrize('error',[NotFound,PreconditionFailed])
def test_continuous_generation_race_fails_closed(monkeypatch,error):
    storage=Storage();control=ControlGCS('synthetic',client=storage)
    blob=control.blob;blob.upload_from_string(json.dumps(empty()),if_generation_match=0)
    def race(**kwargs):raise error('replaced')
    monkeypatch.setattr(blob,'download_as_bytes',race)
    with pytest.raises(Conflict):control.read()
    assert blob.generation==1

def test_missing_object_remains_read_only():
    storage=Storage();control=ControlGCS('synthetic',client=storage)
    assert control.read()==(empty(),0) and control.blob.data is None
