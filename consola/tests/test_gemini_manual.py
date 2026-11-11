"""Flujos manuales y novedades con SQLite sintético; nunca Google real."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from decimal import Decimal
import json
from pathlib import Path
from threading import Barrier
from uuid import uuid4

from bs4 import BeautifulSoup
import httpx
from playwright.sync_api import expect
import pytest

from catalogo.modelos import Origen, Oferta, Operacion
from metro.web import servicio
from oportunidades.automatizacion import recalcular, solicitar_gemini, plan_gemini, clave_novedad, candidato, despues_scraper
from oportunidades.gemini import Gemini
from oportunidades.modelos import ClienteDatos, OportunidadDatos
from oportunidades.matching import comparar
from oportunidades.seguimiento import SeguimientoSQLite
from oportunidades.servicio import servicio_oportunidades
from test_browser import servidor, pagina
from test_v03 import inmueble, necesidades
from test_v06 import escenario06, formulario, GeminiFalso, evaluar_manual


class CatalogoMutable:
    def __init__(self, items):
        self.items = items

    def listar(self):
        return self.items


def anuncio(codigo, **datos):
    return inmueble(origen=Origen(fuente='metrocuadrado', id_original=codigo), **datos)


def test_todas_entradas_automaticas_con_clave_cero_llamadas(escenario06, escenario_consola, monkeypatch):
    c, s, o, repo = escenario06
    monkeypatch.setenv('GEMINI_API_KEY', 'sintetica-nunca-real')
    llamadas = []
    monkeypatch.setattr(Gemini, 'evaluar', lambda *a: llamadas.append(a))
    r = c.post('/v0.6/oportunidades', data=formulario())
    assert r.status_code == 200
    assert c.post('/v0.6/oportunidades', data=formulario(cliente_id=o.cliente_id, oportunidad_id=o.id)).status_code == 200
    assert c.post('/consola/oportunidades', data=formulario()).status_code == 200
    assert c.post('/consola/oportunidades', data=formulario(cliente_id=o.cliente_id, oportunidad_id=o.id)).status_code == 200
    datos = OportunidadDatos(cliente_id=o.cliente_id, necesidades=necesidades()).model_dump(mode='json')
    assert c.post('/api/oportunidades', json=datos).status_code == 201
    assert c.put(f'/api/oportunidades/{o.id}', json=datos).status_code == 200
    for activo in ('0', '1'):
        assert c.post(f'/v0.6/clientes/{o.cliente_id}', data={'nombre':'Prueba', 'activo':activo}).status_code == 200
    assert c.post(f'/v0.6/oportunidades/{o.id}/recalcular').status_code == 200
    assert c.post(f'/api/oportunidades/{o.id}/buscar').status_code == 200
    despues_scraper(escenario_consola['ruta'])
    for url in (f'/v0.6/clientes/{o.cliente_id}?orden=ia', f'/v0.6/oportunidades/{o.id}/estado',
                f'/api/oportunidades/{o.id}/coincidencias', f'/api/oportunidades/{o.id}/gemini'):
        assert c.get(url).status_code == 200
    assert not llamadas and not repo.ultima_gemini(o.id)


def test_novedad_baseline_actualizado_antes_no_cumplia_persistencia_y_reaparicion(escenario06):
    _, s, o, repo = escenario06
    a, b = anuncio('a'), anuncio('b', ofertas=(Oferta(operacion=Operacion.VENTA, precio=Decimal('999999999')),))
    cat = CatalogoMutable([a, b])
    recalcular(s, cat, o.id)
    assert not any(n['nueva'] for n in repo.novedades(o.id).values())
    # Un anuncio nuevo y uno conocido que ahora cumple, sin cambiar necesidades.
    cat.items = [a, anuncio('b'), anuncio('c')]
    assert recalcular(s, cat, o.id, True)
    filas = s.coincidencias(o.id, cat)
    nuevas = {clave_novedad(r): repo.novedades(o.id)[clave_novedad(r)] for r in filas if repo.novedades(o.id)[clave_novedad(r)]['nueva']}
    assert len(nuevas) == 2
    repo2 = SeguimientoSQLite(s.repositorio.ruta)
    assert repo2.novedades(o.id) == repo.novedades(o.id)
    recalcular(s, cat, o.id, True)
    assert repo.novedades(o.id) == repo2.novedades(o.id)
    n = nuevas['p:' + anuncio('b').id_interno]
    repo.marcar_vistas(o.id, [(n['relacion'], n['ultima_deteccion'])])
    cat.items = [a, anuncio('c')]
    recalcular(s, cat, o.id)
    cat.items = [anuncio('b'), a, anuncio('c')]
    recalcular(s, cat, o.id)
    vuelve = repo.novedades(o.id)['p:' + anuncio('b').id_interno]
    assert vuelve['tipo'] == 'reaparicion' and vuelve['apariciones'] == 2 and vuelve['nueva']
    assert vuelve['detectada'] == n['detectada']
    with repo.conexion() as db:
        tipos = [r[0] for r in db.execute('SELECT tipo FROM radar_novedad_eventos WHERE oportunidad=? AND relacion=? ORDER BY fecha', (o.id, n['relacion']))]
    assert tipos == ['nueva', 'vista', 'desaparicion', 'reaparicion']
    # Un formulario anterior no borra una reaparición posterior.
    repo.marcar_vistas(o.id, [(n['relacion'], n['ultima_deteccion'])])
    assert repo.novedades(o.id)['p:' + anuncio('b').id_interno]['nueva']


def test_migracion_resultado_heredado_linea_base_y_grupo_sin_falso_nuevo(escenario06):
    _, s, o, repo = escenario06
    a, b = anuncio('a'), anuncio('b')
    repo.iniciar(o.id, 'heredada')
    repo.terminar(o.id, 'heredada', {'ids':[a.id_interno]})
    cat = CatalogoMutable([a])
    recalcular(s, cat, o.id)
    # Agrupación ya confirmada por v0.10: otro representante, sin deducir identidades.
    cat.items = [replace(b, inmueble_id='grupo-existente', publicaciones=(a,b)),
                 replace(a, inmueble_id='grupo-existente', publicaciones=(a,b))]
    recalcular(s, cat, o.id)
    n = repo.novedades(o.id)['g:grupo-existente']
    assert n['tipo'] == 'inicial' and not n['nueva'] and n['apariciones'] == 1
    assert len(s.coincidencias(o.id, cat)) == 1
    # Orden/repetición no crean detecciones.
    cat.items.reverse()
    recalcular(s, cat, o.id, True)
    assert repo.novedades(o.id)['g:grupo-existente']['detectada'] == n['detectada']
    cat.items = [a, b]  # Deshacer el grupo no deduplica las relaciones de seguimiento.
    recalcular(s, cat, o.id, True)
    estado = repo.novedades(o.id)
    assert estado['p:' + a.id_interno]['relacion'] != estado['p:' + b.id_interno]['relacion']
    assert not estado['p:' + a.id_interno]['nueva'] and not estado['p:' + b.id_interno]['nueva']


def test_solicitud_cache_limite_pendientes_excluidos_y_decisiones(escenario06, monkeypatch):
    _, s, o, repo = escenario06
    monkeypatch.setenv('GEMINI_MAX_CANDIDATES', '2')
    cat = CatalogoMutable([anuncio('a'), anuncio('b', habitaciones=None),
        anuncio('c', ofertas=(Oferta(operacion=Operacion.VENTA, precio=Decimal('999999999')),))])
    ia = GeminiFalso()
    recalcular(s, cat, o.id)
    antes = repo.novedades(o.id)
    repo.decision(o.id, anuncio('b').id_interno, 'preseleccionado')
    assert evaluar_manual(s, cat, o.id, ia)
    assert len(ia.llamadas) == 1 and len(ia.llamadas[0]) == 2
    assert repo.novedades(o.id) == antes
    assert {c['id'] for c in ia.llamadas[0]} == {anuncio('a').id_interno, anuncio('b').id_interno}
    assert next(r for r in s.coincidencias(o.id, cat) if r.inmueble.habitaciones is None).pendientes
    assert evaluar_manual(s, cat, o.id, ia)
    assert len(ia.llamadas) == 1
    datos = repo.ultima_gemini(o.id)['datos']
    assert datos['solicitudes'] == 0 and datos['reutilizadas'] == 2 and datos['enviados'] == 0
    ia.clave = ''
    assert evaluar_manual(s, cat, o.id, ia)
    assert repo.ultima_gemini(o.id)['datos']['resultado'] == 'cache'
    ia.clave = 'solo-prueba'
    assert repo.decisiones(o.id)[anuncio('b').id_interno]['estado'] == 'preseleccionado'
    cat.items.insert(0, anuncio('d'))
    recalcular(s, cat, o.id)
    assert len(ia.llamadas) == 1
    assert evaluar_manual(s, cat, o.id, ia)
    assert len(ia.llamadas) == 2 and len(ia.llamadas[-1]) == 1
    assert repo.ultima_gemini(o.id)['datos']['candidatos'] == 2


def test_concurrencia_doble_clic_y_fallo_sin_reintento(escenario06):
    _, s, o, repo = escenario06
    ia = GeminiFalso()
    solicitud = str(uuid4())
    barrera = Barrier(2)
    def reservar():
        barrera.wait(timeout=5)
        return solicitar_gemini(s, servicio(), o.id, solicitud, gemini=ia)
    with ThreadPoolExecutor(max_workers=2) as pool:
        tareas = [f.result() for f in [pool.submit(reservar), pool.submit(reservar)]]
    assert sum(t is not None for t in tareas) == 1
    next(t for t in tareas if t)()
    assert len(ia.llamadas) == 1
    assert solicitar_gemini(s, servicio(), o.id, solicitud, gemini=ia) is None
    # Fallo tampoco convierte el mismo clic en permiso para reintentar.
    class Falla(GeminiFalso):
        version = 'falla'
        def evaluar(self, n, cs):
            self.llamadas.append(cs)
            return {}, 'Prueba de fallo'
    ia = Falla()
    solicitud = str(uuid4())
    tarea = solicitar_gemini(s, servicio(), o.id, solicitud, gemini=ia)
    tarea()
    assert solicitar_gemini(s, servicio(), o.id, solicitud, gemini=ia) is None
    recalcular(s, servicio(), o.id, True)
    assert len(ia.llamadas) == 1 and repo.ultima_gemini(o.id)['datos']['resultado'] == 'error'


def test_api_explicitud_vista_previa_y_cambio_antes_del_clic(escenario06, monkeypatch):
    c, s, o, repo = escenario06
    monkeypatch.setattr('oportunidades.automatizacion.Gemini', GeminiFalso)
    url = f'/api/oportunidades/{o.id}/gemini'
    preview = c.get(url).json()
    assert preview['necesitan_evaluacion'] == 10 and not repo.ultima_gemini(o.id)
    assert c.post(url, json={}).status_code == 422
    datos = {'solicitud':str(uuid4()), 'huella':preview['huella']}
    assert c.post(url, json=datos).json()['aceptada']
    assert not c.post(url, json=datos).json()['aceptada']
    assert c.get(url).json()['necesitan_evaluacion'] == 0
    s.guardar_oportunidad(OportunidadDatos(cliente_id=o.cliente_id, necesidades=necesidades().model_copy(update={'habitaciones_min':2})), o.id)
    assert c.post(url, json={'solicitud':str(uuid4()), 'huella':preview['huella']}).status_code == 409
    pagina = c.get(f'/v0.6/clientes/{o.cliente_id}').text
    assert 'Los datos cambiaron' in pagina and 'hace falta una nueva solicitud' in pagina


@pytest.mark.parametrize('modo,categoria,http', [('timeout','timeout',None),('cuota','limite_uso',429),('http','proveedor',503),('red','conexion',None),('json','respuesta_invalida',200),('bloqueo','respuesta_invalida',200)])
def test_fallos_saneados_una_solicitud_y_tokens(monkeypatch, modo, categoria, http):
    monkeypatch.setenv('GEMINI_API_KEY','secreto-no-registrar')
    intentos = []
    cuerpo = {'modelVersion':'gemini-3.8-flash-001','usageMetadata':{'promptTokenCount':100,'candidatesTokenCount':30,'thoughtsTokenCount':20,'totalTokenCount':150},
              'candidates':[{'finishReason':'STOP','content':{'parts':[{'text':'invalido'}]}}]}
    def responder(req):
        intentos.append(req)
        if modo == 'timeout': raise httpx.ReadTimeout('secreto-no-registrar')
        if modo == 'red': raise httpx.ConnectError('secreto-no-registrar')
        if modo == 'bloqueo': cuerpo['candidates'] = []
        return httpx.Response(http or 200, json=cuerpo)
    real = httpx.Client
    monkeypatch.setattr(httpx,'Client',lambda **kw: real(transport=httpx.MockTransport(responder), **kw))
    ia = Gemini()
    evaluaciones, aviso = ia.evaluar({}, [candidato(comparar(necesidades(), inmueble()))])
    assert not evaluaciones and aviso and ia.reporte['resultado'] == categoria
    assert len(intentos) == 1 and ia.reporte['solicitudes'] == 1 and ia.reporte['http'] == http
    assert 'secreto-no-registrar' not in json.dumps(ia.reporte) + aviso
    if http == 200:
        assert ia.reporte['tokens']['totalTokenCount'] == 150
    if modo == 'timeout': assert 'puede ser desconocido' in aviso


def test_rest_simulado_persiste_consumo_saneado_y_cache(escenario06, monkeypatch):
    _, s, o, repo = escenario06
    monkeypatch.setenv('GEMINI_API_KEY', 'credencial-sintetica')
    solicitudes = []
    def responder(req):
        solicitudes.append(req)
        enviado = json.loads(json.loads(req.content)['contents'][0]['parts'][0]['text'])
        assert 'nombre' not in enviado and 'observaciones' not in enviado['necesidades']
        respuesta = {'evaluaciones':[{'id':c['id'], 'puntuacion':80, 'explicacion':'Ciudad documentada.',
            'evidencias':[{'campo':'ciudad','valor':c['hechos']['ciudad']}]} for c in enviado['candidatos']]}
        return httpx.Response(200, json={'modelVersion':'gemini-3.8-flash-001',
            'usageMetadata':{'promptTokenCount':100,'candidatesTokenCount':30,'thoughtsTokenCount':20,'cachedContentTokenCount':10,'totalTokenCount':150},
            'candidates':[{'finishReason':'STOP','content':{'parts':[{'text':json.dumps(respuesta)}]}}]})
    real = httpx.Client
    monkeypatch.setattr(httpx,'Client',lambda **kw: real(transport=httpx.MockTransport(responder), **kw))
    ia = Gemini()
    evaluar_manual(s, servicio(), o.id, ia)
    datos = repo.ultima_gemini(o.id)['datos']
    assert datos['resultado'] == 'correcto' and datos['http'] == 200
    assert datos['tokens']['totalTokenCount'] == 150 and datos['tokens']['thoughtsTokenCount'] == 20
    assert datos['version_modelo'] == 'gemini-3.8-flash-001' and datos['duracion_ms'] >= 0
    assert 'credencial-sintetica' not in json.dumps(datos)
    evaluar_manual(s, servicio(), o.id, ia)
    assert len(solicitudes) == 1 and repo.ultima_gemini(o.id)['datos']['solicitudes'] == 0


def test_vistas_limitadas_a_oportunidad_y_novedades_mostradas(escenario06):
    c, s, o, repo = escenario06
    cat = CatalogoMutable([anuncio('a')])
    recalcular(s, cat, o.id)
    otra = s.capturar(ClienteDatos(nombre='Otro escenario'), necesidades())
    recalcular(s, cat, otra.id)
    cat.items.extend([anuncio('b'), anuncio('c')])
    for oid in (o.id, otra.id): recalcular(s, cat, oid)
    n = repo.novedades(o.id)['p:' + anuncio('b').id_interno]
    token = n['relacion'] + '|' + n['ultima_deteccion']
    assert c.post(f'/v0.6/oportunidades/{otra.id}/novedades/vistas', data={'novedad':token}).status_code == 200
    assert repo.novedades(o.id)['p:' + anuncio('b').id_interno]['nueva']
    assert repo.novedades(otra.id)['p:' + anuncio('b').id_interno]['nueva']
    assert c.post(f'/v0.6/oportunidades/{o.id}/novedades/vistas', data={'novedad':token}).status_code == 200
    assert not repo.novedades(o.id)['p:' + anuncio('b').id_interno]['nueva']
    assert repo.novedades(o.id)['p:' + anuncio('c').id_interno]['nueva']


def test_sin_configuracion_sin_candidatos_y_privacidad(escenario06, monkeypatch):
    _, s, o, repo = escenario06
    class NoConfigurado(GeminiFalso):
        clave = ''
    ia = NoConfigurado()
    evaluar_manual(s, servicio(), o.id, ia)
    assert not ia.llamadas and repo.ultima_gemini(o.id)['datos']['resultado'] == 'configuracion'
    evaluar_manual(s, CatalogoMutable([]), o.id, ia)
    assert not ia.llamadas and repo.ultima_gemini(o.id)['datos']['resultado'] == 'sin_candidatos'
    s.guardar_oportunidad(OportunidadDatos(cliente_id=o.cliente_id, necesidades=necesidades(observaciones='Nombre privado correo@test.com 3001234567')), o.id)
    ia = GeminiFalso()
    cat = CatalogoMutable([anuncio('a', descripcion='Contactar Nombre 3001234567', caracteristicas=('Privado 3001234567',))])
    evaluar_manual(s, cat, o.id, ia)
    enviado = json.dumps(ia.llamadas)
    assert '3001234567' not in enviado and 'descripcion' not in enviado
    plan = plan_gemini(s.oportunidad(o.id), s.coincidencias(o.id, cat), repo, ia)
    assert 'observaciones' not in plan['necesidades']


@pytest.mark.parametrize('width,height', [(1440,900),(768,1024),(390,844)])
def test_browser_buscar_nuevo_vistas_y_gemini_sin_clave(servidor, pagina, escenario_consola, width, height):
    s = servicio_oportunidades()
    o = s.capturar(ClienteDatos(nombre='Cliente sintético'), necesidades())
    recalcular(s, servicio(), o.id)
    page = pagina
    page.set_viewport_size({'width':width,'height':height})
    page.goto(servidor + f'/v0.6/clientes/{o.cliente_id}')
    expect(page.locator('[data-new]')).to_have_count(0)
    # El catálogo incorpora una publicación conocida que antes excedía presupuesto.
    doc = escenario_consola['documentos']['11-M11']
    doc['normalized']['price'] = 109_000_000
    escenario_consola['store'].result(escenario_consola['run'], '11-M11', 'success', doc)
    page.get_by_role('button', name='Buscar coincidencias', exact=True).click()
    expect(page.locator('[data-new]')).to_have_count(1)
    expect(page.locator('[data-new-count]')).to_contain_text('1 coincidencia nueva')
    page.reload()
    expect(page.locator('[data-new]')).to_have_count(1)
    page.get_by_label('Ordenar candidatos').select_option('precio_desc')
    page.get_by_role('button', name='Ordenar', exact=True).click()
    expect(page.locator('[data-new]')).to_have_count(1)
    expect(page.locator('[data-gemini-preview]')).to_contain_text('Gemini no está configurado')
    page.get_by_role('button', name='Evaluar con Gemini', exact=True).focus()
    expect(page.get_by_role('button', name='Evaluar con Gemini', exact=True)).to_be_focused()
    page.get_by_role('button', name='Evaluar con Gemini', exact=True).click()
    expect(page.locator('[data-match-status]')).to_contain_text('Gemini no está configurado')
    assert page.locator('label').count() > 0
    page.wait_for_load_state('load')
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    salida = Path('.tmp/gemini-manual-20261111-browser')
    salida.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(salida / f'cliente-{width}.png'), full_page=True)
    page.get_by_role('button', name='Marcar novedades como vistas', exact=True).click()
    expect(page.locator('[data-new]')).to_have_count(0)
    assert not any(n['nueva'] for n in SeguimientoSQLite(s.repositorio.ruta).novedades(o.id).values())
