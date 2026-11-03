"""v0.6 con SQLite sintético; ninguna llamada externa ni modificación de datos reales."""
from dataclasses import replace
from decimal import Decimal
import hashlib
import json
from pathlib import Path
from unittest.mock import Mock

from bs4 import BeautifulSoup
from fastapi.testclient import TestClient
import httpx
import pytest

from metro.web import app, servicio
from oportunidades.servicio import servicio_oportunidades
from oportunidades.modelos import ClienteDatos, Necesidades, OportunidadDatos
from oportunidades.matching import comparar
from oportunidades.seguimiento import SeguimientoSQLite
from oportunidades.automatizacion import recalcular, despues_scraper, candidato
from oportunidades.gemini import Gemini
from catalogo.modelos import Oferta, Operacion, Disponibilidad, PresenciaBusqueda
from consola.inicio import indicadores
from test_v03 import necesidades, inmueble
from test_browser import servidor, pagina, seleccionar_barrio
from playwright.sync_api import expect


@pytest.fixture(autouse=True)
def sin_credenciales(monkeypatch):
    monkeypatch.delenv('GEMINI_API_KEY', raising=False)
    monkeypatch.delenv('GEMINI_MODEL', raising=False)
    monkeypatch.delenv('GEMINI_MAX_CANDIDATES', raising=False)


@pytest.fixture
def escenario06(escenario_consola):
    s = servicio_oportunidades()
    o = s.capturar(ClienteDatos(nombre='Ana'), necesidades())
    return TestClient(app), s, o, SeguimientoSQLite(s.repositorio.ruta)


def formulario(**cambios):
    return dict(nombre='Ana', operacion='compra', tipo='casa', ciudad='Bogotá',
                ubicaciones=['barrio:La Carolina'], presupuesto_max='110000000', **cambios)


def test_dashboard_cuatro_secciones_contadores_y_catalogo_inalterado(escenario06, escenario_consola):
    c, s, o, repo = escenario06
    store = escenario_consola['store']
    store.update_run(escenario_consola['run'], status='completed', finished='2026-11-03T16:11:51+00:00')
    antes = hashlib.sha256(escenario_consola['ruta'].read_bytes()).hexdigest()
    soup = BeautifulSoup(c.get('/v0.6/').text, 'html.parser')
    assert len(soup.select('main section')) == 4
    assert [n['data-dashboard-section'] for n in soup.select('main section')] == ['oportunidades', 'catalogo', 'fuente', 'nuevo-cliente']
    assert [n.text.strip() for n in soup.select('.metrics dd')][0] == '26'
    assert '03/11/2026 · 11:11' in soup.select_one('.metric-date').text
    assert soup.select('.metrics dd')[2].text == '26'
    assert soup.select_one('a[href="/v0.4/"]')
    assert hashlib.sha256(escenario_consola['ruta'].read_bytes()).hexdigest() == antes
    assert c.get('/v0.4/exportar.csv').status_code == 200


def test_ausencia_en_una_busqueda_no_es_retiro_global():
    i = inmueble(origen=replace(inmueble().origen, busquedas=(
        PresenciaBusqueda(id_busqueda='a', disponibilidad=Disponibilidad.ACTIVO),
        PresenciaBusqueda(id_busqueda='b', disponibilidad=Disponibilidad.POSIBLEMENTE_RETIRADO))))
    assert i.disponibilidad == Disponibilidad.ACTIVO
    assert indicadores([i], None)['ausentes'] == 1


def test_flujo_guardar_sin_criterios_secundarios_editar_y_cerrar(escenario06):
    c, s, o, repo = escenario06
    respuesta = c.post('/v0.6/oportunidades', data=formulario(), follow_redirects=False)
    assert respuesta.status_code == 303
    nueva = s.oportunidades()[0]
    assert '/v0.6/clientes/' in respuesta.headers['location']
    assert repo.leer(nueva.id)['estado'] == 'listo'
    ficha = c.get(respuesta.headers['location'])
    assert ficha.status_code == 200 and 'Gemini no está configurado' in ficha.text
    assert 'Pendiente de verificar' not in BeautifulSoup(ficha.text, 'html.parser').select_one('.candidate-table').text
    editada = c.post('/v0.6/oportunidades', data=formulario(cliente_id=nueva.cliente_id,
        oportunidad_id=nueva.id, habitaciones_max='2', estado='cerrada'))
    assert editada.status_code == 200
    assert s.oportunidad(nueva.id).estado == 'cerrada'
    assert repo.leer(nueva.id)['estado'] == 'listo'
    assert c.post(f'/v0.6/oportunidades/{nueva.id}/recalcular').status_code == 422


@pytest.mark.parametrize('campos', [{'presupuesto_min':'120000000'}, {'habitaciones_min':'4','habitaciones_max':'2'}, {'ubicaciones':[]}])
def test_formulario_valida_sin_crear_clientes(escenario06, campos):
    c, s, _, _ = escenario06
    datos = formulario() | campos
    antes = len(s.clientes())
    respuesta = c.post('/v0.6/oportunidades', data=datos)
    assert respuesta.status_code == 422 and 'Revisa los datos' in respuesta.text
    assert len(s.clientes()) == antes


def test_cliente_inactivo_y_reactivacion_conservan_historia(escenario06):
    c, s, o, repo = escenario06
    assert c.post(f'/v0.6/clientes/{o.cliente_id}', data={'nombre':'Ana nueva','activo':'0'}).status_code == 200
    assert not repo.activo(o.cliente_id)
    assert 'Ana nueva' not in c.get('/v0.6/clientes').text
    assert 'Ana nueva' in c.get('/v0.6/clientes?vista=inactivos').text
    assert not recalcular(s, servicio(), o.id)
    assert c.post(f'/v0.6/clientes/{o.cliente_id}', data={'nombre':'Ana nueva','activo':'1'}).status_code == 200
    assert repo.activo(o.cliente_id) and repo.leer(o.id)
    assert s.oportunidad(o.id).creado_en == o.creado_en


def test_decisiones_independientes_del_motor_persisten_y_se_editan(escenario06):
    c, s, o, repo = escenario06
    iid = s.coincidencias(o.id, servicio())[0].inmueble.id_interno
    endpoint = f'/v0.6/oportunidades/{o.id}/decision'
    assert c.post(endpoint, data={'inmueble':iid,'estado':'preseleccionado'}).status_code == 200
    recalcular(s, servicio(), o.id)
    assert SeguimientoSQLite(s.repositorio.ruta).decisiones(o.id)[iid]['estado'] == 'preseleccionado'
    otra = s.capturar(ClienteDatos(nombre='Otro'), necesidades())
    assert not repo.decisiones(otra.id)
    s.guardar_oportunidad(OportunidadDatos(cliente_id=o.cliente_id, necesidades=necesidades().model_copy(update={'habitaciones_min':20})), o.id)
    recalcular(s, servicio(), o.id)
    ficha = c.get(f'/v0.6/clientes/{o.cliente_id}')
    assert 'Decisiones fuera de los candidatos actuales (1)' in ficha.text
    assert c.post(endpoint, data={'inmueble':iid,'estado':'descartado'}).status_code == 200
    assert repo.decisiones(o.id)[iid]['estado'] == 'descartado'
    assert c.post(endpoint, data={'inmueble':iid,'estado':'pendiente'}).status_code == 200
    assert c.post(endpoint, data={'inmueble':'inventado','estado':'pendiente'}).status_code == 404
    assert c.post(endpoint, data={'inmueble':iid,'estado':'vendido'}).status_code == 422


def test_limites_estrictos_y_preferencias_sin_descarte():
    n = Necesidades.model_validate(necesidades().model_dump() | {'presupuesto_min':'106000000', 'habitaciones_max':4})
    assert comparar(n, inmueble()) is None
    assert comparar(n, inmueble(ofertas=())) is not None
    n = Necesidades.model_validate(necesidades().model_dump() | {'habitaciones_min':None,'habitaciones_max':2,'preferencias':['habitaciones_max']})
    assert comparar(n, inmueble()) is None
    r = comparar(necesidades(banos_min=20, parqueaderos_min=10, area_min_m2=1000, antiguedad_max=1), inmueble())
    assert r.confirmada and len(r.preferencias_no_cumplidas) == 3 and r.preferencias_pendientes
    assert not comparar(necesidades(), inmueble(habitaciones=None)).confirmada


def test_fuentes_normalizadas_duplicados_y_sin_extraccion(escenario06, escenario_consola):
    c, _, _, _ = escenario06
    antes = escenario_consola['ruta'].read_bytes()
    datos = {'nombre':'En la Carolina', 'url':'http://metrocuadrado.com/inmuebles/venta/bogota/la-carolina/?utm_source=a#hola'}
    r = c.post('/v0.6/fuentes', data=datos)
    assert r.status_code == 200 and 'Fuente guardada' in r.text
    datos['nombre'] = 'Otro nombre'
    datos['url'] = 'https://www.metrocuadrado.com/inmuebles/venta/bogota/la-carolina'
    r = c.post('/v0.6/fuentes', data=datos)
    assert 'ya está registrada' in r.text
    guardadas = servicio().listar_busquedas()
    assert len(guardadas) == 1 and guardadas[0]['nombre'] == 'En la Carolina'
    assert guardadas[0]['url'] == guardadas[0]['id_busqueda'] == datos['url']
    assert escenario_consola['ruta'].read_bytes() == antes


@pytest.mark.parametrize('url', ['https://evil.com/inmuebles/venta','https://metrocuadrado.com.evil.com/inmuebles/venta',
    'javascript:alert(1)','https://metrocuadrado.com/inmueble/1', 'https://usuario@metrocuadrado.com/inmuebles/venta',
    'https://metrocuadrado.com:99/inmuebles/venta','https://metrocuadrado.com/inmuebles/ven ta'])
def test_fuentes_invalidas(escenario06, url):
    c, *_ = escenario06
    assert c.post('/v0.6/fuentes', data={'nombre':'Fuente','url':url}).status_code == 422
    assert not servicio().listar_busquedas()


class GeminiFalso:
    modelo, clave, version = 'gemini-prueba-flash', 'solo-prueba', 'test'
    def __init__(self):
        self.llamadas = []
    def evaluar(self, necesidades, candidatos):
        self.llamadas.append(candidatos)
        return {c['id']: {'id':c['id'], 'puntuacion':70, 'explicacion':'Coincide con los hechos',
                          'evidencias':[{'campo':'ciudad','valor':c['hechos']['ciudad']}]} for c in candidatos}, ''


def test_matching_cache_no_duplicados_cambios_y_manual(escenario06):
    c, s, o, repo = escenario06
    ia = GeminiFalso()
    assert recalcular(s, servicio(), o.id, gemini=ia)
    assert len(ia.llamadas) == 1
    assert not recalcular(s, servicio(), o.id, gemini=ia)
    assert recalcular(s, servicio(), o.id, True, ia)
    assert len(ia.llamadas) == 1  # manual tampoco repite evaluaciones intactas
    assert len(repo.leer(o.id)['datos']['evaluaciones']) == 10
    s.guardar_oportunidad(OportunidadDatos(cliente_id=o.cliente_id, necesidades=necesidades(observaciones='Prefiere terraza')), o.id)
    assert recalcular(s, servicio(), o.id, gemini=ia)
    assert len(ia.llamadas) == 2
    assert repo.iniciar(o.id, 'nueva', True)
    assert not repo.iniciar(o.id, 'otra', True)


def test_despues_scraper_actualiza_solo_abiertas_y_no_escribe_catalogo(escenario06, escenario_consola):
    _, s, o, repo = escenario06
    cerrada = s.capturar(ClienteDatos(nombre='Cerrada'), necesidades(), estado='cerrada')
    antes = escenario_consola['ruta'].read_bytes()
    despues_scraper(escenario_consola['ruta'])
    assert repo.leer(o.id) and not repo.leer(cerrada.id)
    assert escenario_consola['ruta'].read_bytes() == antes


def test_cambios_durante_evaluacion_se_recalculan_despues(escenario06):
    _, s, o, repo = escenario06
    class CambiaDuranteGemini(GeminiFalso):
        def evaluar(self, n, candidatos):
            if not self.llamadas:
                nuevos = Necesidades.model_validate(o.necesidades.model_dump() | {'habitaciones_min': 2})
                s.guardar_oportunidad(OportunidadDatos(cliente_id=o.cliente_id, necesidades=nuevos), o.id)
                assert not recalcular(s, servicio(), o.id, gemini=self)
            return super().evaluar(n, candidatos)
    ia = CambiaDuranteGemini()
    assert recalcular(s, servicio(), o.id, gemini=ia)
    assert len(ia.llamadas) == 2
    assert repo.leer(o.id)['datos']['necesidades_huella'] != ''
    assert not recalcular(s, servicio(), o.id, gemini=ia)


def test_no_mostrar_ia_obsoleta_y_orden_manual(escenario06):
    c, s, o, repo = escenario06
    recalcular(s, servicio(), o.id, gemini=GeminiFalso())
    url = f'/v0.6/clientes/{o.cliente_id}'
    assert 'Coincide con los hechos' in c.get(url + '?orden=ia').text
    s.guardar_oportunidad(OportunidadDatos(cliente_id=o.cliente_id, necesidades=necesidades(observaciones='Otra preferencia')), o.id)
    assert 'Coincide con los hechos' not in c.get(url).text
    assert c.post(f'/v0.6/oportunidades/{o.id}/recalcular', follow_redirects=False).status_code == 303
    assert 'Gemini no está configurado' in c.get(url).text
    soup = BeautifulSoup(c.get(url + '?orden=precio').text, 'html.parser')
    primero = soup.select_one('[data-candidate]')['data-candidate']
    assert servicio().obtener(primero).origen.id_original == '1-M1'
    assert c.get(url + '?orden=inventado').status_code == 422


def test_fuentes_registradas_disponibles_en_cli(escenario06, escenario_consola, monkeypatch):
    import metro.__main__ as cli
    c, _, _, _ = escenario06
    c.post('/v0.6/fuentes', data={'nombre':'Fuente CLI','url':'https://metrocuadrado.com/inmuebles/venta/bogota/la-carolina'})
    capturada = []
    class ScraperPrueba:
        def __init__(self, config):
            capturada.append(config)
        async def run(self):
            return {'status':'completed'}
    monkeypatch.setattr(cli, 'Scraper', ScraperPrueba)
    monkeypatch.setattr('sys.argv', ['metro','--db',str(escenario_consola['ruta']),'scrape','--fuentes-registradas'])
    # El main CLI es síncrono; separarlo del loop de la sesión Playwright cuando existe.
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor() as executor:
        executor.submit(cli.main).result()
    assert capturada[0].urls == ['https://www.metrocuadrado.com/inmuebles/venta/bogota/la-carolina']


def test_hook_scraper_no_oculta_exito_ante_fallo_crm(escenario_consola, monkeypatch):
    import asyncio
    import concurrent.futures
    import metro.scraper as modulo
    from unittest.mock import AsyncMock
    from oportunidades import automatizacion
    hook = Mock(side_effect=RuntimeError('CRM de prueba no disponible'))
    monkeypatch.setattr(automatizacion, 'despues_scraper', hook)
    scraper = modulo.Scraper(modulo.Config(db=str(escenario_consola['ruta']), resume=escenario_consola['run']))
    scraper.discover = AsyncMock()
    scraper.process_details = AsyncMock()
    browser = Mock(new_context=AsyncMock(return_value=Mock(route=AsyncMock())), close=AsyncMock())
    playwright = Mock(chromium=Mock(launch=AsyncMock(return_value=browser)))
    monkeypatch.setattr(modulo, 'async_playwright', lambda: Mock(__aenter__=AsyncMock(return_value=playwright), __aexit__=AsyncMock(return_value=False)))
    with scraper.store.connect() as db:
        db.execute('UPDATE run_searches SET listing_complete=1')
        db.execute('UPDATE runs SET listing_complete=1')
    with concurrent.futures.ThreadPoolExecutor() as executor:
        resultado = executor.submit(lambda: asyncio.run(scraper._run())).result()
    assert resultado['status'] == 'completed'
    hook.assert_called_once()


def test_actividad_cliente_y_pendientes_reales(escenario06):
    c, s, o, repo = escenario06
    otra = s.capturar(ClienteDatos(nombre='Sin pendientes'), necesidades())
    for r in s.coincidencias(otra.id, servicio()):
        repo.decision(otra.id, r.inmueble.id_interno, 'descartado')
    soup = BeautifulSoup(c.get('/v0.6/').text, 'html.parser')
    filas = soup.select('.opportunities tbody tr')
    assert 'Ana' in filas[0].text and filas[0].select_one('.count').text == '10'
    assert filas[1].select_one('.count').text == '0'
    assert 'Decisión guardada' in filas[1].text


def test_gemini_rest_estructurado_y_validacion(monkeypatch):
    monkeypatch.setenv('GEMINI_API_KEY', 'test-no-real')
    r = comparar(necesidades(), inmueble())
    candidato_ia = candidato(r)
    datos = {'evaluaciones':[{'id':r.inmueble.id_interno,'puntuacion':85,'explicacion':'Ubicación compatible.',
                             'evidencias':[{'campo':'ciudad','valor':'Bogotá'}]}]}
    def respuesta():
        return {'candidates':[{'finishReason':'STOP','content':{'parts':[{'text':json.dumps(datos)}]}}]}
    cliente = Mock()
    cliente.post.return_value.json.side_effect = respuesta
    monkeypatch.setattr(httpx, 'Client', lambda **kw: Mock(__enter__=Mock(return_value=cliente), __exit__=Mock(return_value=False)))
    evaluaciones, aviso = Gemini().evaluar(necesidades().model_dump(mode='json'), [candidato_ia])
    assert evaluaciones[r.inmueble.id_interno]['puntuacion'] == 85 and not aviso
    cuerpo = cliente.post.call_args.kwargs['json']
    assert cuerpo['generationConfig']['responseMimeType'] == 'application/json'
    assert 'responseJsonSchema' in cuerpo['generationConfig']
    assert cuerpo['generationConfig']['thinkingConfig']['thinkingLevel'] == 'LOW'
    assert 'temperature' not in cuerpo['generationConfig']
    assert 'gemini-3.8-flash:generateContent' in cliente.post.call_args.args[0]
    assert 'nombre' not in cuerpo['contents'][0]['parts'][0]['text']
    for campo, valor in [('id','inventado'),('puntuacion',101),('evidencias',[{'campo':'banos','valor':'99'}])]:
        original = datos['evaluaciones'][0][campo]
        datos['evaluaciones'][0][campo] = valor
        assert Gemini().evaluar({}, [candidato_ia])[0] == {}
        datos['evaluaciones'][0][campo] = original
    cliente.post.side_effect = httpx.ConnectError('prueba')
    assert 'matching determinista' in Gemini().evaluar({}, [candidato_ia])[1]


@pytest.mark.parametrize('width,height', [(1440,900),(768,1024),(390,844)])
def test_navegacion_responsive_creacion_revision_y_catalogo(servidor, pagina, width, height):
    page = pagina
    page.set_viewport_size({'width':width,'height':height})
    page.goto(servidor + '/v0.6/')
    assert page.locator('[data-dashboard-section]').count() == 4
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), page.evaluate('''[...document.querySelectorAll('body *')].filter(e=>e.getBoundingClientRect().right>innerWidth && getComputedStyle(e).position!=='absolute').slice(0,12).map(e=>[e.tagName,e.className,e.getBoundingClientRect().right])''')
    page.screenshot(path=str(Path('.tmp') / f'v06-inicio-{width}.png'), full_page=True)
    page.get_by_role('link', name='Registrar cliente y necesidad').click()
    page.locator('#crm_nombre').fill('Cliente v06')
    page.locator('#crm_tipo').select_option('casa')
    page.locator('#crm_ciudad').select_option(label='Bogotá')
    page.locator('#crm_presupuesto').fill('110000000')
    seleccionar_barrio(page, True)
    page.get_by_role('button', name='Confirmar y guardar oportunidad').click()
    expect(page.locator('h1')).to_have_text('Cliente v06')
    expect(page.locator('[data-match-status]')).to_contain_text('Gemini no está configurado')
    assert page.locator('[data-candidate]').count() == 10
    page.screenshot(path=str(Path('.tmp') / f'v06-cliente-{width}.png'), full_page=True)
    page.locator('.decision-form select').first.select_option('preseleccionado')
    page.locator('.decision-form button').first.click()
    expect(page.locator('.decision-form select').first).to_have_value('preseleccionado')
    # El valor del select puede estar disponible antes de terminar la navegación y cargar CSS.
    page.wait_for_load_state('load')
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), page.evaluate('''[...document.querySelectorAll('body *')].filter(e=>e.getBoundingClientRect().right>innerWidth && getComputedStyle(e).position!=='absolute').slice(0,12).map(e=>[e.tagName,e.className,e.getBoundingClientRect().right])''')
    page.get_by_role('link', name='Editar necesidades').click()
    expect(page.locator('#crm_nombre')).to_have_value('Cliente v06')
    assert page.locator('input[name=preferencias]').count() == 0
    page.goto(servidor + '/v0.4/?limit=12&offset=12&orden=id')
    page.goto(servidor + '/v0.6/')
    page.get_by_role('link', name='Abrir catálogo completo').click()
    assert 'offset=12' in page.url


@pytest.mark.parametrize('width', [1440, 390])
def test_selector_barrios_guia_ciudad_y_distingue_estados_vacios(escenario_consola, servidor, pagina, width):
    # Patrón observado: una ciudad con barrios confirmados y otra sin ellos.
    for iid, doc in escenario_consola['documentos'].items():
        if doc['normalized']['city'] == 'Medellín':
            doc['normalized'].update(city='Cartagena de Indias', neighborhood=None, zone=None)
            escenario_consola['store'].result(escenario_consola['run'], iid, 'success', doc)
    page = pagina
    page.set_viewport_size({'width':width, 'height':900})
    page.goto(servidor + '/v0.6/')
    page.get_by_role('link', name='Registrar cliente y necesidad').click()
    assert page.url == servidor + '/v0.6/nuevo'
    expect(page.locator('h1')).to_have_text('Registrar cliente y necesidad')
    expect(page.locator('#crm-form')).to_be_visible()
    page.locator('[data-location-picker] > summary').click()
    expect(page.locator('[data-location-empty]')).to_contain_text('Primero selecciona una ciudad')
    expect(page.locator('[data-location-search]')).to_be_disabled()
    page.locator('#crm_ciudad').select_option(label='Cartagena de Indias')
    page.locator('[data-location-picker] > summary').click()
    expect(page.locator('[data-location-empty]')).to_contain_text('No hay barrios disponibles en el catálogo para esta ciudad')
    page.locator('#crm_ciudad').select_option(label='Bogotá')
    page.locator('[data-location-picker] > summary').click()
    expect(page.locator('[data-location-search]')).to_be_enabled()
    expect(page.locator('[data-location-row]:visible')).to_have_count(1)
    page.locator('[data-location-search]').fill('barrio inexistente')
    expect(page.locator('[data-location-empty]')).to_contain_text('No hay barrios que coincidan con el texto')
    page.locator('[data-location-search]').fill('carolína')
    expect(page.locator('[data-location-row]:visible')).to_have_count(1)
    page.locator('[data-location-row]:visible input').check()
    page.keyboard.press('Escape')
    expect(page.locator('[data-location-picker] > summary')).to_be_focused()
    expect(page.locator('[data-location-tags]')).to_contain_text('La Carolina')
    page.locator('#crm_nombre').fill('Cliente prueba barrios')
    page.locator('#crm_tipo').select_option('casa')
    page.locator('#crm_presupuesto').fill('110000000')
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    page.get_by_role('button', name='Confirmar y guardar oportunidad').click()
    expect(page.locator('h1')).to_have_text('Cliente prueba barrios')
    expect(page.locator('[data-candidate]')).to_have_count(10)


def test_selector_barrios_con_ciudad_unica_preseleccionada(escenario_consola, servidor, pagina):
    for iid, doc in escenario_consola['documentos'].items():
        doc['normalized']['city'] = 'Bogotá D.C.'
        escenario_consola['store'].result(escenario_consola['run'], iid, 'success', doc)
    pagina.goto(servidor + '/v0.6/nuevo')
    expect(pagina.locator('#crm_ciudad')).to_have_value('Bogotá D.C.')
    pagina.locator('[data-location-picker] > summary').click()
    expect(pagina.locator('[data-location-search]')).to_be_enabled()
    expect(pagina.locator('[data-location-row]:visible')).to_have_count(1)
