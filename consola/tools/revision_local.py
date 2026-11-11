"""Instancia de revisión aislada, sin red externa ni credenciales operativas.

No se importa desde la aplicación. Ejecutar desde la raíz con --datos .tmp/...
Reutiliza las bases si existe manifest.json; nunca regenera datos al reiniciar.
"""
import argparse
import copy
import ipaddress
import json
import os
import re
from pathlib import Path
import sys
import threading

RAIZ = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(RAIZ), str(RAIZ / 'scraper')]


def configurar(ruta):
    ruta = Path(ruta).resolve()
    if not ruta.is_relative_to(RAIZ / '.tmp') or ruta == RAIZ / '.tmp':
        raise ValueError('Los datos de revisión deben estar en una subcarpeta de .tmp/')
    if any(k in os.environ for k in ('K_SERVICE', 'K_REVISION', 'K_CONFIGURATION')):
        raise ValueError('Esta herramienta es exclusivamente local; no admite Cloud Run')
    for k in tuple(os.environ):
        if k.startswith(('GEMINI_', 'WASI_', 'GOOGLE_', 'RADAR_IAP_')):
            os.environ.pop(k)
    for k, f in [('METRO_DB', 'metro.sqlite'), ('WASI_DB', 'wasi.sqlite'),
                 ('FINCARAIZ_DB', 'fincaraiz.sqlite'), ('RADAR_CRM_DB', 'crm.sqlite')]:
        os.environ[k] = str(ruta / f)
    os.environ.update(RADAR_AUTH_MODE='local', GEMINI_API_KEY='solo-simulacion-sin-valor',
                      GEMINI_MODEL='gemini-3.8-flash', GEMINI_MAX_CANDIDATES='20')
    os.environ.pop('RADAR_PUBLIC_ORIGIN', None)
    ruta.mkdir(parents=True, exist_ok=True)
    return ruta


def sembrar(ruta, extras=24, clientes=4):
    from metro.storage import Store
    from wasi.scraper import WasiStore
    from fincaraiz.scraper import FincaraizStore
    from catalogo.fuentes import fincaraiz, wasi
    from catalogo.persistencia.busquedas import BusquedasSQLite
    from oportunidades.modelos import ClienteDatos, Necesidades
    from oportunidades.servicio import servicio_oportunidades
    from oportunidades.automatizacion import recalcular
    from metro.web import servicio

    manifest = ruta / 'manifest.json'
    if manifest.exists():
        return json.loads(manifest.read_text(encoding='utf-8'))
    if any(ruta.glob('*.sqlite*')):
        raise ValueError('Hay bases sin manifest: usa una carpeta nueva; no se sobrescriben')
    fr = copy.deepcopy(fincaraiz.opciones_iniciales()[0])
    wc = wasi.configurar({'id_pais':'1', 'id_dpto':'15', 'id_ciudad':'794',
                         'id_localidad':'1', 'business_type_id':'1'}, wasi.opciones_iniciales())
    mc = 'https://www.metrocuadrado.com/inmuebles/venta/bogota/la-carolina'
    stores = {'metrocuadrado': Store(ruta / 'metro.sqlite'),
              'wasi': WasiStore(ruta / 'wasi.sqlite'),
              'fincaraiz': FincaraizStore(ruta / 'fincaraiz.sqlite')}
    urls = {'metrocuadrado': mc, 'wasi': wasi.identidad(wc), 'fincaraiz': fr['url_efectiva']}
    datos = [
        ('metrocuadrado', '001', 'A - límite superior', 450000000, {}),
        ('wasi', '001', 'B - preferencia incumplida', 400000000, {'rooms':2, 'bathrooms':1, 'built_area':65}),
        ('fincaraiz', '001', 'C - habitaciones pendientes', 430000000, {'rooms':None}),
        ('metrocuadrado', '004', 'D - excede presupuesto', 450000001, {}),
        ('metrocuadrado', '005', 'E - una habitación', 400000000, {'rooms':1}),
        ('metrocuadrado', '006', 'F - otro barrio', 400000000, {'neighborhood':'La Calleja'}),
        ('metrocuadrado', '007', 'G - otra ciudad', 400000000, {'city':'Medellín'}),
        ('metrocuadrado', '008', 'H - casa', 400000000, {'property_type':'Casa'}),
        ('metrocuadrado', '009', 'I - arriendo', 3000000, {'operation':'arriendo'}),
        ('metrocuadrado', '010', 'J - límite inferior', 350000000, {}),
        ('metrocuadrado', '011', 'K - inferior al mínimo', 349999999, {}),
        ('metrocuadrado', '012', 'L - precio pendiente', None, {}),
    ]
    fuentes = tuple(stores)
    datos += [(fuentes[n % 3], str(1000+n), f'Reserva {n+1:04}', 300000000+n*100000,
               {'city':'Medellín', 'neighborhood':'El Poblado'}) for n in range(extras)]
    for fuente, store in stores.items():
        url = urls[fuente]
        run = store.new_run(url, {'urls':[url], 'listing_currency':'COP'})
        filas = [d for d in datos if d[0] == fuente]
        enlaces = [{'id':cod, 'url':f'https://publicacion.example.test/{fuente}/{cod}',
                    'raw':{'mtiponegocio':c.get('operation', 'venta'), 'mvalorventa':precio}}
                   for _, cod, _, precio, c in filas]
        store.save_page(run, 1, '1', url, 'fixture revisión', enlaces, None, search_url=url)
        store.plan_incremental(run)
        for (_, cod, titulo, precio, cambios), link in zip(filas, enlaces):
            normalized = dict(title='Demo '+titulo, description='Publicación enteramente sintética.',
                price=precio, currency='COP', operation='venta', property_type='Apartamento',
                city='Bogotá', neighborhood='La Carolina', zone='Norte', built_area=90,
                built_area_unit='m²', private_area=82, private_area_unit='m²', rooms=3,
                bathrooms=2, garages=1, advertiser='Agencia Demo',
                advertiser_url='https://anunciante.example.test/agencia-demo',
                phone=None, whatsapp=None, url=link['url'])
            normalized.update(cambios)
            doc = {'normalized':normalized, 'quality':'success', 'photos':[], 'features':[],
                   'fields':{}, 'sources':{}, 'extra':{}, 'media':{}, 'visible_text':'', 'errors':[]}
            store.result(run, cod, 'success', doc)
        store.update_search(run, url, complete=True)
        store.update_run(run, status='completed', finished='2026-11-11T15:00:00+00:00')
    s = servicio_oportunidades()
    repo = BusquedasSQLite(s.repositorio.ruta)
    repo.guardar('metrocuadrado', mc, mc, 'Demo Metrocuadrado')
    repo.guardar_wasi('Demo Wasi', wc)
    repo.guardar_fincaraiz('Demo Fincaraíz', fr)
    necesidades = dict(operacion='compra', tipo='apartamento', ciudad='Bogotá', barrios=['La Carolina'],
        presupuesto_min='350000000', presupuesto_max='450000000', habitaciones_min=2,
        habitaciones_max=3, banos_min=2, area_min_m2=80, tipo_area='construida')
    registros = []
    for n in range(clientes):
        nombre = ['Demo Matching', 'Demo Gemini correcto', 'Demo Gemini error', 'Demo Sin resultados'][n] if n < 4 else f'Demo cliente {n+1:02}'
        nd = dict(necesidades)
        if n == 2:
            nd['banos_min'] = 9  # Disparador documentado del transporte falso; no cambia reglas.
        if n == 3:
            nd['barrios'] = ['La Calleja']
            nd['tipo'] = 'casa'
        o = s.capturar(ClienteDatos(nombre=nombre), Necesidades.model_validate(nd))
        recalcular(s, servicio(), o.id)
        registros.append({'nombre':nombre, 'cliente':o.cliente_id, 'oportunidad':o.id})
    contenido = {'entorno':'SINTÉTICO SIN RED EXTERNA', 'publicaciones':len(datos),
                 'clientes':registros, 'fuentes':urls}
    manifest.write_text(json.dumps(contenido, ensure_ascii=False, indent=2), encoding='utf-8')
    return contenido


def transporte_simulado(ruta):
    import httpx
    lock = threading.Lock()

    def responder(request):
        if request.url.host != 'generativelanguage.googleapis.com':
            raise httpx.ConnectError('Red externa deshabilitada en revisión', request=request)
        contenido = json.loads(request.content)
        entrada = json.loads(contenido['contents'][0]['parts'][0]['text'])
        error = entrada['necesidades'].get('banos_min') == 9
        with lock, (ruta / 'simulaciones.jsonl').open('a', encoding='utf-8') as f:
            f.write(json.dumps({'integracion':'Gemini SIMULADO', 'http':429 if error else 200,
                                'candidatos':len(entrada['candidatos'])})+'\n')
        if error:
            return httpx.Response(429, json={'error':{'code':429, 'status':'RESOURCE_EXHAUSTED',
                                                     'message':'Límite simulado de revisión'}})
        evaluaciones = [{'id':c['id'], 'puntuacion':85,
            'explicacion':'SIMULADO: ciudad documentada; revisar preferencias y datos pendientes.',
            'evidencias':[{'campo':'ciudad', 'valor':c['hechos']['ciudad']}]} for c in entrada['candidatos']]
        return httpx.Response(200, json={'candidates':[{'finishReason':'STOP', 'content':{
            'parts':[{'text':json.dumps({'evaluaciones':evaluaciones})}]}}],
            'modelVersion':'simulado-local', 'usageMetadata':{}})

    return httpx.MockTransport(responder)


def preparar_app(ruta):
    import httpx
    import oportunidades.gemini as modulo
    from types import SimpleNamespace
    from metro.web import app
    from catalogo.fuentes.fincaraiz import opciones_iniciales, identidad
    import fincaraiz.browser
    import wasi.options

    # Solo el módulo proveedor usa este cliente; TestClient y el resto no se alteran.
    cliente_real = httpx.Client
    modulo.httpx = SimpleNamespace(Client=lambda **kw: cliente_real(transport=transporte_simulado(ruta), **kw),
        Timeout=httpx.Timeout, TimeoutException=httpx.TimeoutException,
        HTTPStatusError=httpx.HTTPStatusError, HTTPError=httpx.HTTPError)

    async def verificar(url, esperado=None):
        for c in opciones_iniciales():
            if identidad(c['url_efectiva']) == identidad(url):
                if esperado is not None and esperado != c['filtros']:
                    raise ValueError('Filtros diferentes del fixture')
                return copy.deepcopy(c)
        raise ValueError('URL sin fixture local; no se consulta el portal')

    async def opciones(repo, padres):
        raise ValueError('Sincronización externa deshabilitada en revisión local')

    fincaraiz.browser.verificar = verificar
    wasi.options.actualizar_opciones = opciones

    @app.middleware('http')
    async def identificacion(request, call_next):
        response = await call_next(request)
        response.headers['X-Radar-Entorno'] = 'sintetico-sin-red-externa'
        if response.headers.get('content-type', '').startswith('text/html'):
            from starlette.responses import Response
            body = b''.join([chunk async for chunk in response.body_iterator])
            aviso = ('<div role="note" data-revision-local style="padding:12px;background:#fff0ad;color:#332900;overflow-wrap:anywhere">'
                     'REVISIÓN LOCAL · Datos sintéticos · Gemini y verificación Fincaraíz simulados · '
                     'Red externa deshabilitada. Gemini: baños preferidos = 9 simula HTTP 429; otros valores, respuesta válida.'
                     '</div>').encode('utf-8')
            body = re.sub(rb'(<body\b[^>]*>)', lambda m: m[0]+aviso, body, count=1)
            headers = dict(response.headers)
            headers.pop('content-length', None)
            return Response(body, status_code=response.status_code, headers=headers,
                            background=response.background)
        return response

    return app


def bloquear_red(event, args):
    if event == 'subprocess.Popen':
        raise PermissionError('Subprocesos deshabilitados en revisión local')
    if event == 'socket.connect':
        destino = args[1]
        try:
            local = ipaddress.ip_address(destino[0]).is_loopback
        except (ValueError, TypeError, IndexError):
            local = False
        if not local:
            raise PermissionError('Red externa deshabilitada en revisión local')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--datos', required=True)
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--solo-preparar', action='store_true')
    args = parser.parse_args()
    ruta = configurar(args.datos)
    sys.addaudithook(bloquear_red)
    contenido = sembrar(ruta)
    if args.solo_preparar:
        print(json.dumps(contenido, ensure_ascii=False, indent=2))
        return
    app = preparar_app(ruta)
    import uvicorn
    uvicorn.run(app, host='127.0.0.1', port=args.port, proxy_headers=False)


if __name__ == '__main__':
    main()
