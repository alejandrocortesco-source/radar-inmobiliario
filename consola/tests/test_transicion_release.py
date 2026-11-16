"""Transición/rollback y comandos simulados: sin SDK productivo."""
import copy,json,subprocess,types
from pathlib import Path
from uuid import uuid4
import pytest
from google.api_core.exceptions import PreconditionFailed
from test_ejecuciones import execution,A,start
from test_programacion import FakeScheduler
from ejecuciones.calendarios import Calendarios
from ejecuciones.control import ControlGCS,Conflict,IntegrityError,now
from ejecuciones.transicion import rollback_legacy
from deployment.prepare_release import prepare,verify


def legacy(name):
    source=subprocess.check_output(['git','show','7283bc4:ejecuciones/'+name+'.py'],text=True,encoding='utf-8')
    module=types.ModuleType('ejecuciones._old_'+name);module.__package__='ejecuciones'
    exec(compile(source,'<old-'+name+'>','exec'),module.__dict__)
    return module

@pytest.fixture
def transition(execution):
    svc=execution[0];svc.overview(refresh=True);scheduler=FakeScheduler()
    from ejecuciones.programacion import Programacion
    cfg=Programacion(svc,scheduler).save([['metrocuadrado',A]],[0],'09:00','activate','')
    return Calendarios(svc,scheduler),scheduler,cfg

def migrate(multi):
    return multi.change('create',values=dict(name='Prueba',keys=[['metrocuadrado',A]],frequency='daily',hour='9',minute='0',days=[],enabled=False))

def test_real_old_binary_and_stale_generation_fenced(transition,execution):
    multi,scheduler,cfg=transition
    old=legacy('control').ControlGCS('synthetic',client=execution[2])
    doc,generation=old.read();migrate(multi)
    assert multi.control.read()[0]['version']==2
    with pytest.raises(RuntimeError):old.read()
    with pytest.raises(RuntimeError):old.change(lambda d:d.update(schedule=cfg))
    with pytest.raises(PreconditionFailed):old.blob.upload_from_string(json.dumps(doc),if_generation_match=generation)
    before=multi.control.read()
    with pytest.raises(IntegrityError):legacy('programacion').Programacion(multi.service,scheduler).save(cfg['keys'],[0],'09:00','save',before[0]['schedule']['revision'])
    assert multi.control.read()==before

def test_rollback_preserves_new_history_receipts_and_snapshot(transition,execution):
    multi,scheduler,cfg=transition;migrate(multi)
    manual=start(execution);multi.control.patch(manual['id'],dict(status='completed',finished=now()))
    multi.control.change(lambda d:d.update(extra_business={'after_migration':True},schedule_receipts={'later':now()}))
    # Cambio comercial posterior a migración, en el snapshot sintético.
    with execution[3]() as state:
        state.cargar(execution[4]/'business-after')
        from oportunidades.persistencia import SQLite
        from oportunidades.modelos import ClienteDatos
        SQLite(execution[4]/'business-after'/'metro-consola.sqlite').guardar_cliente(ClienteDatos(nombre='Cliente posterior sintético'))
        state.guardar(execution[4]/'business-after')
    multi.control.change(lambda d:d['runs'].append(dict(id=str(uuid4()),status='failed',created='2000-01-01T00:00:00+00:00',finished='2000-01-01T00:00:00+00:00')),transition=True)
    before=copy.deepcopy(multi.control.read()[0]);blob=execution[2].blob('radar/state.tar.gz');snapshot=blob.data
    desired=rollback_legacy(multi.control,scheduler,before['schedule']['revision'])
    after=multi.control.read()[0]
    assert after['version']==1 and not desired['enabled'] and scheduler.remote['state']=='PAUSED'
    assert after['runs']==before['runs'] and after['schedule_receipts']==before['schedule_receipts']
    assert after['extra_business']==before['extra_business'] and blob.data==snapshot
    assert after['schedules_archives'][-1]['schedules']==before['schedules']
    assert legacy('control').ControlGCS('synthetic',client=execution[2]).read()[0]==after
    assert after['schedule']['keys']==cfg['keys'] and after['schedule']['time']=='09:00'
    migrate(multi);assert multi.control.read()[0]['version']==2
    assert not multi.service.cloud.launched or multi.service.cloud.launched==[manual['id']]

def test_rollback_busy_stale_and_failed_sync_are_closed(transition,execution):
    multi,scheduler,cfg=transition;migrate(multi);rev=multi.control.read()[0]['schedule']['revision']
    with pytest.raises(Conflict):rollback_legacy(multi.control,scheduler,'wrong')
    r=start(execution)
    with pytest.raises(Conflict):rollback_legacy(multi.control,scheduler,rev)
    multi.control.patch(r['id'],dict(status='completed',finished=now()))
    scheduler.fail=True
    with pytest.raises(TimeoutError):rollback_legacy(multi.control,scheduler,rev)
    assert multi.control.read()[0]['version']==2 and multi.control.read()[0]['schedule']['pending']
    scheduler.fail=False
    multi.control.change(lambda d:d['schedule']['pending'].update(at='2020-01-01T00:00:00+00:00'))
    rollback_legacy(multi.control,scheduler,rev)
    assert multi.control.read()[0]['version']==1

@pytest.mark.parametrize('mode,origin',[('Private','https://ejecuciones-review---radar-dvhqhy5u3q-uc.a.run.app'),('Public','https://radar-56106530298.us-central1.run.app')])
def test_deploy_plan_only_preserves_settings(mode,origin):
    cmd=['powershell','-NoProfile','-File','deployment/deploy-web.ps1','-WebDigest','us-central1-docker.pkg.dev/radar-inmobiliario-co/radar/web@sha256:'+'a'*64,'-SourceSha','b'*40,'-SourceTree','c'*64,'-RevisionSuffix','candidate-test','-Mode',mode,'-PlanOnly']
    args=json.loads(subprocess.check_output(cmd,text=True,encoding='utf-8-sig'))
    assert '--no-traffic' in args and not any(a.startswith(('--set-env-vars','--set-secrets')) for a in args)
    env=next(a for a in args if a.startswith('--update-env-vars='))
    for key in ['RADAR_EXECUTION_JOB=radar-manual-review','RADAR_CONTROL_OBJECT=radar/executions/control.json','RADAR_SCHEDULE_TARGET=','RADAR_PUBLIC_ORIGIN='+origin]:assert key in env
    assert ('--tag=ejecuciones-review' in args)==(mode=='Private')

def test_origin_remains_strict_for_each_revision(monkeypatch):
    from consola.acceso import AccesoRadar
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    inner=FastAPI()
    @inner.post('/write')
    def write():return {'ok':True}
    monkeypatch.setenv('RADAR_AUTH_MODE','iap');monkeypatch.setenv('RADAR_IAP_AUDIENCE','/projects/56106530298/locations/us-central1/services/radar')
    monkeypatch.setattr('consola.acceso.validar_iap',lambda *a:{'sub':'synthetic'})
    for origin in ['https://radar-56106530298.us-central1.run.app','https://ejecuciones-review---radar-dvhqhy5u3q-uc.a.run.app']:
        monkeypatch.setenv('RADAR_PUBLIC_ORIGIN',origin)
        client=TestClient(AccesoRadar(inner))
        assert client.post('/write',headers={'Origin':origin,'x-goog-iap-jwt-assertion':'signed'}).status_code==200
        for other in ['https://evil.test','null','https://radar-56106530298.us-central1.run.app.evil.test']:
            assert client.post('/write',headers={'Origin':other,'x-goog-iap-jwt-assertion':'signed'}).status_code==403
        assert client.post('/write',headers={'Origin':origin}).status_code==401

def test_release_is_deterministic_and_verified(tmp_path):
    first,m=prepare(tmp_path);before=first.read_bytes();second,n=prepare(tmp_path)
    assert first==second and before==second.read_bytes() and m==n and verify(first)==m
    assert m['version']=='0.14.1' and not any(name.startswith(('.tmp/','.local/')) for name in m['files'])


def test_first_conversion_refuses_live_old_worker(transition,execution):
    multi,scheduler,cfg=transition
    run=start(execution);before=multi.control.read();calls=len(scheduler.calls)
    with pytest.raises(Conflict):migrate(multi)
    assert multi.control.read()==before and len(scheduler.calls)==calls
    multi.control.patch(run['id'],dict(status='completed',finished=now()))
    migrate(multi);assert multi.control.read()[0]['version']==2
