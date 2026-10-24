import asyncio
import copy
import json
import sqlite3
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from metro.prices import price, same_price, search_identity
from metro.storage import Store
from metro.scraper import Config, Scraper
from metro.web import app

A = 'https://www.metrocuadrado.com/inmuebles/venta/bogota/la-carolina?search=form'
B = 'https://www.metrocuadrado.com/inmuebles/venta/bogota/usaquen'


def listing(pid='1-M1', amount=1_000_000, currency='COP'):
    return {'id':pid,'url':f'https://www.metrocuadrado.com/inmueble/apartamento/{pid}',
            'group':'results','raw':{'midinmueble':pid,'mtiponegocio':'venta','mvalorventa':amount,'currency':currency}}


def document(pid='1-M1', amount=1_000_000, currency='COP', quality='success'):
    return {'quality':quality,'normalized':{'id':pid,'title':'Apartamento completo','price':amount,
            'operation':'venta','currency':currency,'city':'Bogotá','property_type':'Apartamento',
            'description':'Descripción completa conservada'},'photos':['https://example.com/photo.jpg'],
            'features':[],'fields':{},'sources':{},'extra':{},'visible_text':'','media':{},'errors':[]}


def discover(store, mapping, *, complete=True):
    urls = list(mapping)
    run = store.new_run(urls[0],{'urls':urls,'listing_currency':'COP'})
    for url, links in mapping.items():
        store.save_page(run,1,'1',url,'page-1',links,None,search_url=url)
        if complete:
            store.update_search(run,url,advertised={'totalHits':len(links)},complete=True)
    store.plan_incremental(run)
    return run


def finish(store, run, status='completed'):
    store.update_run(run,status=status)
    return store.finalize_absences(run)


def seed(store, mapping=None):
    mapping = mapping or {A:[listing()]}
    run = discover(store,mapping)
    for job in store.pending(run,3):
        amount = json.loads(job['listing_price_json'])['amount']
        store.result(run,job['property_id'],'success',document(job['property_id'],float(amount)))
    assert finish(store,run)
    return run


def member(store, url=A, pid='1-M1'):
    with store.connect() as db:
        return dict(db.execute('SELECT * FROM search_memberships WHERE search_url=? AND property_id=?',
                               (search_identity(url),pid)).fetchone())


def test_new_unchanged_modified_and_full_data_preservation(tmp_path):
    store = Store(tmp_path/'db.sqlite')
    first = seed(store)
    with store.connect() as db:
        before = dict(db.execute('SELECT * FROM properties').fetchone())
    run = discover(store,{A:[listing(amount='$ 1.000.000 COP')]})
    assert not store.pending(run,3)
    assert store.summary(run)['classifications']=={'unchanged':1}
    with store.connect() as db:
        after = dict(db.execute('SELECT * FROM properties').fetchone())
        job = dict(db.execute('SELECT * FROM jobs WHERE run_id=?',(run,)).fetchone())
    assert after == before
    assert job['attempts']==0 and job['data_json']==before['data_json']
    assert member(store)['last_seen_run']==run
    assert finish(store,run)
    changed = discover(store,{A:[listing(amount=1_200_000),listing('2-M2',500_000)]})
    assert store.summary(changed)['classifications']=={'modified':1,'new':1}
    assert len(store.pending(changed,3))==2
    data = document(amount=1_200_000)
    data['normalized']['title']='Título actualizado'
    store.validate_detail_price(changed,'1-M1',data)
    store.result(changed,'1-M1','success',data)
    with store.connect() as db:
        change = dict(db.execute('SELECT * FROM price_changes WHERE run_id=?',(changed,)).fetchone())
        assert json.loads(db.execute('SELECT data_json FROM properties WHERE id=?',('1-M1',)).fetchone()[0])==data
    assert json.loads(change['previous_price_json'])['amount']=='1000000'
    assert json.loads(change['new_price_json'])['amount']=='1200000'
    assert change['detected_at'] and change['verification']=='confirmed'


@pytest.mark.parametrize('amount,currency',[(None,'COP'),(0,'COP'),('Desde 1000000','COP'),(1_000_000,'USD'),('1,234.567','COP')])
def test_uncertain_price_opens_detail(tmp_path,amount,currency):
    store=Store(tmp_path/'db.sqlite')
    seed(store)
    run=discover(store,{A:[listing(amount=amount,currency=currency)]})
    assert len(store.pending(run,3))==1
    assert store.summary(run)['classifications']=={'review':1}


def test_two_successful_absences_reappearance_and_idempotence(tmp_path):
    store=Store(tmp_path/'db.sqlite')
    seed(store,{A:[listing(),listing('2-M2')]})
    one=discover(store,{A:[listing()]})
    assert finish(store,one)
    assert member(store,pid='2-M2')['state']=='possibly_removed'
    assert member(store,pid='2-M2')['missing_streak']==1
    interrupted=discover(store,{A:[listing()]},complete=False)
    assert not finish(store,interrupted,'incomplete')
    assert member(store,pid='2-M2')['missing_streak']==1
    two=discover(store,{A:[listing()]})
    assert finish(store,two)
    assert member(store,pid='2-M2')['state']=='removed'
    finish(store,two)
    assert member(store,pid='2-M2')['missing_streak']==2
    back=discover(store,{A:[listing(),listing('2-M2')]})
    assert not store.pending(back,3)
    assert member(store,pid='2-M2')['state']=='active'
    assert member(store,pid='2-M2')['missing_streak']==0


@pytest.mark.parametrize('status',['failed','blocked','incomplete','interrupted','running'])
def test_unsuccessful_runs_never_count_missing(tmp_path,status):
    store=Store(tmp_path/'db.sqlite')
    seed(store,{A:[listing(),listing('2-M2')]})
    run=discover(store,{A:[listing()]})
    assert not finish(store,run,status)
    assert member(store,pid='2-M2')['state']=='active'
    assert member(store,pid='2-M2')['missing_streak']==0


def test_partial_and_mismatched_detail_keeps_good_catalog_and_retries(tmp_path):
    store=Store(tmp_path/'db.sqlite')
    seed(store,{A:[listing(),listing('2-M2')]})
    run=discover(store,{A:[listing(amount=1_200_000)]})
    data=store.validate_detail_price(run,'1-M1',document(amount=1_100_000))
    assert data['quality']=='partial'
    store.result(run,'1-M1','partial',data)
    assert not finish(store,run)
    assert member(store,pid='2-M2')['missing_streak']==0
    with store.connect() as db:
        saved=json.loads(db.execute('SELECT data_json FROM properties WHERE id=?',('1-M1',)).fetchone()[0])
        assert saved['normalized']['price']==1_000_000
        assert db.execute('SELECT verification FROM price_changes').fetchone()[0]=='disagreement_or_uncomparable'
    again=discover(store,{A:[listing()]})
    assert store.summary(again)['classifications']=={'review':1}
    assert len(store.pending(again,3))==1


def test_memberships_are_per_search_and_details_are_global(tmp_path):
    store=Store(tmp_path/'db.sqlite')
    seed(store,{A:[listing()],B:[listing()]})
    run=discover(store,{A:[],B:[listing()]})
    assert store.summary(run)['unique']==1
    assert not store.pending(run,3)
    assert finish(store,run)
    assert member(store,A)['state']=='possibly_removed'
    assert member(store,B)['state']=='active'
    run=discover(store,{A:[],B:[listing()]})
    assert finish(store,run)
    assert store.catalog()['items'][0]['state']=='active'
    assert store.catalog(state='removed',search_url=A)['total']==1
    assert store.catalog(state='removed')['total']==0


def test_one_incomplete_search_blocks_all_absence_confirmations(tmp_path):
    store=Store(tmp_path/'db.sqlite')
    seed(store,{A:[listing()],B:[listing('2-M2')]})
    run=discover(store,{A:[],B:[]},complete=False)
    store.update_search(run,A,complete=True)
    assert not finish(store,run,'completed')
    assert member(store,A)['state']=='active'


def test_conflicting_duplicate_prices_force_review(tmp_path):
    store=Store(tmp_path/'db.sqlite')
    seed(store)
    run=discover(store,{A:[listing()]})
    store.save_page(run,2,'2',A,'page-2',[listing(amount=1_200_000)],None)
    store.plan_incremental(run)
    assert store.summary(run)['classifications']=={'review':1}
    assert len(store.pending(run,3))==1
    store.result(run,'1-M1','success',document())
    assert not finish(store,run)


def test_same_normalized_duplicates_do_not_force_review(tmp_path):
    store=Store(tmp_path/'db.sqlite')
    seed(store)
    run=discover(store,{A:[listing()]})
    store.save_page(run,2,'2',A,'page-2',[listing(amount='$ 1.000.000,00 COP')],None)
    store.plan_incremental(run)
    assert store.summary(run)['classifications']=={'unchanged':1}


def test_worker_only_opens_required_details(tmp_path):
    scraper=Scraper(Config(db=str(tmp_path/'db.sqlite')))
    seed(scraper.store)
    scraper.run_id=discover(scraper.store,{A:[listing(),listing('2-M2')]})
    scraper.detail=AsyncMock()
    asyncio.run(scraper.process_details(object()))
    assert scraper.detail.await_count==1
    assert scraper.detail.call_args.args[1]['property_id']=='2-M2'


def test_catalog_history_and_unchanged_api(tmp_path,monkeypatch):
    database=tmp_path/'db.sqlite'
    monkeypatch.setenv('METRO_DB',str(database))
    store=Store(database)
    seed(store)
    run=discover(store,{A:[listing()]})
    assert finish(store,run)
    client=TestClient(app)
    assert client.get('/').status_code==200
    assert client.get('/catalog').status_code==200
    assert client.get('/api/catalog').json()['items'][0]['state']=='active'
    response=client.get('/api/properties?status=unchanged').json()
    assert response['items'][0]['classification']=='unchanged'
    data=client.get('/api/properties/1-M1').json()
    assert data['memberships'][0]['last_seen_run']==run
    assert data['data']['photos']
    assert client.get(f'/api/runs/{run}/export').status_code==200


def test_legacy_migration_preserves_documents_and_makes_backup(tmp_path):
    path=tmp_path/'legacy.sqlite'
    data=json.dumps(document())
    item=listing()
    with sqlite3.connect(path) as db:
        db.executescript('''
          CREATE TABLE runs(id INTEGER PRIMARY KEY,url TEXT,started TEXT,finished TEXT,status TEXT,advertised_json TEXT,listing_complete INTEGER,config_json TEXT);
          CREATE TABLE pages(run_id INTEGER,number INTEGER,active TEXT,url TEXT,fingerprint TEXT,links_json TEXT,next_json TEXT,visited TEXT,PRIMARY KEY(run_id,number),UNIQUE(run_id,fingerprint));
          CREATE TABLE properties(id TEXT PRIMARY KEY,url TEXT UNIQUE,data_json TEXT,title TEXT,price REAL,city TEXT,property_type TEXT,updated TEXT);
          CREATE TABLE appearances(run_id INTEGER,page INTEGER,property_id TEXT,url TEXT,PRIMARY KEY(run_id,page,property_id));
          CREATE TABLE jobs(run_id INTEGER,property_id TEXT,status TEXT,attempts INTEGER DEFAULT 0,error TEXT,data_json TEXT,updated TEXT,PRIMARY KEY(run_id,property_id));
          CREATE TABLE events(id INTEGER PRIMARY KEY,run_id INTEGER,time TEXT,level TEXT,kind TEXT,context_json TEXT);
        ''')
        db.execute('INSERT INTO runs VALUES(1,?,?,?,?,?,?,?)',(A,'2026-10-24',None,'completed',None,1,'{}'))
        db.execute('INSERT INTO properties VALUES(?,?,?,?,?,?,?,?)',('1-M1',item['url'],data,'Apartamento',1_000_000,'Bogotá','Apartamento','2026-10-24'))
        db.execute('INSERT INTO pages VALUES(1,1,?,?,?,?,?,?)',('1',A,'fp',json.dumps([item]),'null','2026-10-24'))
        db.execute('INSERT INTO appearances VALUES(1,1,?,?)',('1-M1',item['url']))
        db.execute("INSERT INTO jobs(run_id,property_id,status,data_json) VALUES(1,'1-M1','success',?)",(data,))
    store=Store(path)
    Store(path)  # La migración se ejecuta una sola vez.
    assert store.summary(1)['unique']==1
    assert store.pages(1)[0]['search_url']==search_identity(A)
    with store.connect() as db:
        assert db.execute('SELECT data_json FROM properties').fetchone()[0]==data
        assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
    with sqlite3.connect(tmp_path/'legacy.pre-incremental.sqlite') as backup:
        assert backup.execute('SELECT data_json FROM properties').fetchone()[0]==data
        assert backup.execute('PRAGMA user_version').fetchone()[0]==0
    assert member(store)['state']=='active'
    assert not store.finalize_absences(1) or member(store)['missing_streak']==0


def test_multiple_url_orchestration_and_single_detail_queue(tmp_path,monkeypatch):
    scraper=Scraper(Config(db=str(tmp_path/'multi.sqlite'),urls=[A,B]))
    context=SimpleNamespace(route=AsyncMock())
    browser=SimpleNamespace(new_context=AsyncMock(return_value=context),close=AsyncMock())
    playwright=SimpleNamespace(chromium=SimpleNamespace(launch=AsyncMock(return_value=browser)))
    class Session:
        async def __aenter__(self): return playwright
        async def __aexit__(self,*args): pass
    monkeypatch.setattr('metro.scraper.async_playwright',lambda:Session())
    visited=[]
    async def discover_source(context,source):
        visited.append(source)
        links=[listing()]
        scraper.store.save_page(scraper.run_id,1,'1',source,'same-ids',links,None,search_url=source)
        scraper.store.update_search(scraper.run_id,source,complete=True)
    async def fetch(context,job):
        scraper.store.result(scraper.run_id,job['property_id'],'success',document())
    scraper.discover=discover_source
    scraper.detail=AsyncMock(side_effect=fetch)
    result=asyncio.run(scraper._run())
    assert set(visited)=={A,B}
    assert scraper.detail.await_count==1
    assert result['pages']==2 and result['unique']==1
    assert result['status']=='completed'


def test_failed_refresh_is_not_skipped_on_next_run(tmp_path):
    store=Store(tmp_path/'db.sqlite')
    seed(store)
    run=discover(store,{A:[listing(amount=1_200_000)]})
    store.attempt(run,'1-M1')
    store.result(run,'1-M1','failed',error='timeout')
    assert not finish(store,run,'incomplete')
    next_run=discover(store,{A:[listing()]})
    assert store.summary(next_run)['classifications']=={'review':1}
    assert store.pending(next_run,3)


def test_uncomparable_listing_currency_without_confirmation(tmp_path):
    store=Store(tmp_path/'db.sqlite')
    seed(store)
    run=store.new_run(A,{'listing_currency':None})
    store.save_page(run,1,'1',A,'fp',[listing(currency=None)],None)
    store.plan_incremental(run)
    assert store.summary(run)['classifications']=={'review':1}
    assert store.pending(run,3)


def test_empty_successful_search_counts_absence_twice(tmp_path):
    store=Store(tmp_path/'db.sqlite')
    seed(store)
    first=discover(store,{A:[]})
    assert finish(store,first)
    assert member(store)['state']=='possibly_removed'
    second=discover(store,{A:[]})
    assert finish(store,second)
    assert member(store)['state']=='removed'
    back=discover(store,{A:[listing()]},complete=False)
    assert not finish(store,back,'blocked')
    assert member(store)['state']=='active'
    assert member(store)['missing_streak']==0


def test_detail_can_confirm_change_when_listing_price_is_missing(tmp_path):
    store=Store(tmp_path/'db.sqlite')
    seed(store)
    run=discover(store,{A:[listing(amount=None)]})
    data=store.validate_detail_price(run,'1-M1',document(amount=1_200_000))
    store.result(run,'1-M1','success',data)
    with store.connect() as db:
        row=db.execute('SELECT source,verification FROM price_changes').fetchone()
    assert tuple(row)==('detail','confirmed')


def test_partial_refresh_can_resume_without_losing_previous_price(tmp_path):
    store=Store(tmp_path/'db.sqlite')
    seed(store)
    run=discover(store,{A:[listing(amount=1_200_000)]})
    store.attempt(run,'1-M1')
    store.result(run,'1-M1','partial',document(amount=1_200_000,quality='partial'))
    store.plan_incremental(run)
    job=store.pending(run,3)[0]
    assert job['attempts']==1
    assert job['classification']=='modified'
    assert json.loads(job['previous_price_json'])['amount']=='1000000'
    store.attempt(run,'1-M1')
    store.result(run,'1-M1','success',document(amount=1_200_000))
    assert not store.pending(run,3)
    assert finish(store,run)
