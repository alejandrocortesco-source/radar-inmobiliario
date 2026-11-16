"""Resultados finales con SQLite y snapshots sintéticos; sin Cloud ni portales."""
import copy
import hashlib
import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from google.api_core.exceptions import NotFound

from metro.storage import Store
from metro.web import app
from ejecuciones.resultados import FINAL_KEYS, final_result, from_db, summarize, valid
from ejecuciones.worker import metrics
from ejecuciones.informes import SnapshotReports, project
from ejecuciones.control import now
from wasi.durable import empaquetar
from test_ejecuciones import execution

A = 'https://www.metrocuadrado.com/inmuebles/venta/bogota/la-carolina'


def detail(amount=1000000, title='Ficha sintética'):
    return {'quality':'success','normalized':{'price':amount,'operation':'venta','currency':'COP','title':title}}


def job(status='success', previous=1000000, amount=1000000):
    return {'status':status,'classification':'review','decision_reason':'price_not_comparable','attempts':1,
            'previous_price_json':json.dumps({'status':'valid','amount':str(previous),'currency':'COP','operation':'venta'}),
            'data_json':json.dumps(detail(amount))}


def make_69(folder, source='metrocuadrado'):
    folder.mkdir(parents=True, exist_ok=True)
    key = {'metrocuadrado':A,'wasi':'wasi:sintetica','fincaraiz':'fincaraiz:sintetica'}[source]
    filename = {'metrocuadrado':'metro.sqlite','wasi':'wasi.sqlite','fincaraiz':'fincaraiz.sqlite'}[source]
    store = Store(folder/filename, normalizar_busqueda=lambda v:v)
    def listing(i, uncomparable=False):
        return {'id':str(i),'url':'https://example.invalid/'+str(i),'group':'results',
                'raw':{'businessType':'venta','mvalorventa':None if uncomparable else 1000000,'currency':'COP'}}
    first = store.new_run(key, {'urls':[key],'listing_currency':'COP'})
    store.save_page(first,1,'1',key,'baseline',[listing(i) for i in range(68)],None,search_url=key)
    store.plan_incremental(first)
    for i in range(68):store.result(first,str(i),'success',detail())
    store.update_search(first,key,complete=True)
    store.update_run(first,status='completed',finished=now())
    run = store.new_run(key, {'urls':[key],'listing_currency':'COP'})
    store.save_page(run,1,'1',key,'new',[listing(i,55<=i<68) for i in range(69)],None,search_url=key)
    store.plan_incremental(run)
    for i in range(55,69):store.attempt(run,str(i));store.result(run,str(i),'success',detail())
    store.update_search(run,key,complete=True)
    store.update_run(run,status='completed',finished=now())
    return store,run,key


@pytest.mark.parametrize('source',['metrocuadrado','wasi','fincaraiz'])
def test_69_shared_sources_and_preserves_initial_reasons(tmp_path, source):
    store,run,key = make_69(tmp_path/source,source)
    before = hashlib.sha256(Path(store.path).read_bytes()).hexdigest()
    result = metrics(SimpleNamespace(store=store,run_id=run))
    assert (result['processed'],result['new'],result['changed'],result['unchanged']) == (69,1,0,68)
    assert (result['reused'],result['reread_unchanged'],result['pending']) == (55,13,0)
    assert valid(result) and sum(result[k] for k in FINAL_KEYS)==69
    with store.connect() as db:
        assert db.execute("SELECT count(*) FROM jobs WHERE run_id=? AND classification='review' AND decision_reason='price_not_comparable'",(run,)).fetchone()[0]==13
        assert from_db(db,run,key)['unchanged']==68
    assert hashlib.sha256(Path(store.path).read_bytes()).hexdigest()==before


@pytest.mark.parametrize('case,expected', [
    (job(),'unchanged'),(job(amount=1100000),'changed'),
    (job(status='partial'),'partial'),(job(status='failed'),'failed'),
    (job(status='blocked'),'blocked'),(job(status='pending'),'pending'),
    (job(status='processing'),'pending'),
])
def test_resolved_review_and_technical_outcomes(case, expected):
    original=copy.deepcopy(case)
    result=summarize([case])
    assert result[expected]==1 and valid(result)
    assert result['processed']==(0 if expected=='pending' else 1)
    assert case==original


@pytest.mark.parametrize('patch', [
    {'previous_price_json':None}, {'previous_price_json':'{}'},
    {'previous_price_json':'invalid'}, {'data_json':None},
    {'data_json':json.dumps({'quality':'success','normalized':{}})},
    {'data_json':json.dumps({'quality':'success','normalized':[]})},
    {'previous_price_json':json.dumps({'status':'valid','currency':'COP','operation':'venta'})},
    {'classification':'legacy','previous_price_json':None},
    {'previous_price_json':json.dumps({'status':'valid','amount':'NaN','currency':'COP','operation':'venta'})},
])
def test_success_without_comparison_evidence_is_explicitly_unclassified(patch):
    row=dict(job(),**patch)
    result=summarize([row])
    assert result['unclassified']==result['processed']==1
    assert result['unchanged']==result['changed']==result['new']==0
    assert valid(result)


def test_price_comparison_is_not_content_equality():
    row=job(); row['data_json']=json.dumps(detail(title='Otro contenido'))
    assert final_result(row)=='unchanged'


def test_exclusive_results_and_pending_outside_processed():
    rows=[job(),job(amount=2),job(status='partial'),job(status='failed'),job(status='blocked'),
          dict(job(),previous_price_json=None),job(status='pending')]
    result=summarize(rows)
    assert result['processed']==6 and result['pending']==1
    assert sum(result[k] for k in FINAL_KEYS)==6
    assert result['reread_unchanged']==1 and result['reused']==0


class Bucket:
    def __init__(self,name,archive):self.name=name;self.archive=archive;self.calls=[];self.missing=False
    def blob(self,name,generation=None):
        assert name=='radar/state.tar.gz' and generation==17
        parent=self
        class Blob:
            def download_to_filename(self,path,if_generation_match,timeout):
                assert if_generation_match==17
                parent.calls.append(generation)
                if parent.missing:raise NotFound('sensitive body not for UI')
                Path(path).write_bytes(parent.archive)
        return Blob()


def historical(folder, source='wasi'):
    store,run,key=make_69(folder/'state',source)
    bucket=Bucket(str(folder),empaquetar(folder/'state'))
    class State:
        objeto='radar/state.tar.gz'
        def __enter__(self):pytest.fail('No adquirir bloqueo')
        def cargar(self,*a):pytest.fail('No cargar snapshot vigente')
        @property
        def lock(self):pytest.fail('No tocar bloqueo')
    state=State();state.bucket=bucket
    reader=SnapshotReports(lambda:state, folder/'reports')
    row={'fuente':source,'id_busqueda':key,'technical_run':run,'nombre':'Wasi sintética',
         'url':'https://example.invalid/','activa':True,'status':'completed','started':now(),'finished':now(),
         'duration':360,'processed':69,'new':1,'changed':0,'unchanged':55,'listing_error_count':0,'error_count':0,
         'listing_complete':True,'listing_pages':2,'listing_code':None,'error':None}
    record={'id':str(uuid4()),'created':now(),'started':now(),'updated':now(),'finished':now(),
            'job':'radar-manual','worker':'synthetic','status':'completed','phase':'Guardado remoto confirmado',
            'persisted':True,'snapshot_generation':'17','searches':[row]}
    doc={'runs':[record],'searches':[row],'catalog_updated':now()}
    return doc,reader,bucket,store


@pytest.mark.parametrize('source',['metrocuadrado','wasi','fincaraiz'])
def test_historical_projection_pins_snapshot_is_readonly_and_cached(tmp_path,source):
    doc,reader,bucket,store=historical(tmp_path,source)
    original=copy.deepcopy(doc);before=hashlib.sha256(Path(store.path).read_bytes()).hexdigest()
    first=project(doc,reader)
    row=first['runs'][0]['searches'][0]
    assert row['unchanged']==68 and row['reported']['unchanged']==55
    assert row['report_origin']=='snapshot' and row['report_generation']=='17'
    # El catálogo posterior no es evidencia de esta ejecución histórica.
    with store.connect() as db:db.execute("UPDATE properties SET data_json=NULL")
    assert project(doc,SnapshotReports(reader.state_factory,reader.data_dir))['runs'][0]['searches'][0]['unchanged']==68
    assert bucket.calls==[17] and doc==original
    assert not list(reader.data_dir.glob('report-read-*'))
    # El único cambio local fue la mutación sintética explícita de esta prueba.
    assert before != hashlib.sha256(Path(store.path).read_bytes()).hexdigest()


def test_missing_historical_snapshot_is_not_replaced_by_current_data(tmp_path):
    doc,reader,bucket,_=historical(tmp_path)
    bucket.missing=True
    row=project(doc,reader)['runs'][0]['searches'][0]
    assert row['processed']==69 and row['unchanged'] is None and row['new'] is None
    assert row['reported']['unchanged']==55
    assert 'sensitive' not in json.dumps(row)


def test_active_old_worker_does_not_read_snapshot(tmp_path):
    doc,reader,bucket,_=historical(tmp_path)
    doc['runs'][0]['status']='running'
    project(doc,reader)
    assert bucket.calls==[]


def test_old_schema_counts_unknown_without_migration(tmp_path):
    file=tmp_path/'old.sqlite'
    with sqlite3.connect(file) as db:
        db.executescript("CREATE TABLE runs(id,config_json);INSERT INTO runs VALUES(1,'{}');CREATE TABLE jobs(run_id,status,data_json);INSERT INTO jobs VALUES(1,'success','{}');")
    before=file.read_bytes()
    with sqlite3.connect(file.as_uri()+'?mode=ro&immutable=1',uri=True) as db:
        result=from_db(db,1)
    assert result['unclassified']==1 and result['processed']==1
    assert file.read_bytes()==before


@pytest.mark.parametrize('viewport',[(1440,900),(768,1024),(390,844)])
def test_report_ui_api_reload_and_visual_evidence(execution,chromium,viewport,tmp_path):
    from urllib.parse import urlsplit
    from playwright.sync_api import expect
    svc=execution[0]
    doc,reader,bucket,_=historical(tmp_path/'visual')
    original=copy.deepcopy(doc)
    svc.reports=reader
    svc.overview=lambda refresh=False:(doc,None)
    client=TestClient(app)
    response=client.get('/v0.6/ejecuciones/estado?run='+doc['runs'][0]['id'])
    assert response.status_code==200
    row=response.json()['run']['searches'][0]
    assert row['processed']==69 and row['unchanged']==68 and row['reused']==55 and row['reread_unchanged']==13
    context=chromium.new_context(viewport={'width':viewport[0],'height':viewport[1]})
    page=context.new_page()
    def route(route):
        url=urlsplit(route.request.url)
        result=client.get(url.path+('?' + url.query if url.query else ''))
        route.fulfill(status=result.status_code,headers={k:v for k,v in result.headers.items() if k.lower() not in ('content-length','content-encoding')},body=result.content)
    page.route('**/*',route)
    try:
        page.goto('http://127.0.0.1/v0.6/ejecuciones?run='+doc['runs'][0]['id'])
        expect(page.locator('[data-execution-report]')).to_contain_text('1 / 0 / 68')
        expect(page.locator('[data-result-totals]')).to_contain_text('55 fichas reutilizadas y 13 releídas')
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
        out=Path.cwd()/'.tmp/resultados-finales-20261116';out.mkdir(parents=True,exist_ok=True)
        page.screenshot(path=str(out/f'informe-69-{viewport[0]}.png'),full_page=True)
        page.locator('[data-execution-report]').screenshot(path=str(out/f'informe-69-panel-{viewport[0]}.png'))
        page.evaluate('poll()')
        expect(page.locator('[data-execution-report]')).to_contain_text('1 / 0 / 68')
        page.reload()
        assert doc==original and bucket.calls==[17]
        # Sin evidencia: N/D explícito y acceso al informe original, no 55 corregidos por suposición.
        reader.cache.clear();bucket.missing=True
        page.reload()
        expect(page.locator('[data-execution-report]')).to_contain_text('No hay evidencia histórica suficiente')
        expect(page.locator('[data-execution-report]')).to_contain_text('N/D / N/D / N/D')
        page.screenshot(path=str(out/f'historico-sin-evidencia-{viewport[0]}.png'),full_page=True)
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
    finally:context.close()


def test_ui_accounts_for_partial_failed_pending_and_unknown(execution,chromium,tmp_path):
    from urllib.parse import urlsplit
    from playwright.sync_api import expect
    svc=execution[0]
    doc,_,_,_=historical(tmp_path/'incomplete')
    outcomes=[job(),job(amount=2),job(status='partial'),job(status='failed'),job(status='blocked'),
              dict(job(),previous_price_json=None),job(status='pending')]
    row=doc['runs'][0]['searches'][0]
    row.update(summarize(outcomes),status='partial',error_count=3)
    doc['runs'][0]['status']='partial'
    svc.overview=lambda refresh=False:(doc,None)
    client=TestClient(app)
    data=client.get('/v0.6/ejecuciones/estado').json()['run']['searches'][0]
    assert data['processed']==6 and data['pending']==1
    assert sum(data[k] for k in FINAL_KEYS)==6
    ctx=chromium.new_context(viewport={'width':390,'height':844})
    page=ctx.new_page()
    def route(route):
        u=urlsplit(route.request.url);r=client.get(u.path+('?' + u.query if u.query else ''))
        route.fulfill(status=r.status_code,headers={k:v for k,v in r.headers.items() if k.lower() not in ('content-length','content-encoding')},body=r.content)
    page.route('**/*',route)
    try:
        page.goto('http://127.0.0.1/v0.6/ejecuciones')
        expect(page.locator('[data-result-totals]')).to_contain_text('Parciales: 1')
        expect(page.locator('[data-result-totals]')).to_contain_text('Sin clasificación final: 1')
        expect(page.locator('[data-result-totals]')).to_contain_text('Pendientes conocidos: 1 (fuera de procesados)')
        expect(page.locator('[data-execution-report]')).to_contain_text('evidencia suficiente para clasificar')
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
        page.screenshot(path=str(Path.cwd()/'.tmp/resultados-finales-20261116/parcial-pendiente-390.png'),full_page=True)
    finally:ctx.close()


def test_historical_metro_uses_existing_search_identity(tmp_path):
    store,run,key=make_69(tmp_path/'identity')
    with store.connect() as db:
        report=from_db(db,run,key+'?search=form&utm_source=synthetic',source='metrocuadrado')
    assert report['processed']==69 and report['unchanged']==68


def test_incomplete_historical_reference_does_not_attempt_storage(tmp_path):
    doc,reader,bucket,_=historical(tmp_path)
    doc['runs'][0]['searches'][0]['technical_run']=[]
    row=project(doc,reader)['runs'][0]['searches'][0]
    assert row['unchanged'] is None and bucket.calls==[]
