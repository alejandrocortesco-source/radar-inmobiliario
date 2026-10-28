import json
import os
from pathlib import Path
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from . import __version__
from .storage import Store
from .paths import DEFAULT_DB
from .prices import search_identity
from catalogo.api import crear_router, consultar_catalogo, consultar_ficha
from catalogo.persistencia.sqlite import CatalogoSQLite
from catalogo.servicio import ServicioCatalogo
from consola.rutas import crear_router as crear_router_consola, ESTATICOS
from consola.v04 import crear_router as crear_router_v04, ESTATICOS as ESTATICOS_V04

app = FastAPI(title='Metrocuadrado · Revisión local',version=__version__)
templates = Jinja2Templates(directory=str(Path(__file__).parent/'templates'))
templates.env.filters['from_json'] = json.loads

def store():
    return Store(os.getenv('METRO_DB',str(DEFAULT_DB)))

def servicio():
    repositorio = CatalogoSQLite(os.getenv('METRO_DB', str(DEFAULT_DB)))
    return ServicioCatalogo(
        repositorio, revision=repositorio, normalizar_busqueda=search_identity)


app.include_router(crear_router(servicio))
app.include_router(crear_router_consola(servicio))
app.include_router(crear_router_v04(servicio))
app.mount('/v0.4/static', StaticFiles(directory=str(ESTATICOS_V04)), name='v04-static')
app.mount('/consola/static', StaticFiles(directory=str(ESTATICOS)), name='consola-static')


def rows(run_id=None,q='',status='',property_type='',limit=30,offset=0):
    filters, args = ['1=1'], []
    if run_id is not None:
        filters.append('j.run_id=?'); args.append(run_id)
    else:
        filters.append('j.run_id=(SELECT max(id) FROM runs)')
    if q:
        filters.append("(json_extract(j.data_json,'$.normalized.title') LIKE ? OR p.id LIKE ? OR json_extract(j.data_json,'$.normalized.city') LIKE ?)"); args.extend(['%'+q+'%']*3)
    if status:
        filters.append('j.status=?'); args.append(status)
    if property_type:
        filters.append("json_extract(j.data_json,'$.normalized.property_type')=?"); args.append(property_type)
    sql = ' FROM jobs j JOIN properties p ON p.id=j.property_id WHERE '+' AND '.join(filters)
    with store().connect() as db:
        total=db.execute('SELECT count(*)'+sql,args).fetchone()[0]
        result=[dict(r) for r in db.execute("SELECT p.id,p.url,json_extract(j.data_json,'$.normalized.title') title,json_extract(j.data_json,'$.normalized.price') price,json_extract(j.data_json,'$.normalized.city') city,json_extract(j.data_json,'$.normalized.property_type') property_type,json_extract(j.data_json,'$.normalized.map_url') map_url,json_extract(j.data_json,'$.normalized.portal_map_url') portal_map_url,j.status,j.attempts,j.error,j.updated,j.run_id,j.classification,j.decision_reason"+sql+' ORDER BY p.id LIMIT ? OFFSET ?',(*args,limit,offset))]
    return {'total':total,'items':result,'limit':limit,'offset':offset}

@app.get('/health')
def health():
    return {'status':'ok'}

@app.get('/api/runs')
def runs():
    dbstore=store()
    with dbstore.connect() as db:
        ids=[r[0] for r in db.execute('SELECT id FROM runs ORDER BY id DESC')]
    return [dbstore.summary(i) for i in ids]

@app.get('/api/properties')
def properties(run_id:int|None=None,q:str='',status:str='',property_type:str='',limit:int=Query(30,ge=1,le=200),offset:int=Query(0,ge=0)):
    return rows(run_id,q,status,property_type,limit,offset)

def property_data(property_id,run_id=None):
    return consultar_ficha(servicio(), property_id, run_id)


@app.get('/catalog',response_class=HTMLResponse)
def catalog_page(request:Request,state:str|None=None,search_url:str|None=None,page:int=Query(1,ge=1)):
    return templates.TemplateResponse(request=request,name='catalog.html',context={
        'result':consultar_catalogo(servicio(),state=state,search_url=search_url,limit=50,offset=(page-1)*50),
        'state':state,'search_url':search_url,'page':page})

@app.get('/api/runs/{run_id}/report')
def report(run_id:int):
    dbstore=store()
    try: summary=dbstore.summary(run_id)
    except ValueError: raise HTTPException(404,'Ejecución no encontrada')
    with dbstore.connect() as db:
        events=[dict(r) for r in db.execute('SELECT * FROM events WHERE run_id=? ORDER BY id',(run_id,))]
    pages=dbstore.pages(run_id)
    for page in pages: page['links']=json.loads(page.pop('links_json'))
    return {'summary':summary,'pages':pages,'events':events}

@app.get('/api/runs/{run_id}/export')
def export(run_id:int):
    result=report(run_id)
    with store().connect() as db:
        ids=[r[0] for r in db.execute('SELECT property_id FROM jobs WHERE run_id=? ORDER BY property_id',(run_id,))]
    result['properties']=[property_data(i,run_id) for i in ids]
    return JSONResponse(result,headers={'Content-Disposition':f'attachment; filename="metro-run-{run_id}.json"'})

@app.get('/',response_class=HTMLResponse)
def index(request:Request,run_id:int|None=None,q:str='',status:str='',property_type:str='',page:int=Query(1,ge=1)):
    all_runs=runs()
    selected=run_id if run_id is not None else (all_runs[0]['id'] if all_runs else None)
    summary=next((r for r in all_runs if r['id']==selected),None)
    result=rows(selected,q,status,property_type,30,(page-1)*30)
    with store().connect() as db:
        types=[r[0] for r in db.execute('SELECT DISTINCT property_type FROM properties WHERE property_type IS NOT NULL ORDER BY property_type')]
    return templates.TemplateResponse(request=request,name='index.html',context={'runs':all_runs,'selected':selected,'summary':summary,'result':result,'q':q,'status':status,'property_type':property_type,'types':types,'page':page})

@app.get('/properties/{property_id}',response_class=HTMLResponse)
def detail(request:Request,property_id:str,run_id:int|None=None):
    return templates.TemplateResponse(request=request,name='detail.html',context={'prop':property_data(property_id,run_id)})
