from ejecuciones.scheduler import Scheduler as RealScheduler
import json
from datetime import datetime,timezone
import pytest
from fastapi.testclient import TestClient
from test_programacion import program,ready
from test_ejecuciones import execution
from ejecuciones.disparador import app

@pytest.fixture
def receiver(program,monkeypatch):
    cfg,date=ready(program)
    monkeypatch.setattr('ejecuciones.disparador.authenticate',lambda h:None)
    monkeypatch.setattr('ejecuciones.disparador.ServicioEjecuciones',lambda:program.service)
    monkeypatch.setattr('ejecuciones.disparador.Scheduler',lambda:program.scheduler)
    return TestClient(app),program,cfg,date

def post(receiver,job,clock=None,header='X-CloudScheduler-JobName'):
    client,program,cfg,date=receiver
    headers={header:job} if job is not None else {}
    if clock is not None:headers['X-CloudScheduler-ScheduleTime']=clock
    return client.post('/trigger',json={'revision':cfg['revision']},headers=headers)

def test_short_endpoint_contract(receiver):
    r=post(receiver,'radar-weekly-review',receiver[3].isoformat())
    assert r.status_code==202,r.text
    assert len(receiver[1].service.cloud.launched)==1

@pytest.mark.parametrize('header',['x-cloudscheduler-jobname','X-CLOUDSCHEDULER-JOBNAME'])
def test_canonical_duplicate(receiver,header):
    a=post(receiver,'radar-weekly-review',receiver[3].isoformat(),header)
    b=post(receiver,receiver[1].scheduler.name,receiver[3].isoformat())
    assert a.status_code==b.status_code==202
    assert a.json()['id']==b.json()['id']
    assert len(receiver[1].control.read()[0]['runs'])==1
    assert len(receiver[1].service.cloud.launched)==1

@pytest.mark.parametrize('job',[None,'','other','RADAR-WEEKLY-REVIEW',' radar-weekly-review','radar-weekly-review ','prefixradar-weekly-review','radar-weekly-review/suffix','projects/other/locations/us-central1/jobs/radar-weekly-review','projects/radar-inmobiliario-co/locations/europe-west1/jobs/radar-weekly-review','projects/radar-inmobiliario-co/locations/us-central1/jobs/radar-weekly-review/extra'])
def test_rejected_identifiers(receiver,job,caplog):
    r=post(receiver,job,receiver[3].isoformat())
    assert r.status_code==422
    assert r.json()['code'] in {'missing_job_header','unrecognized_job'}
    assert not receiver[1].control.read()[0]['runs']
    assert not receiver[1].service.cloud.launched
    assert 'canonical_job' not in caplog.text

@pytest.mark.parametrize('date',[None,'','invalid','2026-11-16T08:15:00'])
def test_bad_clock(receiver,date):
    r=post(receiver,'radar-weekly-review',date)
    assert r.status_code==422
    assert r.json()['code'] in {'missing_schedule_header','invalid_schedule_time'}
    assert not receiver[1].control.read()[0]['runs']
    assert not receiver[1].service.cloud.launched


def test_paused(receiver):
    receiver[1].control.change(lambda d:d['schedule'].update(enabled=False))
    r=post(receiver,'radar-weekly-review',receiver[3].isoformat())
    assert r.status_code==202 and r.json()['status']=='skipped'
    assert not receiver[1].service.cloud.launched


def test_authentication_and_bounded_diagnostics(receiver,monkeypatch,caplog):
    def denied(h):raise ValueError('SECRET_COOKIE_TOKEN')
    monkeypatch.setattr('ejecuciones.disparador.authenticate',denied)
    assert post(receiver,'radar-weekly-review',receiver[3].isoformat()).status_code==401
    assert not receiver[1].control.read()[0]['runs']
    assert 'SECRET_COOKIE_TOKEN' not in caplog.text


def test_safe_diagnostics(receiver,caplog):
    r=post(receiver,'radar-weekly-review',receiver[3].isoformat())
    events=[json.loads(r.message) for r in caplog.records if r.name=='ejecuciones.disparador']
    assert events[-1]['canonical_job']==receiver[1].scheduler.name
    assert events[-1]['job_format']=='short' and events[-1]['scheduled_at'] and events[-1]['request_id']
    assert events[-1]['run_id']==r.json()['id']

@pytest.mark.parametrize('body,code',[({},'missing_revision'),([], 'missing_revision'),({'revision':None},'invalid_revision')])
def test_body_contract(receiver,body,code):
    r=receiver[0].post('/trigger',json=body,headers={'X-CloudScheduler-JobName':'radar-weekly-review','X-CloudScheduler-ScheduleTime':receiver[3].isoformat()})
    assert r.status_code==422 and r.json()['code']==code
    assert not receiver[1].service.cloud.launched


def test_configured_scheduler_http_payload(receiver):
    import base64
    payload=RealScheduler(session=object()).payload(receiver[2])
    target=payload['httpTarget']
    response=receiver[0].request(target['httpMethod'],'/trigger',content=base64.b64decode(target['body']),headers={**target['headers'],'X-CloudScheduler-JobName':'radar-weekly-review','X-CloudScheduler-ScheduleTime':receiver[3].isoformat()})
    assert response.status_code==202
    assert len(receiver[1].service.cloud.launched)==1


def test_parallel_representations(receiver):
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(2) as pool:
        results=list(pool.map(lambda name:post(receiver,name,receiver[3].isoformat()),['radar-weekly-review',receiver[1].scheduler.name]))
    assert all(r.status_code==202 for r in results)
    assert results[0].json()['id']==results[1].json()['id']
    assert len(receiver[1].service.cloud.launched)==1
