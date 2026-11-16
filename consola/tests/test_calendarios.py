"""Backend múltiple: GCS/Cloud simulados y SQLite sintético exclusivamente."""
import copy
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4, uuid5, NAMESPACE_URL
import pytest
from test_ejecuciones import execution, A, B, start, run_manual, fake_scrapers
from test_programacion import FakeScheduler
from ejecuciones.calendarios import Calendarios, plans, migrate, next_dates, validate_plan, LEGACY_ID
from ejecuciones.control import Conflict, IntegrityError, now
from ejecuciones.programacion import Programacion, DEFAULT, TZ, cron
from ejecuciones.cloud_run import reconcile

@pytest.fixture
def multi(execution):
    svc=execution[0];svc.overview(refresh=True)
    return Calendarios(svc, FakeScheduler())

def values(**kw):
    return dict(name='Carolina',keys=[['metrocuadrado',A]],frequency='daily',days=[],hour='9',minute='0',enabled=True) | kw

def create(multi, **kw):
    v=values();v.update(kw)
    return multi.change('create',values=v)

def arm(multi, ids):
    tick=datetime.now(timezone.utc).replace(second=0,microsecond=0)
    def change(d):
        for key in ids:
            p=d['schedules'][key]
            p.update(time=tick.astimezone(TZ).strftime('%H:%M'),days=list(range(7)),date=tick.astimezone(TZ).date().isoformat(),effective_after=(tick-timedelta(days=1)).isoformat(),cursor=(tick-timedelta(minutes=1)).isoformat())
    multi.control.change(change)
    return tick

def deliver(multi, tick):
    return multi.tick(multi.scheduler.name,multi.control.read()[0]['schedule']['revision'],tick.isoformat())

def test_independent_crud_and_restart(multi):
    a=create(multi);b=create(multi,name='Norte',keys=[['metrocuadrado',B]],frequency='weekly',days=[1,4],hour='23',minute='59')
    assert len(multi.read()['items'])==2 and cron(multi.control.read()[0]['schedule'])=='* * * * *'
    original=copy.deepcopy(b)
    a=multi.change('edit',a['id'],values(name='Otro'),a['revision'])
    assert multi.control.read()[0]['schedules'][b['id']]==original
    a=multi.change('pause',a['id'],expected=a['revision']);assert not a['enabled']
    a=multi.change('activate',a['id'],expected=a['revision']);assert a['enabled']
    duplicate=multi.change('duplicate',a['id'],expected=a['revision'])
    assert duplicate['id']!=a['id'] and not duplicate['enabled'] and duplicate['last_run'] is None
    multi.change('delete',a['id'],expected=a['revision'])
    rebuilt=Calendarios(multi.service,multi.scheduler)
    assert len(rebuilt.read()['items'])==2 and len(rebuilt.control.read()[0]['schedules'])==3
    assert not multi.service.cloud.launched

@pytest.mark.parametrize('field,value',[('name',''),('frequency','monthly'),('hour','24'),('hour',True),('minute','60'),('keys',[]),('days',[]),('days',[True]),('days',[7]),('date','2026-02-30')])
def test_invalid_fields(multi,field,value):
    v=values();v.update(frequency='weekly');v[field]=value
    if field=='date':v['frequency']='once'
    with pytest.raises(ValueError):multi.change('create',values=v)
    assert not multi.service.cloud.launched

@pytest.mark.parametrize('frequency,days,clock,after,expected',[
    ('daily',list(range(7)),'00:00','2026-12-31T23:59:59-05:00','2027-01-01T00:00'),
    ('weekly',[0],'09:00','2026-11-16T09:00:00-05:00','2026-11-23T09:00'),
    ('daily',list(range(7)),'23:59','2028-02-28T23:59:00-05:00','2028-02-29T23:59'),
    ('once',list(range(7)),'09:00','2026-12-31T23:59:59-05:00','2027-01-01T09:00')])
def test_dates_and_bogota(frequency,days,clock,after,expected):
    p=dict(frequency=frequency,enabled=True,days=days,time=clock,date='2027-01-01',effective_after='2020-01-01T00:00:00+00:00')
    result=next_dates(p,datetime.fromisoformat(after))[0]
    assert result.startswith(expected) and result.endswith('-05:00')
    with pytest.raises(ValueError):next_dates(p,datetime(2026,1,1))

def test_coincident_duplicate_ticks_and_manual_conflicts(multi,execution):
    a=create(multi);b=create(multi,name='Otra')
    tick=arm(multi,[a['id'],b['id']])
    with ThreadPoolExecutor(4) as pool: results=list(pool.map(lambda _:deliver(multi,tick),range(4)))
    runs=multi.control.read()[0]['runs']
    assert len(runs)==2 and sorted(r['status'] for r in runs)==['launching','skipped']
    assert len(multi.service.cloud.launched)==1
    assert all(r['schedule_id'] and r['schedule_name'] for r in runs)
    with pytest.raises(Conflict):start(execution)
    multi.control.patch(multi.service.cloud.launched[0],dict(status='completed',finished=now()))
    multi.control.change(lambda d:d.update(runs=[]))
    deliver(multi,tick)
    assert len(multi.service.cloud.launched)==1

def test_manual_busy_and_durable_rebuild(multi,execution):
    a=create(multi);tick=arm(multi,[a['id']]);manual=start(execution)
    result=deliver(multi,tick)['occurrences'][0]
    assert result['status']=='skipped' and 'curso' in result['error']
    rebuilt=Calendarios(multi.service,multi.scheduler)
    assert deliver(rebuilt,tick)['occurrences']==[]
    assert multi.service.cloud.launched==[manual['id']]

def test_pause_fences_claim_but_started_continues(multi,execution):
    a=create(multi);tick=arm(multi,[a['id']]);r=deliver(multi,tick)['occurrences'][0]
    a=multi.change('pause',a['id'],expected=a['revision'])
    assert not run_manual(execution[4]/'fenced',r['id'],multi.control,execution[3],lambda *a:pytest.fail('no portal'))
    assert multi.control.get(r['id'])['status']=='skipped'
    a=multi.change('activate',a['id'],expected=a['revision']);tick=arm(multi,[a['id']]);r=deliver(multi,tick)['occurrences'][0]
    called=[];paused=[]
    def hook():
        if not paused:paused.append(multi.change('pause',a['id'],expected=a['revision']))
    assert run_manual(execution[4]/'started',r['id'],multi.control,execution[3],fake_scrapers(['completed'],called,hook),heartbeat=.001)
    assert multi.control.get(r['id'])['persisted'] and called==[A]

def test_once_consumes_even_on_skip_and_never_rearms(multi,execution):
    a=create(multi,frequency='once',date=(datetime.now(TZ)+timedelta(days=1)).date().isoformat())
    tick=arm(multi,[a['id']]);r=deliver(multi,tick)['occurrences'][0]
    assert not next_dates(multi.control.read()[0]['schedules'][a['id']])
    assert run_manual(execution[4]/'once',r['id'],multi.control,execution[3],fake_scrapers(['completed'],[]),heartbeat=.001)
    assert deliver(multi,tick)['occurrences']==[]
    with pytest.raises(ValueError):multi.change('activate',a['id'],expected=a['revision'])
    a=multi.change('delete',a['id'],expected=a['revision'])
    assert multi.control.get(r['id'])['schedule_name']=='Carolina'

def test_migration_idempotent_preserves_legacy_identity_and_all_data(multi):
    stamp=datetime.now(timezone.utc).replace(second=0,microsecond=0)
    old=dict(DEFAULT,keys=[['metrocuadrado',A],['metrocuadrado',B],['wasi','synthetic']],days=[0],time='09:00',enabled=True,revision=str(uuid4()),effective_after=(stamp-timedelta(days=1)).isoformat())
    document=dict(schedule=old,runs=[{'id':'old'}],other={'preserve':True})
    untouched=copy.deepcopy(document)
    projection=plans(document,stamp.isoformat());assert document==untouched
    assert projection[LEGACY_ID]['keys']==old['keys'] and projection[LEGACY_ID]['enabled']
    migrate(document,stamp.isoformat());first=copy.deepcopy(document);migrate(document);assert document==first
    assert document['schedule_legacy']==old and document['runs']==untouched['runs'] and document['other']==untouched['other']
    document['schedules_version']=2
    with pytest.raises(IntegrityError):plans(document)
    with pytest.raises(IntegrityError):migrate(document)

def test_migrated_occurrence_retains_legacy_receipt(multi):
    stamp=datetime.now(timezone.utc).replace(second=0,microsecond=0)
    old=dict(DEFAULT,keys=[['metrocuadrado',A]],days=list(range(7)),time=stamp.astimezone(TZ).strftime('%H:%M'),enabled=True,revision=str(uuid4()),effective_after=(stamp-timedelta(days=1)).isoformat())
    multi.control.change(lambda d:d.update(schedule=old))
    first=Programacion(multi.service,multi.scheduler).deliver(multi.scheduler.name,old['revision'],stamp.isoformat())
    multi.control.patch(first['id'],dict(status='completed',finished=now()))
    multi.change('create',values=values(enabled=False))
    multi.control.change(lambda d:d['schedules'][LEGACY_ID].update(cursor=(stamp-timedelta(minutes=1)).isoformat()))
    result=deliver(multi,stamp)
    assert result['occurrences'][0]['id']==first['id'] and len(multi.service.cloud.launched)==1

def test_pending_timeout_and_cas_failure_block_launch(multi,execution):
    a=create(multi);before=copy.deepcopy(a);multi.scheduler.fail=True
    with pytest.raises(RuntimeError):multi.change('pause',a['id'],expected=a['revision'])
    assert multi.read()['error'] and multi.control.read()[0]['schedules'][a['id']]==before
    with pytest.raises(Conflict):multi.change('pause',a['id'],expected=a['revision'])
    multi.control.change(lambda d:d['schedule']['pending'].update(at='2020-01-01T00:00:00+00:00'))
    multi.scheduler.fail=False
    assert not multi.change('pause',a['id'],expected=a['revision'])['enabled']
    blob=multi.control.blob;blob.fail=True;calls=len(multi.scheduler.calls)
    with pytest.raises(RuntimeError):create(multi)
    assert len(multi.scheduler.calls)==calls and not multi.service.cloud.launched

def test_lost_launch_response_reconciles_without_relaunch(multi,execution):
    a=create(multi);tick=arm(multi,[a['id']]);multi.service.cloud.uncertain=True
    r=deliver(multi,tick)['occurrences'][0]
    multi.control.patch(r['id'],dict(created=(tick-timedelta(minutes=15)).isoformat()))
    reconcile(multi.control,multi.service.cloud,multi.service.unlock,force=True)
    assert multi.control.get(r['id'])['status']=='interrupted'
    assert deliver(multi,tick)['occurrences']==[] and len(multi.service.cloud.launched)==1
    assert not run_manual(execution[4]/'late',r['id'],multi.control,execution[3],lambda *a:pytest.fail('no portal'))

def test_stale_forms_shared_lock_and_overdue_audit(multi,execution):
    a=create(multi)
    with pytest.raises(Conflict):multi.change('pause',a['id'],expected='old')
    tick=arm(multi,[a['id']])
    with execution[3]():result=deliver(multi,tick)['occurrences'][0]
    assert result['status']=='skipped' and not multi.service.cloud.launched
    multi.control.change(lambda d:d['schedules'][a['id']].update(cursor=(tick-timedelta(days=2)).isoformat(),effective_after=(tick-timedelta(days=3)).isoformat()))
    results=deliver(multi,tick)['occurrences']
    assert any('15 minutos' in (r.get('error') or '') for r in results)

def test_selected_removed_and_multi_source_names(multi,execution):
    a=create(multi,keys=[['metrocuadrado',A],['metrocuadrado',B]])
    tick=arm(multi,[a['id']])
    with execution[3]() as state:
        state.cargar(execution[4]/'removed')
        from catalogo.persistencia.busquedas import BusquedasSQLite
        repo=BusquedasSQLite(execution[4]/'removed'/'metro-consola.sqlite');repo.eliminar('metrocuadrado',A)
        repo.cambiar_estado('metrocuadrado',B,False);state.guardar(execution[4]/'removed')
    r=deliver(multi,tick)['occurrences'][0]
    assert not run_manual(execution[4]/'empty-worker',r['id'],multi.control,execution[3],lambda *a:pytest.fail('no portal'))
    assert multi.control.get(r['id'])['status']=='skipped'


def test_obsolete_occurrence_cannot_consume_edited_once(multi):
    a=create(multi);tick=arm(multi,[a['id']]);old=copy.deepcopy(multi.control.read()[0]['schedules'][a['id']])
    edited=multi.change('edit',a['id'],values(frequency='once',date=(datetime.now(TZ)+timedelta(days=1)).date().isoformat()),a['revision'])
    occ=dict(job=multi.scheduler.name,revision=old['revision'],schedule_id=a['id'],schedule_name=old['name'],scheduled_at=tick.isoformat())
    r=multi.submit(str(uuid4()),occ,old)
    assert r['status']=='skipped' and multi.control.read()[0]['schedules'][a['id']]==edited

def test_mixed_portal_selection_uses_search_keys(multi):
    rows=[dict(fuente=f,id_busqueda=k,nombre=f,url='https://synthetic.test',activa=True) for f,k in [('metrocuadrado',A),('wasi','wasi:1'),('fincaraiz','finca:1')]]
    multi.service.snapshot_searches=lambda action:action(rows)
    p=create(multi,keys=[[b['fuente'],b['id_busqueda']] for b in rows])
    assert len(p['keys'])==3 and not multi.service.cloud.launched

def test_http_crud_preview_and_errors(multi,monkeypatch):
    from fastapi.testclient import TestClient
    from metro.web import app
    import json
    monkeypatch.setenv('RADAR_SCHEDULE_TARGET','https://synthetic.run.app')
    monkeypatch.setattr('ejecuciones.scheduler.Scheduler',lambda:multi.scheduler)
    client=TestClient(app)
    html=client.get('/v0.6/ejecuciones/programaciones')
    assert html.status_code==200 and 'Nueva programación' in html.text
    assert '<details id="plan-editor" class="plan-editor" >' in html.text
    body=dict(name='Mañanas',frequency='daily',hour='9',minute='0',schedule_search=json.dumps(['metrocuadrado',A]),action='create')
    before=multi.control.read()
    assert client.post('/v0.6/ejecuciones/programaciones/previsualizar',data=body).status_code==200
    assert multi.control.read()==before and not multi.service.cloud.launched
    invalid=client.post('/v0.6/ejecuciones/programaciones',data=dict(body,hour='24'))
    assert invalid.status_code==422 and 'Selecciona hora y minutos válidos' in invalid.text
    assert client.post('/v0.6/ejecuciones/programaciones',data=body).status_code==200
    p=list(multi.control.read()[0]['schedules'].values())[0]
    for action in ['activate','pause','duplicate']:
        assert client.post('/v0.6/ejecuciones/programaciones',data=dict(action=action,id=p['id'],revision=p['revision'])).status_code==200
        p=multi.control.read()[0]['schedules'][p['id']]
    assert client.post('/v0.6/ejecuciones/programaciones',data=dict(action='delete',id=p['id'],revision=p['revision'])).status_code==422
    assert client.post('/v0.6/ejecuciones/programaciones',data=dict(action='delete',id=p['id'],revision=p['revision'],confirm='yes')).status_code==200
    assert not multi.service.cloud.launched
    assert client.post('/v0.6/ejecuciones/programaciones',data=body,headers={'Origin':'https://evil.example'}).status_code==403

def test_spinner_only_for_confirmed_running_and_terminal_stops():
    from consola.v06 import templates
    template=templates.env.get_template('v06/_estado_ejecucion.html')
    macro=template.module.estado
    from consola.ejecuciones import LABELS
    for state,verified,spins in [('running','active',True),('saving','active',True),('running','unavailable',False),('launching','active',False),('completed','active',False),('skipped','active',False)]:
        html=macro(dict(status=state,verification=dict(state=verified)),LABELS)
        assert ('radar-spinner' in html)==spins
        if spins:assert 'En ejecución' in html


@pytest.mark.parametrize('viewport',[(1440,900),(768,1024),(390,844)])
def test_browser_multiple_crud_keyboard_and_preview(multi,execution,monkeypatch,chromium,viewport):
    from fastapi.testclient import TestClient
    from metro.web import app
    from urllib.parse import urlsplit
    from pathlib import Path
    from playwright.sync_api import expect
    monkeypatch.setenv('RADAR_SCHEDULE_TARGET','https://synthetic.run.app')
    monkeypatch.setattr('ejecuciones.scheduler.Scheduler',lambda:multi.scheduler)
    create(multi,name='Lunes · Carolina',frequency='weekly',days=[0])
    create(multi,name='Tardes · Norte',keys=[['metrocuadrado',B]],hour='18',minute='30',enabled=False)
    client=TestClient(app);ctx=chromium.new_context(viewport=dict(width=viewport[0],height=viewport[1]),reduced_motion='reduce');page=ctx.new_page();page.set_default_timeout(8000)
    def routed(route):
        req=route.request;url=urlsplit(req.url)
        res=client.request(req.method,url.path+('?' + url.query if url.query else ''),content=req.post_data_buffer)
        route.fulfill(status=res.status_code,headers={k:v for k,v in res.headers.items() if k.lower() not in {'content-length','content-encoding'}},body=res.content)
    page.route('**/*',routed);page.goto('http://127.0.0.1/v0.6/ejecuciones/programaciones')
    assert not page.locator('#plan-editor').evaluate('(e)=>e.open')
    assert page.locator('.plan-table tbody tr').count()==2
    page.get_by_role('link',name='+ Nueva programación',exact=True).click()
    page.get_by_label('Nombre',exact=True).fill('Mañanas diarias')
    page.get_by_label('Carolina',exact=True).check()
    page.get_by_label('Frecuencia',exact=True).select_option('daily')
    page.get_by_label('Hora',exact=True).select_option('7');page.get_by_label('Minutos',exact=True).select_option('5')
    expect(page.locator('[data-plan-preview]')).to_contain_text('Próxima ejecución prevista:')
    assert page.locator('#plan-hour option').count()==24 and page.locator('#plan-minute option').count()==60
    page.get_by_role('button',name='Guardar programación',exact=True).click()
    expect(page.get_by_role('status').first).to_contain_text('Configuración guardada')
    row=page.locator('.plan-table tbody tr').filter(has_text='Mañanas diarias')
    row.get_by_role('link',name='Editar',exact=True).click()
    page.get_by_label('Nombre',exact=True).fill('Mañanas editadas')
    page.get_by_role('button',name='Guardar programación',exact=True).click()
    row=page.locator('.plan-table tbody tr').filter(has_text='Mañanas editadas')
    row.get_by_text('Más acciones',exact=True).click();row.get_by_role('button',name='Activar',exact=True).click()
    row=page.locator('.plan-table tbody tr').filter(has_text='Mañanas editadas')
    row.get_by_text('Más acciones',exact=True).click();row.get_by_role('button',name='Pausar',exact=True).click()
    row=page.locator('.plan-table tbody tr').filter(has_text='Mañanas editadas')
    row.get_by_text('Más acciones',exact=True).click();row.get_by_role('button',name='Duplicar',exact=True).click()
    row=page.locator('.plan-table tbody tr').filter(has_text='Copia de Mañanas editadas')
    row.get_by_text('Más acciones',exact=True).click();row.get_by_text('Eliminar',exact=True).click()
    assert 'Sus ejecuciones anteriores se conservan' in row.inner_text()
    row.get_by_role('button',name='Confirmar eliminación',exact=True).click()
    assert page.locator('.plan-table tbody tr').count()==3
    page.keyboard.press('Tab');assert page.evaluate('document.activeElement !== document.body')
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    out=Path('.tmp/multiple-20261116/screenshots');out.mkdir(parents=True,exist_ok=True)
    page.screenshot(path=str(out/f'multiple-{viewport[0]}.png'),full_page=True)
    page.get_by_role('link',name='+ Nueva programación',exact=True).click()
    page.screenshot(path=str(out/f'formulario-{viewport[0]}.png'),full_page=True)
    assert not multi.service.cloud.launched
    ctx.close()


def test_browser_spinner_live_stops_and_reduced_motion(multi,execution,monkeypatch,chromium):
    from fastapi.testclient import TestClient
    from metro.web import app
    from urllib.parse import urlsplit
    from playwright.sync_api import expect
    monkeypatch.setenv('RADAR_SCHEDULE_TARGET','https://synthetic.run.app')
    monkeypatch.setattr('ejecuciones.scheduler.Scheduler',lambda:multi.scheduler)
    r=start(execution)
    multi.control.patch(r['id'],dict(status='running',verification=dict(state='active',checked=now())))
    doc=multi.control.read()[0]
    multi.service.overview=lambda refresh=False:(doc,None)
    multi.service.report=lambda d,*a:d
    client=TestClient(app);ctx=chromium.new_context(reduced_motion='reduce');page=ctx.new_page();page.set_default_timeout(8000)
    def routed(route):
        req=route.request;url=urlsplit(req.url)
        res=client.request(req.method,url.path+('?' + url.query if url.query else ''),content=req.post_data_buffer)
        route.fulfill(status=res.status_code,headers={k:v for k,v in res.headers.items() if k.lower() not in {'content-length','content-encoding'}},body=res.content)
    page.route('**/*',routed);page.clock.install();page.goto('http://127.0.0.1/v0.6/ejecuciones/programaciones')
    assert page.locator('.radar-spinner').count()==1
    assert page.locator('.radar-spinner').evaluate('(e)=>getComputedStyle(e).animationName')=='none'
    doc['runs'][0].update(status='completed',finished=now())
    page.clock.run_for(15100)
    expect(page.locator('.radar-spinner')).to_have_count(0)
    expect(page.locator('[data-plan-activity]')).to_contain_text('Completada')
    ctx.close()


def test_legacy_pending_recovery_does_not_inherit_per_plan_gate(multi):
    old=dict(DEFAULT,keys=[['metrocuadrado',A]],days=[0],time='09:00',enabled=True,revision=str(uuid4()),effective_after=now(),pending=dict(at='2020-01-01T00:00:00+00:00',token='old'))
    multi.control.change(lambda d:d.update(schedule=old))
    create(multi,enabled=False)
    migrated=multi.control.read()[0]['schedules'][LEGACY_ID]
    assert migrated['enabled'] and 'pending' not in migrated
    tick=arm(multi,[LEGACY_ID]);assert deliver(multi,tick)['occurrences'][0]['status']=='launching'

def test_finish_cas_failure_pending_blocks_until_explicit_recovery(multi):
    a=create(multi);sync=multi.scheduler.sync
    def fail_finish(cfg):
        sync(cfg);multi.control.blob.fail=True
    multi.scheduler.sync=fail_finish
    with pytest.raises(RuntimeError):multi.change('pause',a['id'],expected=a['revision'])
    multi.control.blob.fail=False
    assert multi.control.read()[0]['schedules'][a['id']]==a and multi.read()['error']
    multi.control.change(lambda d:d['schedule']['pending'].update(at='2020-01-01T00:00:00+00:00'))
    multi.scheduler.sync=sync
    assert not multi.change('pause',a['id'],expected=a['revision'])['enabled']
    assert not multi.service.cloud.launched

def test_trigger_multiple_endpoint_and_old_client_fenced(multi,monkeypatch):
    from fastapi.testclient import TestClient
    from ejecuciones.disparador import app
    a=create(multi);tick=arm(multi,[a['id']])
    monkeypatch.setattr('ejecuciones.disparador.authenticate',lambda *a:None)
    monkeypatch.setattr('ejecuciones.disparador.ServicioEjecuciones',lambda:multi.service)
    monkeypatch.setattr('ejecuciones.disparador.Scheduler',lambda:multi.scheduler)
    cfg=multi.control.read()[0]['schedule'];client=TestClient(app)
    body=dict(revision=cfg['revision']);headers={'X-CloudScheduler-JobName':multi.scheduler.name.rsplit('/',1)[-1],'X-CloudScheduler-ScheduleTime':tick.isoformat()}
    result=client.post('/trigger',json=body,headers=headers)
    assert result.status_code==202 and len(result.json()['occurrences'])==1
    assert client.post('/trigger',json=body,headers=headers).json()['occurrences']==[]
    assert len(multi.service.cloud.launched)==1
    with pytest.raises(Conflict):Programacion(multi.service,multi.scheduler).save(a['keys'],[0],'09:00','save',cfg['revision'])


def test_browser_without_javascript_preview_and_save(multi,monkeypatch,chromium):
    from fastapi.testclient import TestClient
    from metro.web import app
    from urllib.parse import urlsplit
    from playwright.sync_api import expect
    monkeypatch.setenv('RADAR_SCHEDULE_TARGET','https://synthetic.run.app')
    monkeypatch.setattr('ejecuciones.scheduler.Scheduler',lambda:multi.scheduler)
    client=TestClient(app);ctx=chromium.new_context(java_script_enabled=False);page=ctx.new_page()
    def routed(route):
        req=route.request;url=urlsplit(req.url)
        res=client.request(req.method,url.path+('?' + url.query if url.query else ''),content=req.post_data_buffer)
        route.fulfill(status=res.status_code,headers={k:v for k,v in res.headers.items() if k.lower() not in {'content-length','content-encoding'}},body=res.content)
    page.route('**/*',routed);page.goto('http://127.0.0.1/v0.6/ejecuciones/programaciones?nuevo=1')
    page.get_by_label('Nombre',exact=True).fill('Sin JavaScript')
    page.get_by_label('Carolina',exact=True).check()
    page.get_by_label('Lunes',exact=True).check()
    before=multi.control.read()
    page.get_by_role('button',name='Vista previa',exact=True).click()
    expect(page.locator('[data-plan-preview]')).to_contain_text('Próxima ejecución prevista:')
    assert multi.control.read()==before
    page.get_by_role('button',name='Guardar programación',exact=True).click()
    expect(page.locator('.plan-table')).to_contain_text('Sin JavaScript')
    assert not multi.service.cloud.launched
    ctx.close()


def test_pending_change_of_other_plan_does_not_cancel_reserved_worker(multi,execution):
    a=create(multi);b=create(multi,name='Independiente')
    tick=arm(multi,[a['id']])
    # Solo A vence en este minuto; B mantiene su hora original.
    r=deliver(multi,tick)['occurrences'][0]
    assert r['schedule_id']==a['id']
    multi.scheduler.fail=True
    with pytest.raises(RuntimeError):multi.change('pause',b['id'],expected=b['revision'])
    called=[]
    assert run_manual(execution[4]/'independent-worker',r['id'],multi.control,execution[3],fake_scrapers(['completed'],called),heartbeat=.001)
    assert called==[A] and multi.control.get(r['id'])['persisted']
