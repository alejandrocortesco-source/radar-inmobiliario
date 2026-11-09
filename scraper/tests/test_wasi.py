"""Portal simulado en Chromium y SQLite sintético. Nunca contacta Wasi."""
import asyncio
import copy
import importlib.util
import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from playwright.async_api import async_playwright

from catalogo.fuentes.wasi import configurar, identidad, opciones_iniciales
from catalogo.persistencia.busquedas import BusquedasSQLite
from metro.extraction import ExtractionError
from wasi.scraper import WasiStore, WasiScraper, WasiConfig
from wasi.extraction import listado, normalizar, whatsapp_limpio, publicacion_whatsapp
from wasi.auth import autenticar, AuthBlocked, secreto, resolver_sesion_en_uso
from wasi.browser import lote, aplicar
from wasi.durable import empaquetar, restaurar, EstadoGCS

FILTROS = {'id_pais':'1','id_dpto':'15','id_ciudad':'794','id_localidad':'1','business_type_id':'1','title':'Casa sintética'}


@pytest.fixture(autouse=True)
def sin_archivos_de_secretos_reales(monkeypatch):
    monkeypatch.delenv('WASI_USER_FILE', raising=False)
    monkeypatch.delenv('WASI_PASSWORD_FILE', raising=False)
    monkeypatch.delenv('WASI_USE_HERE', raising=False)


def config():
    return configurar(FILTROS, opciones_iniciales())


def item(codigo='001', price='100.000.000'):
    return listado({'id':codigo, 'codigo':codigo, 'info':'Casa\nVender - Casa\nColombia/Cundinamarca/Bogotá D.C.\n$'+str(price),
                    'title':'Casa sintética', 'company':'Empresa sintética','company_id':'company', 'public_url':'https://example.invalid/casa/'+codigo})


def documento(codigo='001', price='100.000.000'):
    return normalizar(codigo, {'title':'Casa sintética','labels':{'Código':codigo,'Tipo de inmueble':'Casa','Tipo de negocio':'Vender',
        'Ubicación':'Bogotá D.C., Cundinamarca, Colombia','Localidad':'Usaquén','Zona / barrio':'Cedritos','Alcobas':'3'},
        'description':'Descripción sintética','prices':{'Venta':'$'+str(price)}}, item(codigo, price))


def descubrir(store, mapeo, complete=True):
    claves=list(mapeo)
    run=store.new_run(claves[0], {'urls':claves, 'listing_currency':'COP','searches':{k:config() for k in claves}})
    for clave, links in mapeo.items():
        store.save_page(run,1,'1','https://wasi.co/usuario/inmuebles/red','page',links,None, search_url=clave)
        store.update_search(run,clave,complete=complete)
    store.plan_incremental(run)
    return run


def test_configuracion_dependiente_estable_y_revision_auxiliar(tmp_path):
    repo=BusquedasSQLite(tmp_path/'crm.sqlite')
    c=config(); key=repo.guardar_wasi('Usaquén', c)
    assert key==identidad(c)==identidad(configurar(dict(reversed(list(FILTROS.items()))),opciones_iniciales()))
    assert repo.configuracion_wasi(key)==c
    c2=configurar(FILTROS|{'id_zona':'137161'},opciones_iniciales())
    nuevo=repo.guardar_wasi('Cedritos',c2,key)
    assert nuevo!=key and len(repo.listar())==1
    assert repo.configuracion_wasi(key)==c
    assert not (tmp_path/'wasi.sqlite').exists()
    for cambio in ({'id_ciudad':''},{'id_localidad':''},{'id_ciudad':'999'}, {'id_localidad':'2','id_zona':'137161'}, {'price_from':'20','price_to':'10'}, {'price_to':'NaN'}):
        with pytest.raises(ValueError):
            configurar(FILTROS|cambio,opciones_iniciales())


def test_titulo_conservado_y_ejecucion_solo_de_busqueda_solicitada(tmp_path):
    from wasi.__main__ import configuracion
    repo=BusquedasSQLite(tmp_path/'crm.sqlite')
    a=configurar(FILTROS|{'title':' La Carolina '},opciones_iniciales())
    b=configurar(FILTROS|{'title':'Otra búsqueda'},opciones_iniciales())
    assert a['filtros']['title']=='La Carolina'
    ka=repo.guardar_wasi('Carolina',a);kb=repo.guardar_wasi('Otra',b)
    assert ka!=kb
    selected=configuracion(repo,tmp_path/'wasi.sqlite',ids=[ka])
    assert selected.urls==[ka] and set(selected.searches)=={ka}
    with pytest.raises(ValueError):configuracion(repo,tmp_path/'wasi.sqlite',ids=['inexistente'])
    with pytest.raises(ValueError):configuracion(repo,tmp_path/'wasi.sqlite',ids=[ka],resume=1)


def test_archivos_secretos_con_etiqueta_bom_y_entorno_literal(tmp_path,monkeypatch):
    usuario=tmp_path/'user.txt';password=tmp_path/'pass.txt'
    usuario.write_text('Usuario: synthetic-user\n',encoding='utf-8-sig')
    password.write_text('Password: synthetic-password:123\n',encoding='utf-8')
    monkeypatch.setenv('WASI_USER_FILE',str(usuario));monkeypatch.setenv('WASI_PASSWORD_FILE',str(password))
    assert secreto('WASI_USER')=='synthetic-user'
    assert secreto('WASI_PASSWORD')=='synthetic-password:123'
    monkeypatch.delenv('WASI_PASSWORD_FILE');monkeypatch.setenv('WASI_PASSWORD','Password: literal')
    assert secreto('WASI_PASSWORD')=='Password: literal'


def test_sesion_en_otro_dispositivo_exige_autorizacion(monkeypatch):
    async def prueba():
        async with async_playwright() as p:
            browser=await p.chromium.launch()
            try:
                page=await browser.new_page()
                await page.set_content('''<div class="modal"><h4>Tu usuario está siendo usado en otros dispositivos</h4><a onclick="this.parentElement.style.display='none'">Usar aquí</a></div>''')
                with pytest.raises(AuthBlocked,match='auth_session_in_use'):
                    await resolver_sesion_en_uso(page,1000)
                assert await page.locator('.modal').is_visible()
                monkeypatch.setenv('WASI_USE_HERE','1')
                assert await resolver_sesion_en_uso(page,1000)
                assert not await page.locator('.modal').is_visible()
            finally:
                await browser.close()
    asyncio.run(prueba())


@pytest.mark.parametrize('price', ['0','no disponible','1,234.567'])
def test_precio_invalido_no_se_sustituye_por_cero(price):
    assert item(price=price)['raw']['mvalorventa'] is None


def test_campos_desconocidos_errores_y_contactos_sin_identidad_de_cuenta():
    d=documento()
    assert d['normalized']['bathrooms'] is None and d['fields']['bathrooms']['status']=='absent'
    assert d['normalized']['address'] is None and d['normalized']['built_area'] is None
    assert d['quality']=='success'
    url='https://wa.me/573001234567?text=identidad-privada-de-cuenta'
    assert whatsapp_limpio(url)=='https://wa.me/573001234567'
    assert whatsapp_limpio('javascript:alert(1)') is None
    url += '%20https%3A%2F%2Fexample.invalid%2Fcasa%2F001'
    assert publicacion_whatsapp(url, '001')=='https://example.invalid/casa/001'
    assert publicacion_whatsapp(url, '002') is None
    datos={'title':'Casa','labels':{'Código':'001','Tipo de negocio':'Vender','Baños':'no interpretable'},'prices':{'Venta':'$100.000.000'}}
    malo=normalizar('001',datos,item())
    assert malo['quality']=='partial' and malo['fields']['bathrooms']['status']=='error'
    with pytest.raises(ExtractionError):
        normalizar('002',datos,item('002'))


def test_incremental_reutilizacion_conflictos_historial_y_fallo_conserva(tmp_path):
    store=WasiStore(tmp_path/'wasi.sqlite'); a,b='wasi:a','wasi:b'
    r=descubrir(store,{a:[item()],b:[item()]})
    assert store.summary(r)['unique']==1 and store.summary(r)['duplicates']==1
    assert store.summary(r)['classifications']=={'new':1}
    store.result(r,'001','success',documento())
    r2=descubrir(store,{a:[item()],b:[item()]})
    assert store.summary(r2)['classifications']=={'unchanged':1} and not store.pending(r2,3)
    r3=descubrir(store,{a:[item(price='110.000.000')]})
    assert store.summary(r3)['classifications']=={'modified':1}
    store.result(r3,'001','failed',error='synthetic failure')
    with store.connect() as db:
        assert json.loads(db.execute('SELECT data_json FROM properties').fetchone()[0])==documento()
        assert db.execute('SELECT count(*) FROM price_changes').fetchone()[0]==1
    r4=descubrir(store,{a:[item()],b:[item(price='110.000.000')]})
    assert store.summary(r4)['classifications']=={'review':1}


def test_ausencias_aisladas_por_busqueda_y_ejecucion_completa(tmp_path):
    s=WasiStore(tmp_path/'wasi.sqlite'); a,b='wasi:a','wasi:b'
    r=descubrir(s,{a:[item()],b:[item()]});s.result(r,'001','success',documento())
    for complete, status in ((False,'incomplete'),(True,'blocked'),(True,'completed'),(True,'completed')):
        r=descubrir(s,{a:[]},complete=complete);s.update_run(r,status=status)
        assert s.finalize_absences(r)==(status=='completed')
    with s.connect() as db:
        assert dict(db.execute('SELECT search_url,state FROM search_memberships'))=={a:'removed',b:'active'}


def html(records, repeat=False):
    texto=Path(__file__).with_name('fixtures').joinpath('wasi_network.html').read_text(encoding='utf-8')
    return texto.replace('__OPTIONS__',json.dumps(opciones_iniciales())).replace('__RECORDS__',json.dumps(records)).replace('__REPEAT__',json.dumps(repeat))


def test_contadores_tardios_y_tabla_inconsistente_no_confirman_vacio():
    async def prueba():
        async with async_playwright() as p:
            browser=await p.chromium.launch()
            try:
                page=await browser.new_page()
                await page.route('**/*',lambda route:route.abort())
                await page.set_content(html([{'id':'001','price':'100.000.000'}]))
                await page.evaluate("""()=>{document.querySelector('#properties_table_info').textContent='';setTimeout(()=>document.querySelector('#properties_table_info').textContent='1 a 1 de 1 inmuebles (filtrados de 100 inmuebles)',200)}""")
                actual=await lote(page,2000,active=1)
                assert actual['total']==1 and actual['links'][0]['id']=='001'
                await page.locator('#properties_table_info').evaluate("e=>e.textContent='0 a 0 de 0 inmuebles'")
                with pytest.raises(ExtractionError,match='No se pudo verificar'):
                    await lote(page,300)
            finally:
                await browser.close()
    asyncio.run(prueba())


def test_pais_preseleccionado_recarga_opciones_dependientes():
    async def prueba():
        async with async_playwright() as p:
            browser=await p.chromium.launch()
            try:
                page=await browser.new_page()
                await page.route('**/*',lambda route:route.abort())
                await page.set_content(html([{'id':'001','price':'100.000.000'}]))
                await page.locator('.advanced-search #id_dpto').evaluate("e=>e.innerHTML='<option value=\"\">Todos</option>'")
                resultado=await aplicar(page,config(),2000,AsyncMock())
                assert resultado['total']==1
                assert await page.locator('.advanced-search #id_dpto').input_value()=='15'
            finally:
                await browser.close()
    asyncio.run(prueba())


def test_usar_aqui_reaplica_filtros_antes_de_buscar(monkeypatch):
    monkeypatch.setenv('WASI_USE_HERE','1')
    async def prueba():
        async with async_playwright() as p:
            browser=await p.chromium.launch()
            try:
                page=await browser.new_page()
                await page.route('**/*',lambda route:route.abort())
                await page.set_content(html([{'id':'001','price':'100.000.000'}]))
                await page.evaluate('''()=>{const m=document.createElement('div');m.className='modal';m.innerHTML='<h4>Tu usuario está siendo usado en otros dispositivos</h4><a>Usar aquí</a>';m.querySelector('a').onclick=()=>{document.querySelector('.advanced-search #title').value='';m.remove();draw()};document.body.append(m)}''')
                resultado=await aplicar(page,config(),2000,AsyncMock())
                assert resultado['total']==1
                assert await page.locator('.advanced-search #title').input_value()==FILTROS['title']
            finally:
                await browser.close()
    asyncio.run(prueba())


LOGIN='''<body><span id="alerts-inf-txt" style="display:none">Credenciales incorrectas</span><form id="login-form"><input id="user"><input id="password" type="password"></form><button id="login" onclick="document.cookie='synthetic_session=1;path=/;Secure';location.href='/desktop'">Ingresar</button></body>'''


async def simulador(context, records, repeat=False, mode='normal'):
    async def route(route):
        if ('/usuario/inmuebles/' in route.request.url or '/usuario/ajax-inmuebles/get-company' in route.request.url) and route.request.resource_type == 'fetch':
            await asyncio.sleep(.05)
            await route.fulfill(status=200, body='{}')
            return
        if mode=='captcha':
            contenido='<body>verifica que eres humano</body>'
        elif mode=='rejected':
            contenido=LOGIN.replace("document.cookie='synthetic_session=1;path=/;Secure';location.href='/desktop'", "document.getElementById('alerts-inf-txt').style.display='block'")
        elif 'synthetic_session=1' not in route.request.headers.get('cookie',''):
            contenido=LOGIN
        else:
            contenido=html(records,repeat)
        await route.fulfill(status=200,content_type='text/html',body=contenido)
    await context.route('**/*',route)


@pytest.mark.parametrize('mode', ['normal','rejected','captcha','missing'])
def test_login_automatico_sesion_y_bloqueos_sin_secretos(mode, monkeypatch):
    monkeypatch.setenv('WASI_USER','synthetic-user');monkeypatch.setenv('WASI_PASSWORD','synthetic-password')
    if mode=='missing':
        monkeypatch.delenv('WASI_PASSWORD')
    async def prueba():
        async with async_playwright() as p:
            browser=await p.chromium.launch()
            try:
                context=await browser.new_context();await simulador(context,[],mode=mode)
                if mode=='normal':
                    assert await autenticar(context,1500)=='authenticated'
                    assert await autenticar(context,1500)=='session_reused'
                    await context.clear_cookies()
                    assert await autenticar(context,1500)=='authenticated'
                else:
                    with pytest.raises(AuthBlocked) as exc:
                        await autenticar(context,1000)
                    assert 'synthetic-password' not in str(exc.value) and 'synthetic-user' not in str(exc.value)
            finally:
                await browser.close()
    asyncio.run(prueba())


@pytest.mark.parametrize('repeat', [False,True])
def test_chromium_paginacion_captura_incremental_y_recuperacion(tmp_path,monkeypatch,repeat,capsys):
    monkeypatch.setenv('WASI_USER','synthetic-user');monkeypatch.setenv('WASI_PASSWORD','synthetic-password')
    records=[{'id':'001','price':'100.000.000'},{'id':'002','price':'200.000.000'},{'id':'003','price':'300.000.000'}]
    class Synthetic(WasiScraper):
        async def create_context(self,browser):
            context=await super().create_context(browser)
            await simulador(context,records,repeat)
            return context
        async def update_matching(self):
            pass
    def cfg(**kwargs):
        return WasiConfig(db=str(tmp_path/'wasi.sqlite'),url=identidad(config()),urls=[identidad(config())],
                          searches={identidad(config()):config()},delay=.5,retries=0,timeout=1500,**kwargs)
    async def prueba():
        nonlocal repeat
        first=await Synthetic(cfg()).run()
        if repeat:
            assert first['status']=='incomplete' and not first['listing_complete']
            repeat=False
            recovered=await Synthetic(cfg(resume=first['id'])).run()
            assert recovered['status']=='completed' and recovered['unique']==3 and recovered['pages']==2
            return
        assert first['status']=='completed' and first['unique']==3 and first['pages']==2
        assert first['details_opened']==3
        second=await Synthetic(cfg()).run()
        assert second['status']=='completed' and second['details_reused']==3 and second['details_opened']==0
        # Reanudar usa los filtros capturados, incluso si se elimina la configuración auxiliar.
        resumed=await Synthetic(cfg(resume=first['id'])).run()
        assert resumed['status']=='completed' and resumed['details_opened']==3
        with WasiStore(tmp_path/'wasi.sqlite').connect() as db:
            docs=[json.loads(r[0]) for r in db.execute('SELECT data_json FROM properties ORDER BY id')]
            assert docs[0]['normalized']['phone']!=docs[1]['normalized']['phone']
            assert len(docs[0]['photos'])==3
            assert 'synthetic-password' not in str([tuple(r) for r in db.execute('SELECT * FROM events')])
    asyncio.run(prueba())
    assert 'Task exception was never retrieved' not in capsys.readouterr().err


def test_snapshot_sqlite_y_rechazo_de_rutas_no_permitidas(tmp_path):
    origen=tmp_path/'origen';origen.mkdir()
    WasiStore(origen/'wasi.sqlite')
    (origen/'secret.txt').write_text('synthetic-secret')
    paquete=empaquetar(origen)
    destino=tmp_path/'destino';restaurar(paquete,destino)
    assert (destino/'wasi.sqlite').exists() and not (destino/'secret.txt').exists()
    with pytest.raises(ValueError):
        restaurar(paquete,destino)


def test_lock_remoto_y_generacion_impiden_sobrescritura(tmp_path):
    class Blob:
        def __init__(self): self.generation=None;self.data=None
        def upload_from_string(self,data,if_generation_match,**kwargs):
            if if_generation_match != (self.generation or 0):raise ValueError('PreconditionFailed')
            self.generation=(self.generation or 0)+1;self.data=data
        def reload(self,**kwargs):
            if self.generation is None:raise ValueError('NotFound')
        def download_as_bytes(self,if_generation_match,**kwargs):
            assert if_generation_match==self.generation
            return self.data
        def delete(self,if_generation_match,**kwargs):
            assert if_generation_match==self.generation
            self.generation=None;self.data=None
    class Bucket:
        def __init__(self): self.blobs={}
        def blob(self,name):return self.blobs.setdefault(name,Blob())
    class Client:
        def __init__(self):self.b=Bucket()
        def bucket(self,name):return self.b
    client=Client();WasiStore(tmp_path/'wasi.sqlite')
    with EstadoGCS('fake',client=client) as first:
        first.guardar(tmp_path)
        with pytest.raises(ValueError):
            with EstadoGCS('fake',client=client):pass
    with EstadoGCS('fake',client=client) as second:
        destino=tmp_path/'restored';second.cargar(destino)
        assert (destino/'wasi.sqlite').exists()
        second.guardar(destino)
        with pytest.raises(ValueError):first.guardar(tmp_path)


def test_horario_configurable_sin_desplegar():
    spec=importlib.util.spec_from_file_location('radar_job',Path(__file__).parents[1]/'job.py')
    modulo=importlib.util.module_from_spec(spec);spec.loader.exec_module(modulo)
    assert modulo.horario('TUE,FRI')=={'schedule':'0 0 * * TUE,FRI','timeZone':'America/Bogota'}
    with pytest.raises(ValueError):modulo.horario('MON,MON')
