"""Calendario y entregas aislados: sin portales, proveedor IA ni API de Cloud real."""
import copy
import json
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4
from urllib.parse import urlsplit
import httpx
import pytest
from fastapi.testclient import TestClient
from test_ejecuciones import execution, A, B, fake_scrapers, run_manual, start
from ejecuciones.control import now, Conflict
from ejecuciones.programacion import validate, upcoming, cron, occurrence_reason, Programacion, DEFAULT, view
from ejecuciones.scheduler import Scheduler
from ejecuciones.servicio import ServicioEjecuciones
from ejecuciones.cloud_run import reconcile
from consola.durable import WebDurable
from metro.web import app
from ejecuciones.disparador import app as trigger_app, authenticate

class FakeScheduler:
    name = 'projects/radar-inmobiliario-co/locations/us-central1/jobs/radar-weekly-review'
    def __init__(self):
        self.remote = None
        self.calls = []
        self.fail = False
    def get(self):
        return copy.deepcopy(self.remote)
    def matches(self, remote, cfg):
        return remote.get('revision') == cfg['revision']
    def sync(self, cfg):
        self.calls.append(copy.deepcopy(cfg))
        if self.fail:
            raise TimeoutError('SECRET_NOT_EXPOSED')
        if cfg['enabled'] or self.remote:
            self.remote = dict(revision=cfg['revision'], state='ENABLED' if cfg['enabled'] else 'PAUSED')

@pytest.fixture
def program(execution, monkeypatch):
    svc = execution[0]
    svc.overview(refresh=True)
    scheduler = FakeScheduler()
    monkeypatch.setenv('RADAR_SCHEDULE_TARGET', 'https://radar-schedule-review-synthetic.us-central1.run.app')
    monkeypatch.setattr('ejecuciones.scheduler.Scheduler', lambda: scheduler)
    return Programacion(svc, scheduler)


def configure(program, enabled=False):
    date = datetime.now(timezone.utc).astimezone(__import__('ejecuciones.programacion',fromlist=['TZ']).TZ).replace(second=0,microsecond=0)
    initial = program.control.read()[0].get('schedule', DEFAULT)
    cfg = program.save([['metrocuadrado', A], ['metrocuadrado', B]], [date.weekday()], date.strftime('%H:%M'), 'activate' if enabled else 'save', initial['revision'])
    return cfg, date


def ready(program):
    cfg, date = configure(program, True)
    # Adelanta solo el gate sintético para representar una fecha futura ya alcanzada.
    program.control.change(lambda d: d['schedule'].update(effective_after=(date-timedelta(days=1)).isoformat()))
    return cfg, date


def deliver(program, cfg, date):
    return program.deliver(program.scheduler.name, cfg['revision'], date.isoformat())

@pytest.mark.parametrize('days,clock', [([], '12:00'), ([7], '12:00'), ([-1], '12:00'), ([True], '12:00'), ([1], '24:00'), ([1], '1:30'), ([1], '12:60'), ([1], '12:30:00')])
def test_invalid(days, clock):
    with pytest.raises(ValueError):
        validate([['metrocuadrado', A]], days, clock)

@pytest.mark.parametrize('clock', ['00:00','00:30','23:59'])
def test_valid_midnight_and_week_change(clock):
    cfg = validate([['metrocuadrado', A]], [0,6,0], clock)
    assert cfg['days'] == [0,6]
    dates = upcoming(cfg, datetime.fromisoformat('2026-11-15T23:59:59-05:00'))
    assert dates[0].startswith('2026-11-16T'+clock)
    assert all(d.endswith('-05:00') for d in dates)
    assert cron(cfg).endswith('1,0')
    equal = upcoming(cfg, datetime.fromisoformat('2026-11-16T'+clock+':00-05:00'))
    assert equal[0].startswith('2026-11-22')


def test_save_activate_pause_edit_restart_without_launch(program):
    cfg, date = configure(program)
    assert not cfg['enabled'] and program.scheduler.remote is None
    cfg = program.save(cfg['keys'], [1,4], '00:30', 'activate', cfg['revision'])
    assert program.read()['active'] and 'Martes y viernes' in program.read()['summary']
    assert all(datetime.fromisoformat(d)>datetime.now(timezone.utc) for d in program.read()['next'])
    cfg = program.save(cfg['keys'], [6], '23:59', 'save', cfg['revision'])
    assert cfg['enabled'] and program.read()['summary'] == 'Domingo a las 23:59'
    rebuilt = Programacion(ServicioEjecuciones(program.control, program.service.cloud, program.service.state_factory, program.service.data_dir), program.scheduler)
    assert rebuilt.read()['config'] == cfg
    cfg = program.save([], [], '', 'pause', cfg['revision'])
    assert not cfg['enabled'] and program.scheduler.remote['state'] == 'PAUSED'
    assert not program.service.cloud.launched


def test_sync_failure_fail_closed_recover_after_interruption(program):
    cfg, date = configure(program, True)
    program.scheduler.fail = True
    with pytest.raises(RuntimeError):
        program.save(cfg['keys'],[2],'03:20','save',cfg['revision'])
    assert not program.read()['active'] and program.read()['uncertain']
    result = deliver(program,cfg,date)
    assert result['status'] == 'skipped'
    program.scheduler.fail = False
    program.control.change(lambda d:d['schedule']['pending'].update(at='2020-01-01T00:00:00+00:00'))
    fixed = program.save(cfg['keys'],[2],'03:20','save',cfg['revision'])
    assert fixed['enabled'] and program.read()['active']
    assert not program.service.cloud.launched


def test_concurrent_duplicate_deliveries_launch_once(program):
    cfg,date = ready(program)
    with ThreadPoolExecutor(4) as pool:
        results = list(pool.map(lambda _:deliver(program,cfg,date),range(4)))
    assert len({r['id'] for r in results}) == 1
    assert len(program.service.cloud.launched) == 1
    assert len(program.control.read()[0]['runs']) == 1


def test_manual_conflict_is_permanently_skipped(program, execution):
    cfg,date = ready(program)
    manual = start(execution)
    result = deliver(program,cfg,date)
    assert result['status'] == 'skipped' and 'curso' in result['error']
    program.control.patch(manual['id'],dict(status='failed',finished=now()))
    assert deliver(program,cfg,date)['status'] == 'skipped'
    assert program.service.cloud.launched == [manual['id']]


def test_manual_after_automatic_is_blocked(program, execution):
    cfg,date = ready(program)
    result = deliver(program,cfg,date)
    with pytest.raises(Conflict):
        start(execution)
    assert program.service.cloud.launched == [result['id']]


def test_lost_launch_response_never_retries_and_reconciles(program, execution):
    cfg,date = ready(program)
    program.service.cloud.uncertain = True
    result = deliver(program,cfg,date)
    program.control.patch(result['id'],dict(created=(datetime.now(timezone.utc)-timedelta(minutes=15)).isoformat()))
    reconcile(program.control,program.service.cloud,program.service.unlock,force=True)
    assert deliver(program,cfg,date)['status'] == 'interrupted'
    assert len(program.service.cloud.launched) == 1
    assert not run_manual(execution[4]/'late',result['id'],program.control,execution[3],lambda *a:pytest.fail('no portal'))


def test_pause_before_worker_fences_start(program, execution):
    cfg,date = ready(program)
    result = deliver(program,cfg,date)
    program.save([],[],'','pause',cfg['revision'])
    assert not run_manual(execution[4]/'worker',result['id'],program.control,execution[3],lambda *a:pytest.fail('no portal'))
    assert program.control.get(result['id'])['status'] == 'skipped'


def test_pause_during_started_worker_does_not_cancel_and_persists(program, execution):
    cfg,date = ready(program)
    result = deliver(program,cfg,date)
    called=[]
    paused=[]
    def hook():
        if not paused:
            paused.append(program.save([],[],'','pause',cfg['revision']))
    assert run_manual(execution[4]/'worker',result['id'],program.control,execution[3],fake_scrapers(['completed','incomplete'],called,hook),heartbeat=.001)
    final=program.control.get(result['id'])
    assert final['status']=='partial' and final['persisted'] and final['snapshot_generation']
    assert final['origin']=='automatic' and final['scheduled_at'] and final['started']
    assert called==[A,B]
    assert all(b['processed']==1 for b in final['searches'])

@pytest.mark.parametrize('case',['paused','old','late','future','off_calendar','before_activation'])
def test_rejected_occurrences_never_launch(program,case):
    cfg,date = ready(program)
    if case=='paused':
        program.save([],[],'','pause',cfg['revision'])
    elif case=='old':
        cfg=dict(cfg,revision=str(uuid4()))
    elif case=='late': date-=timedelta(minutes=16)
    elif case=='future': date+=timedelta(minutes=1)
    elif case=='off_calendar': date-=timedelta(minutes=1)
    elif case=='before_activation':
        program.control.change(lambda d:d['schedule'].update(effective_after=now()))
    result=deliver(program,cfg,date)
    assert result['status']=='skipped'
    assert not program.service.cloud.launched


def test_missing_and_inactive_omitted_and_new_not_added(program, execution):
    cfg,date=ready(program)
    svc,repo,storage,factory,tmp=execution
    with factory() as state:
        state.cargar(tmp/'inactive')
        from catalogo.persistencia.busquedas import BusquedasSQLite
        r=BusquedasSQLite(tmp/'inactive'/'metro-consola.sqlite')
        r.cambiar_estado('metrocuadrado',A,False)
        r.guardar('metrocuadrado',A+'/new',A+'/new','Nueva')
        state.guardar(tmp/'inactive')
    result=deliver(program,cfg,date)
    called=[]
    assert run_manual(tmp/'first-worker',result['id'],program.control,factory,fake_scrapers(['completed'],called),heartbeat=.001)
    assert called==[B]
    assert program.control.get(result['id'])['schedule_warning']


def test_ui_auth_csrf_and_validation(program,monkeypatch):
    client=TestClient(app)
    body={'revision':'','days':'1','time':'24:00','schedule_search':json.dumps(['metrocuadrado',A]),'action':'save'}
    assert client.post('/v0.6/ejecuciones/programacion',data=body).status_code==422
    body['time']='00:00'
    assert client.post('/v0.6/ejecuciones/programacion',data=body,headers={'Origin':'https://evil.example'}).status_code==403
    response=client.post('/v0.6/ejecuciones/programacion',data=body)
    assert response.status_code==200 and 'No se inició scraping' in response.text
    assert not program.service.cloud.launched
    monkeypatch.setenv('RADAR_AUTH_MODE','iap')
    monkeypatch.setenv('RADAR_IAP_AUDIENCE','/projects/56106530298/locations/us-central1/services/radar')
    monkeypatch.setenv('RADAR_PUBLIC_ORIGIN','https://radar.example')
    assert client.post('/v0.6/ejecuciones/programacion',data=body).status_code==401


def test_trigger_rejects_unauthorized_and_validates_oidc(monkeypatch):
    client=TestClient(trigger_app)
    assert client.post('/trigger',json={}).status_code==401
    monkeypatch.setenv('RADAR_SCHEDULE_TARGET','https://private.run.app')
    monkeypatch.setattr('ejecuciones.disparador.verify_oauth2_token',lambda *a,**k:dict(email='evil@example.com',email_verified=True))
    with pytest.raises(ValueError):authenticate('Bearer signed')
    monkeypatch.setattr('ejecuciones.disparador.verify_oauth2_token',lambda *a,**k:dict(email='radar-scheduler@radar-inmobiliario-co.iam.gserviceaccount.com',email_verified=True))
    authenticate('Bearer signed')
    assert client.post('/trigger',json={},headers={'Authorization':'Bearer signed'}).status_code==422


def test_scheduler_payload_oidc_and_no_create_on_disabled(monkeypatch):
    monkeypatch.setenv('RADAR_SCHEDULE_TARGET','https://radar-schedule-review-test.us-central1.run.app')
    calls=[]
    def handler(request):
        calls.append(request)
        return httpx.Response(404,json={})
    with httpx.Client(transport=httpx.MockTransport(handler)) as session:
        scheduler=Scheduler(session)
        cfg=dict(validate([['metrocuadrado',A]],[1,4],'00:30'),enabled=False,revision=str(uuid4()))
        scheduler.sync(cfg)
        payload=scheduler.payload(cfg)
    assert len(calls)==1 and calls[0].method=='GET'
    assert payload['timeZone']=='America/Bogota' and payload['schedule']=='30 0 * * 2,5'
    assert payload['httpTarget']['oidcToken']['audience'].endswith('.run.app')

@pytest.mark.parametrize('viewport',[(1440,900),(768,1024),(390,844)])
def test_browser_configuration_focus_errors_no_overflow(program,execution,chromium,viewport):
    configure(program)
    client=TestClient(app)
    context=chromium.new_context(viewport=dict(width=viewport[0],height=viewport[1]))
    page=context.new_page()
    def routed(route):
        req=route.request
        url=urlsplit(req.url)
        res=client.request(req.method,url.path+('?' + url.query if url.query else ''),content=req.post_data_buffer,follow_redirects=True)
        route.fulfill(status=res.status_code,headers={k:v for k,v in res.headers.items() if k.lower() not in {'content-length','content-encoding'}},body=res.content)
    page.route('**/*',routed)
    page.goto('http://127.0.0.1/v0.6/ejecuciones')
    assert page.locator('#programacion').count()==1
    assert page.locator('#programacion').inner_text().find('Desactivada')>=0
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    page.locator('#schedule-time').focus()
    assert page.locator('#schedule-time').evaluate('(e)=>e===document.activeElement')
    page.get_by_role('checkbox',name='Martes',exact=True).check()
    page.locator('#schedule-time').fill('00:00')
    page.get_by_role('button',name='Guardar',exact=True).click()
    page.locator('#programacion [role=status]').first.wait_for()
    assert 'No se inició scraping' in page.locator('#programacion').inner_text()
    assert not program.service.cloud.launched
    out=Path('.tmp/programacion-20261116');out.mkdir(parents=True,exist_ok=True)
    page.screenshot(path=str(out/f'programacion-{viewport[0]}.png'),full_page=True)
    context.close()


def test_receipt_survives_history_pruning(program):
    cfg,date=ready(program)
    result=deliver(program,cfg,date)
    program.control.patch(result['id'],dict(status='completed',finished=now()))
    program.control.change(lambda d:d.update(runs=[]))
    assert deliver(program,cfg,date)['status']=='skipped'
    assert len(program.service.cloud.launched)==1


def test_real_oidc_verification_signature_audience_expiry(monkeypatch):
    import time
    import jwt
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives import serialization
    key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    pub=key.public_key().public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    class CertResponse:
        status=200
        data=json.dumps({'synthetic':pub}).encode()
    monkeypatch.setattr('ejecuciones.disparador.GoogleRequest',lambda:lambda *a,**kw:CertResponse())
    monkeypatch.setenv('RADAR_SCHEDULE_TARGET','https://private.run.app')
    claims=dict(iss='https://accounts.google.com',aud='https://private.run.app',iat=int(time.time()),exp=int(time.time())+300,sub='123',email='radar-scheduler@radar-inmobiliario-co.iam.gserviceaccount.com',email_verified=True)
    def token(values,signer=key):
        return 'Bearer '+jwt.encode(values,signer,algorithm='RS256',headers={'kid':'synthetic'})
    authenticate(token(claims))
    for invalid in [dict(claims,aud='other'),dict(claims,exp=int(time.time())-300),dict(claims,email='other@example.com')]:
        with pytest.raises(ValueError):authenticate(token(invalid))
    other=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    with pytest.raises(ValueError):authenticate(token(claims,other))


def test_scheduler_full_lifecycle_and_uncertain_patch(monkeypatch):
    monkeypatch.setenv('RADAR_SCHEDULE_TARGET','https://radar-schedule-review-test.us-central1.run.app')
    remote={}
    calls=[]
    fail=[]
    def handler(req):
        calls.append((req.method,str(req.url)))
        if req.method=='GET':return httpx.Response(200 if remote else 404,json=remote)
        if req.method=='PATCH':
            if fail:return httpx.Response(503,json={})
            state=remote['state'];remote.update(json.loads(req.content));remote['state']=state
        elif req.url.path.endswith(':pause'):remote['state']='PAUSED'
        elif req.url.path.endswith(':resume'):remote['state']='ENABLED'
        else:remote.update(json.loads(req.content),state='ENABLED')
        return httpx.Response(200,json=remote)
    with httpx.Client(transport=httpx.MockTransport(handler)) as session:
        scheduler=Scheduler(session)
        cfg=dict(validate([['metrocuadrado',A]],[1],'00:00'),enabled=True,revision=str(uuid4()))
        scheduler.sync(cfg)
        assert remote['state']=='ENABLED' and scheduler.matches(remote,cfg)
        cfg.update(enabled=False,revision=str(uuid4()))
        scheduler.sync(cfg)
        assert remote['state']=='PAUSED' and scheduler.matches(remote,cfg)
        cfg.update(enabled=True,revision=str(uuid4()))
        scheduler.sync(cfg)
        fail.append(True)
        with pytest.raises(httpx.HTTPStatusError):scheduler.sync(dict(cfg,time='01:00'))
        assert remote['state']=='PAUSED'
    assert sum(method=='POST' and url.endswith('/jobs') for method,url in calls)==1


def test_busy_shared_lock_skips_without_snapshot_or_queue(program,execution):
    cfg,date=ready(program)
    with execution[3]():
        result=deliver(program,cfg,date)
        assert result['status']=='skipped'
    assert deliver(program,cfg,date)['status']=='skipped'
    assert not program.service.cloud.launched


def test_trigger_never_downloads_snapshot_and_racing_lock_skips_worker(program,execution):
    cfg,date=ready(program)
    program.service.snapshot_searches=lambda *a:pytest.fail('El disparador no debe cargar snapshot')
    result=deliver(program,cfg,date)
    with execution[3]():
        assert not run_manual(execution[4]/'busy-worker',result['id'],program.control,execution[3],lambda *a:pytest.fail('no portal'))
    assert program.control.get(result['id'])['status']=='skipped'


def test_all_selected_disabled_after_reservation_skip_worker(program,execution):
    cfg,date=ready(program)
    result=deliver(program,cfg,date)
    from catalogo.persistencia.busquedas import BusquedasSQLite
    with execution[3]() as state:
        state.cargar(execution[4]/'disabled')
        repo=BusquedasSQLite(execution[4]/'disabled'/'metro-consola.sqlite')
        for key in (A,B):repo.cambiar_estado('metrocuadrado',key,False)
        state.guardar(execution[4]/'disabled')
    assert not run_manual(execution[4]/'no-selected-worker',result['id'],program.control,execution[3],lambda *a:pytest.fail('no portal'))
    assert program.control.get(result['id'])['status']=='skipped'


def test_authenticated_trigger_records_occurrence_once(program,monkeypatch):
    cfg,date=ready(program)
    monkeypatch.setattr('ejecuciones.disparador.authenticate',lambda header: None)
    monkeypatch.setattr('ejecuciones.disparador.ServicioEjecuciones',lambda:program.service)
    monkeypatch.setattr('ejecuciones.disparador.Scheduler',lambda:program.scheduler)
    client=TestClient(trigger_app)
    headers={'X-CloudScheduler-JobName':program.scheduler.name,'X-CloudScheduler-ScheduleTime':date.isoformat()}
    response=client.post('/trigger',json={'revision':cfg['revision']},headers=headers)
    assert response.status_code==202
    assert client.post('/trigger',json={'revision':cfg['revision']},headers=headers).json()['id']==response.json()['id']
    assert len(program.service.cloud.launched)==1
    assert client.post('/trigger',json={'revision':cfg['revision']},headers={**headers,'X-CloudScheduler-JobName':'wrong'}).status_code==422


def test_schedule_cas_stale_form_and_pending_operation(program):
    cfg,date=configure(program)
    with pytest.raises(Conflict):program.save(cfg['keys'],[1],'03:00','activate','old')
    program.scheduler.fail=True
    with pytest.raises(RuntimeError):program.save(cfg['keys'],[1],'03:00','activate',cfg['revision'])
    with pytest.raises(Conflict):program.save(cfg['keys'],[1],'03:00','pause',cfg['revision'])
    assert not program.read()['active']
