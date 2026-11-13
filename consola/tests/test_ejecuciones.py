"""Control durable sintético: no scraping, credenciales, Gemini ni recursos cloud."""
import asyncio
import copy
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from google.api_core.exceptions import NotFound, PreconditionFailed

from ejecuciones.control import ControlGCS, ACTIVE, Conflict, IntegrityError, empty, now, projection, reserve, select, measurements
from ejecuciones.cloud_run import CloudRun, reconcile
from ejecuciones.servicio import ServicioEjecuciones
from ejecuciones.worker import run_manual as execute_worker, scraper_for
from catalogo.persistencia.busquedas import BusquedasSQLite
from wasi.durable import EstadoGCS
from metro.storage import Store
from metro.web import app
from consola.durable import WebDurable
from consola.ejecuciones import context, remaining

A = 'https://www.metrocuadrado.com/inmuebles/venta/bogota/la-carolina'
B = 'https://www.metrocuadrado.com/inmuebles/venta/bogota/norte'

class Blob:
    def __init__(self):
        self.generation = 0
        self.serial = 0
        self.data = None
        self.fail = False
        self.mutex = threading.RLock()
    def reload(self, **kw):
        if self.data is None:
            raise NotFound('synthetic')
    def download_as_bytes(self, if_generation_match, **kw):
        with self.mutex:
            if if_generation_match != self.generation:
                raise PreconditionFailed('race')
            return self.data
    def upload_from_string(self, data, if_generation_match, **kw):
        with self.mutex:
            if self.fail:
                raise RuntimeError('SECRET_TOKEN_MUST_NOT_APPEAR')
            if if_generation_match != (self.generation if self.data is not None else 0):
                raise PreconditionFailed('race')
            self.data = data.encode() if isinstance(data, str) else data
            self.serial += 1
            self.generation = self.serial
    def delete(self, if_generation_match, **kw):
        with self.mutex:
            if self.data is None:
                raise NotFound('synthetic')
            if if_generation_match != self.generation:
                raise PreconditionFailed('race')
            self.data = None

class Storage:
    def __init__(self):
        self.blobs = {}
    def bucket(self, name):
        return self
    def blob(self, name):
        return self.blobs.setdefault(name, Blob())

class Cloud:
    def __init__(self):
        self.launched = []
        self.rows = []
        self.uncertain = False
        self.failure = False
        self.calls = 0
    def launch(self, key):
        self.launched.append(key)
        if self.uncertain:
            raise TimeoutError('SECRET_TOKEN_MUST_NOT_APPEAR')
        return 'projects/radar-inmobiliario-co/locations/us-central1/operations/synthetic'
    def executions(self, key):
        self.calls += 1
        if self.failure:
            raise PermissionError('SECRET_TOKEN_MUST_NOT_APPEAR')
        return self.rows
    def execution(self, worker):
        self.calls += 1
        if self.failure:
            raise PermissionError('synthetic')
        return self.rows[0] if self.rows else {'name':worker}

@pytest.fixture
def execution(tmp_path, monkeypatch):
    monkeypatch.delenv('GEMINI_API_KEY', raising=False)
    monkeypatch.setenv('RADAR_STATE_BUCKET', 'synthetic')
    monkeypatch.setenv('RADAR_EXECUTION_JOB', 'radar-manual')
    monkeypatch.setenv('CLOUD_RUN_EXECUTION', 'radar-manual-synthetic')
    storage = Storage()
    control = ControlGCS('synthetic', client=storage)
    factory = lambda: EstadoGCS('synthetic', client=storage)
    source = tmp_path / 'source'
    source.mkdir()
    repo = BusquedasSQLite(source / 'metro-consola.sqlite')
    repo.guardar('metrocuadrado', A, A, 'Carolina')
    repo.guardar('metrocuadrado', B, B, 'Norte')
    with factory() as state:
        state.guardar(source)
    cloud = Cloud()
    svc = ServicioEjecuciones(control, cloud, factory, str(tmp_path / 'web'))
    monkeypatch.setattr('consola.ejecuciones.ServicioEjecuciones', lambda: svc)
    for env, name in [('METRO_DB','metro.sqlite'), ('WASI_DB','wasi.sqlite'), ('FINCARAIZ_DB','fincaraiz.sqlite'), ('RADAR_CRM_DB','crm.sqlite')]:
        monkeypatch.setenv(env, str(tmp_path / name))
    return svc, repo, storage, factory, tmp_path


def run_manual(*args, **kwargs):
    # Playwright mantiene un loop propio en el hilo principal durante la suite.
    with ThreadPoolExecutor(1) as pool:
        return pool.submit(execute_worker, *args, **kwargs).result()


def start(execution, keys=None, request_id=None):
    svc = execution[0]
    return svc.start(keys if keys is not None else [['metrocuadrado', A]], request_id or str(uuid4()))


def test_new_search_is_immediately_selectable_and_saving_does_not_launch(execution):
    svc, repo, storage, factory, tmp = execution
    url = 'https://www.metrocuadrado.com/inmuebles/arriendo/bogota/centro'
    repo.guardar('metrocuadrado', url, url, 'Nueva')
    # Simula el guardado remoto ya existente de la web.
    with factory() as state:
        state.cargar(tmp / 'updated')
        b = BusquedasSQLite(tmp / 'updated' / 'metro-consola.sqlite')
        b.guardar('metrocuadrado', url, url, 'Nueva')
        state.guardar(tmp / 'updated')
    doc, _ = svc.overview(refresh=True)
    assert any(b['id_busqueda'] == url for b in doc['searches'])
    assert not svc.cloud.launched
    r = start(execution, [['metrocuadrado', url]])
    assert [b['id_busqueda'] for b in r['searches']] == [url]
    assert svc.cloud.launched == [r['id']]

@pytest.mark.parametrize('keys', [[], [['metrocuadrado', 'missing']], [['other', A]], [['metrocuadrado']], ['command'], None])
def test_rejects_invalid_selection_without_launch(execution, keys):
    svc = execution[0]
    with pytest.raises(ValueError):
        svc.start(keys, str(uuid4()))
    assert not svc.cloud.launched


def test_inactive_revalidated_at_launch(execution):
    svc, repo, storage, factory, tmp = execution
    svc.overview(refresh=True)
    with factory() as state:
        state.cargar(tmp / 'inactive')
        BusquedasSQLite(tmp / 'inactive' / 'metro-consola.sqlite').cambiar_estado('metrocuadrado', A, False)
        state.guardar(tmp / 'inactive')
    with pytest.raises(ValueError, match='inactiva'):
        start(execution)
    assert not svc.cloud.launched


def test_replays_and_competing_requests(execution):
    svc = execution[0]
    key = str(uuid4())
    first = start(execution, request_id=key)
    assert start(execution, request_id=key)['id'] == first['id']
    assert len(svc.cloud.launched) == 1
    with pytest.raises(Conflict):
        start(execution)
    with pytest.raises(Conflict):
        start(execution, [['metrocuadrado', B]], key)


def test_cas_concurrency_and_retains_updates(execution):
    control = execution[0].control
    selected = projection(execution[1])[:1]
    barrier = threading.Barrier(4)
    def attempt(i):
        barrier.wait()
        try:
            return reserve(control, str(uuid4()), selected)[0]['id']
        except Conflict:
            return None
    with ThreadPoolExecutor(4) as pool:
        results = list(pool.map(attempt, range(4)))
    assert len([r for r in results if r]) == 1
    r = control.read()[0]['runs'][0]
    with ThreadPoolExecutor(4) as pool:
        list(pool.map(lambda i: control.patch(r['id'], {f'metric_{i}': i}), range(4)))
    assert all(control.get(r['id'])[f'metric_{i}'] == i for i in range(4))


def test_uncertain_launch_is_not_repeated_and_recovers_after_reload(execution):
    svc = execution[0]
    svc.cloud.uncertain = True
    r = start(execution)
    assert r['status'] == 'uncertain'
    assert start(execution, request_id=r['id'])['id'] == r['id']
    assert len(svc.cloud.launched) == 1
    rebuilt = ServicioEjecuciones(ControlGCS('synthetic', client=execution[2]), svc.cloud, execution[3], str(execution[4] / 'reload'))
    assert rebuilt.overview()[0]['runs'][0]['id'] == r['id']
    assert len(svc.cloud.launched) == 1


def test_progress_and_history_do_not_touch_busy_snapshot(execution):
    svc, repo, storage, factory, tmp = execution
    r = start(execution)
    with factory():
        c = TestClient(WebDurable(app, estado_factory=lambda: pytest.fail('Seguimiento no debe cargar SQLite'), data_dir=str(tmp / 'unused')))
        response = c.get('/v0.6/ejecuciones')
        assert response.status_code == 200, response.text
        assert r['id'] in response.text
        state = c.get('/v0.6/ejecuciones/estado').json()
        assert state['active'] == r['id']
        assert 'Guardado durable final pendiente' in state['html']
        assert c.get('/v0.6/ejecuciones?run=' + r['id']).status_code == 200

@pytest.mark.parametrize('path,method', [('/v0.6/ejecuciones','get'), ('/v0.6/ejecuciones/estado','get'), ('/v0.6/ejecuciones','post')])
def test_authentication_protects_all_execution_routes(execution, monkeypatch, path, method):
    monkeypatch.setenv('RADAR_AUTH_MODE', 'iap')
    monkeypatch.setenv('RADAR_IAP_AUDIENCE', '/projects/56106530298/locations/us-central1/services/radar')
    monkeypatch.setenv('RADAR_PUBLIC_ORIGIN', 'https://radar.example')
    response = getattr(TestClient(app), method)(path)
    assert response.status_code == 401
    assert not execution[0].cloud.launched


def test_csrf_and_server_validation_and_fast_identifier(execution):
    c = TestClient(app)
    body = {'request_id': str(uuid4()), 'searches': [['metrocuadrado', A]]}
    assert c.post('/v0.6/ejecuciones', json=body, headers={'Origin': 'https://evil.example'}).status_code == 403
    for bad in ([], [['metrocuadrado', 'missing']], [['wasi', 'missing']]):
        assert c.post('/v0.6/ejecuciones', json={**body, 'searches': bad}).status_code == 422
    response = c.post('/v0.6/ejecuciones', json=body)
    assert response.status_code == 202
    assert response.json()['id'] == body['request_id']
    assert c.post('/v0.6/ejecuciones', json=body).status_code == 202
    assert len(execution[0].cloud.launched) == 1
    assert c.get('/v0.6/ejecuciones/estado?run=' + str(uuid4())).status_code == 404
    assert c.get('/v0.6/ejecuciones/estado?run=bad').status_code == 422


def test_interruption_reconciles_job_and_releases_only_its_lock(execution):
    svc, _, storage, factory, tmp = execution
    r = start(execution)
    state = factory().__enter__()
    svc.control.patch(r['id'], {'worker': 'synthetic', 'lock_generation': str(state.lock_generacion), 'status': 'running'})
    svc.cloud.rows = [{'name': 'synthetic', 'completionTime': now()}]
    svc.control.patch(r['id'], {'reconciled': None})
    doc = reconcile(svc.control, svc.cloud, svc.unlock)
    assert doc['runs'][0]['status'] == 'interrupted'
    assert doc['runs'][0]['searches'][0]['status'] == 'not_run'
    assert state.lock.data is None


def test_stale_heartbeat_is_not_failure_if_job_still_runs(execution):
    svc = execution[0]
    r = start(execution)
    svc.cloud.rows = [{'name': 'synthetic'}]
    svc.control.patch(r['id'], {'updated': '2020-01-01T00:00:00+00:00', 'reconciled': None})
    assert reconcile(svc.control, svc.cloud)['runs'][0]['status'] in ACTIVE
    assert svc.cloud.calls == 1
    reconcile(svc.control, svc.cloud)
    assert svc.cloud.calls == 1


def test_cloud_query_failure_keeps_reservation_and_sanitizes_errors(execution):
    svc = execution[0]
    r = start(execution)
    svc.cloud.failure = True
    svc.control.patch(r['id'], {'reconciled': None})
    assert reconcile(svc.control, svc.cloud)['runs'][0]['status'] in ACTIVE
    assert 'SECRET_TOKEN' not in json.dumps(svc.control.read()[0])


def test_aged_uncertain_launch_fenced_and_late_worker_cannot_run(execution):
    svc = execution[0]
    svc.cloud.uncertain = True
    r = start(execution)
    svc.control.patch(r['id'], {'created': (datetime.now(timezone.utc) - timedelta(minutes=15)).isoformat(), 'reconciled': None})
    assert reconcile(svc.control, svc.cloud)['runs'][0]['status'] == 'interrupted'
    assert run_manual(execution[4] / 'late', r['id'], svc.control, execution[3], make_scraper=lambda *a: pytest.fail('No Job tardío')) is False
    assert len(svc.cloud.launched) == 1


def fake_scrapers(outcomes, called, hook=None):
    class FakeScraper:
        def __init__(self, repo, folder, b):
            self.b = b
            self.run_id = None
            self.store = Store(folder / {'metrocuadrado':'metro.sqlite','wasi':'wasi.sqlite','fincaraiz':'fincaraiz.sqlite'}[b['fuente']], normalizar_busqueda=lambda x: x)
        async def run(self):
            called.append(self.b['id_busqueda'])
            key = self.b['id_busqueda']
            self.run_id = self.store.new_run(key, {'urls': [key]})
            self.store.save_page(self.run_id, 1, '1', key, 'fp', [{'id':'synthetic', 'url': A + '/synthetic', 'raw': {}}], None, search_url=key)
            self.store.plan_incremental(self.run_id)
            self.store.result(self.run_id, 'synthetic', 'success', {'normalized': {'price': 1_000_000}, 'quality': 'success'})
            if hook:
                hook()
            await asyncio.sleep(.003)
            return {'status': outcomes.pop(0)}
    return FakeScraper


def test_worker_only_selected_sequential_partial_and_remote_confirmation(execution):
    svc, repo, storage, factory, tmp = execution
    r = start(execution, [['metrocuadrado', B], ['metrocuadrado', A]])
    called = []
    assert run_manual(tmp / 'worker', r['id'], svc.control, factory, fake_scrapers(['completed','incomplete'], called), heartbeat=.001)
    result = svc.control.get(r['id'])
    assert called == [B, A]
    assert result['status'] == 'partial' and result['persisted'] is True
    assert [b['processed'] for b in result['searches']] == [1, 1]
    assert result['snapshot_generation']
    assert run_manual(tmp / 'duplicate', r['id'], svc.control, factory, lambda *a: pytest.fail('Duplicado')) is False
    assert called == [B,A]


def test_worker_does_not_execute_unselected_search(execution):
    svc, _, _, factory, tmp = execution
    r = start(execution, [['metrocuadrado', B]])
    called = []
    assert run_manual(tmp / 'worker', r['id'], svc.control, factory, fake_scrapers(['completed'],called), heartbeat=.001)
    assert called == [B]
    assert svc.control.get(r['id'])['status'] == 'completed'


def test_failed_upload_never_reports_success_and_stops_following_searches(execution):
    svc, _, storage, factory, tmp = execution
    r = start(execution, [['metrocuadrado', A], ['metrocuadrado', B]])
    called = []
    hook = lambda: setattr(storage.blob('radar/state.tar.gz'), 'fail', True)
    assert not run_manual(tmp / 'worker', r['id'], svc.control, factory, fake_scrapers(['completed'],called,hook), heartbeat=.001)
    result = svc.control.get(r['id'])
    assert result['status'] == 'failed' and result['persisted'] is False
    assert called == [A]
    assert result['searches'][1]['status'] == 'not_run'
    assert 'SECRET_TOKEN' not in json.dumps(result)


def test_guard_blocks_upload_when_lock_changes(execution):
    factory = execution[3]
    state = factory().__enter__()
    old = state.lock_generacion
    state.lock.delete(if_generation_match=old)
    replacement = factory().__enter__()
    with pytest.raises(RuntimeError, match='perdió'):
        state.guardar(execution[4] / 'source')
    with pytest.raises(PreconditionFailed):
        state.__exit__()
    replacement.__exit__()


def test_retention_never_prunes_active_or_catalog(execution):
    svc, _, storage, factory, tmp = execution
    selected = projection(execution[1])[:1]
    before = storage.blob('radar/state.tar.gz').data
    base, _ = reserve(svc.control, str(uuid4()), selected)
    old = (datetime.now(timezone.utc) - timedelta(days=31)).isoformat()
    def fill(doc):
        for i in range(110):
            r = copy.deepcopy(base)
            r.update(id=str(uuid4()), status='completed', finished=now())
            doc['runs'].append(r)
        r = copy.deepcopy(base)
        r.update(id='old', status='failed', finished=old)
        doc['runs'].append(r)
    svc.control.change(fill)
    rows = svc.control.read()[0]['runs']
    assert len(rows) == 101 and rows[0]['id'] == base['id']
    assert not any(r['id'] == 'old' for r in rows)
    assert storage.blob('radar/state.tar.gz').data == before


def test_load_and_remaining_need_comparable_history_and_never_negative():
    b = {'fuente':'metrocuadrado', 'id_busqueda': A, 'status':'completed', 'duration': 120, 'processed':20, 'finished':now()}
    doc = empty()
    assert measurements(doc,b)['load'] == 'Por estimar'
    doc['runs'] = [{'persisted':True,'searches':[dict(b, technical_run=i+1)]} for i in range(2)]
    assert measurements(doc,b)['range'] is None
    doc['runs'].append({'persisted':True,'searches':[dict(b, technical_run=3)]})
    assert measurements(doc,b)['load'] == 'Liviana'
    run = {'status':'running','searches':[dict(b,status='running',started='2020-01-01T00:00:00+00:00')]}
    assert 'superó' in remaining(doc,run)
    doc['runs'][0]['searches'][0]['duration'] = 1000
    assert measurements(doc,b)['load'] == 'Pesada'


def test_api_fixed_job_and_overrides_only_identifier():
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(200, json={'name':'projects/radar-inmobiliario-co/locations/us-central1/operations/synthetic'})
    with httpx.Client(transport=httpx.MockTransport(handler)) as session:
        cloud = CloudRun('radar-manual', session=session)
        key = str(uuid4())
        cloud.launch(key)
    body = json.loads(calls[0].content)
    assert body['overrides']['containerOverrides'][0]['args'] == ['--execution',key]
    assert str(calls[0].url).endswith('/jobs/radar-manual:run')
    with pytest.raises(ValueError):
        CloudRun('arbitrary-command', session=object())


def test_factory_isolates_all_three_source_configurations(monkeypatch, tmp_path):
    import ejecuciones.worker as worker
    class Repo:
        def listar(self):
            return [{'fuente': f, 'id_busqueda': k, 'activa': True} for f,k in [('wasi','wasi:a'),('wasi','wasi:b'),('fincaraiz','fr:a'),('fincaraiz','fr:b')]]
        def configuracion_wasi(self, key):
            return {'filtros': {'id_ciudad':'1'}, 'id':key}
        def configuracion_fincaraiz(self, key):
            return {'url_efectiva': A, 'id':key}
    for cls in ('Scraper','WasiScraper','FincaraizScraper'):
        monkeypatch.setattr(worker, cls, lambda cfg: cfg)
    for source, key in [('metrocuadrado',A), ('wasi','wasi:b'), ('fincaraiz','fr:b')]:
        cfg = scraper_for(Repo(), tmp_path, {'fuente':source,'id_busqueda':key})
        assert cfg.urls == [key] and cfg.concurrency == 1
        if source != 'metrocuadrado':
            assert list(cfg.searches) == [key]


def test_terminal_job_does_not_delete_a_new_lock(execution):
    svc, _, _, factory, _ = execution
    r = start(execution)
    state = factory().__enter__()
    old = state.lock_generacion
    state.__exit__()
    other = factory().__enter__()
    svc.control.patch(r['id'], {'lock_generation':str(old), 'reconciled':None})
    svc.cloud.rows = [{'completionTime': now()}]
    reconcile(svc.control, svc.cloud, svc.unlock)
    assert other.lock.data is not None
    other.__exit__()


def test_final_report_counts_are_backed_by_remote_snapshot(execution):
    svc, _, storage, factory, tmp = execution
    r = start(execution)
    assert run_manual(tmp / 'worker', r['id'], svc.control, factory, fake_scrapers(['completed'], []), heartbeat=.001)
    restored = factory()
    restored.cargar(tmp / 'after-revision')
    assert Store(tmp / 'after-revision' / 'metro.sqlite').summary(1)['unique'] == 1
    result = svc.control.get(r['id'])
    assert result['persisted'] and result['searches'][0]['new'] == 1


@pytest.mark.parametrize('viewport', [(1440,900),(768,1024),(390,844)])
def test_browser_states_selection_focus_and_no_page_overflow(execution, chromium, viewport):
    from urllib.parse import urlsplit
    from playwright.sync_api import expect
    svc = execution[0]
    doc, _ = svc.overview(refresh=True)
    original = copy.deepcopy(doc)
    client = TestClient(app)
    browser_context = chromium.new_context(viewport={'width':viewport[0], 'height':viewport[1]})
    page = browser_context.new_page()
    def route_request(route):
        request = route.request
        url = urlsplit(request.url)
        response = client.request(request.method, url.path + ('?' + url.query if url.query else ''),
                                  content=request.post_data_buffer,
                                  follow_redirects=False)
        headers = {k:v for k,v in response.headers.items() if k.lower() not in {'content-length','content-encoding'}}
        route.fulfill(status=response.status_code, headers=headers, body=response.content)
    page.route('**/*', route_request)
    def verify(name):
        page.goto('http://127.0.0.1/v0.6/ejecuciones')
        page.wait_for_load_state('networkidle')
        assert page.locator('h1').inner_text() == 'Radar Central'
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        assert page.locator('nav a[aria-current="page"]').inner_text() == 'Radar Central'
        page.keyboard.press('Tab')
        assert page.locator(':focus').count() == 1
        out = Path.cwd() / '.tmp' / 'ejecuciones-visual'
        out.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(out / f'{name}-{viewport[0]}.png'), full_page=True)
    try:
        # Sin historial y con selección individual/todas; inactivas nunca se habilitan.
        inactive = dict(doc['searches'][0], id_busqueda='wasi:inactive', fuente='wasi', nombre='Inactiva', activa=False)
        doc['searches'].append(inactive)
        svc.overview = lambda refresh=False: (doc, None)
        verify('sin-historial')
        expect(page.locator('[data-start]')).to_be_disabled()
        page.locator('[data-select-all]').check()
        expect(page.locator('[data-start]')).to_be_enabled()
        assert page.locator('[data-search]:checked').count() == 2
        expect(page.locator('[data-search][data-active="0"]')).to_be_disabled()
        page.locator('[data-search]').first.uncheck()
        assert page.locator('[data-search]:checked').count() == 1
        # Estado vacío.
        doc['searches'] = []
        verify('sin-busquedas')
        expect(page.get_by_text('No hay búsquedas guardadas disponibles.', exact=False)).to_be_visible()
        doc['searches'] = copy.deepcopy(original['searches'])
        r, _ = reserve(svc.control, str(uuid4()), doc['searches'])
        r.update(status='running', started=now(), phase='Recorriendo resultados')
        r['searches'][0].update(status='running',started=now(),phase='Recorriendo resultados',processed=7)
        doc['runs'] = [r]
        verify('progreso')
        expect(page.locator('[data-start]')).to_be_disabled()
        expect(page.get_by_text('En proceso:',exact=False)).to_be_visible()
        # Recargar recupera el mismo ID, sin nuevos Jobs.
        page.reload()
        expect(page.locator('[data-execution-report]')).to_contain_text(r['id'])
        assert svc.cloud.launched == []
        r.update(status='completed', finished=now(), persisted=True, snapshot_generation='1234',phase='Guardado remoto confirmado')
        for b in r['searches']:
            b.update(status='completed',started=now(),finished=now(),duration=120,processed=12,new=2,changed=1,unchanged=9)
        verify('completado')
        expect(page.get_by_text('Guardado durable confirmado en Cloud Storage.',exact=False)).to_be_visible()
        r.update(status='failed', persisted=False, error='Infraestructura: no se pudo confirmar el guardado.')
        r['searches'][0].update(status='failed',error='Portal: extracción no completada.')
        verify('error')
        expect(page.get_by_text('El guardado final no está confirmado.',exact=False)).to_be_visible()
    finally:
        browser_context.close()



def test_historical_measurements_readonly_and_without_duplicate_samples(execution):
    import hashlib
    from ejecuciones.mediciones import previous
    svc, _, _, factory, tmp = execution
    source = tmp / 'source'
    store = Store(source / 'metro.sqlite')
    for index in range(3):
        run = store.new_run(A, {'urls':[A]})
        store.update_run(run, status='completed',finished=now())
    search = projection(execution[1])[0]
    before = hashlib.sha256((source / 'metro.sqlite').read_bytes()).hexdigest()
    last, samples = previous(source,search)
    assert len(samples) == 3 and last['technical_run'] == 3
    assert hashlib.sha256((source / 'metro.sqlite').read_bytes()).hexdigest() == before
    doc = {'searches':[dict(search,baseline=samples)], 'runs':[{'persisted':True,'searches':[dict(samples[-1])]}]}
    assert measurements(doc,search)['range'] is not None
    doc['searches'][0]['baseline'] = samples[:1]
    doc['runs'][0]['searches'] = samples[:1]
    assert measurements(doc,search)['range'] is None


def test_sqlite_infrastructure_error_stops_the_entire_selection(execution):
    import sqlite3
    svc, _, _, factory, tmp = execution
    r = start(execution, [['metrocuadrado', A],['metrocuadrado', B]])
    called=[]
    class Broken:
        run_id = None
        async def run(self):
            called.append(A)
            raise sqlite3.DatabaseError('SECRET_TOKEN_MUST_NOT_APPEAR')
    assert not run_manual(tmp / 'worker', r['id'], svc.control, factory, lambda *a:Broken(), heartbeat=.001)
    assert called == [A]
    result = svc.control.get(r['id'])
    assert result['status']=='failed' and result['searches'][1]['status']=='not_run'
    assert 'SECRET_TOKEN' not in json.dumps(result)



def test_lock_acquisition_response_lost_recovers_same_owner(execution):
    factory = execution[3]
    state = factory()
    original = state.lock.upload_from_string
    def lost(*a, **kw):
        original(*a, **kw)
        raise TimeoutError('lost response')
    state.lock.upload_from_string = lost
    with state:
        assert state.lock_generacion == state.lock.generation
        state.asegurar_bloqueo()


def test_reconcile_cleans_lock_after_kill_before_generation_record(execution):
    svc, _, _, factory, _ = execution
    r = start(execution)
    state = factory().__enter__()
    svc.control.patch(r['id'], {'worker':'synthetic','status':'running','lock_token':state.lock_token,'reconciled':None})
    svc.cloud.rows = [{'completionTime':now()}]
    reconcile(svc.control,svc.cloud,svc.unlock)
    assert state.lock.data is None
    assert svc.control.get(r['id'])['status']=='interrupted'



def test_worker_claim_racing_reconciliation_is_not_closed_or_unlocked(execution):
    svc = execution[0]
    svc.cloud.uncertain = True
    r = start(execution)
    svc.control.patch(r['id'], {'created':'2020-01-01T00:00:00+00:00','reconciled':None})
    def racing(key):
        svc.control.patch(key, {'worker':'just-started','status':'running'})
        return []
    svc.cloud.executions = racing
    def forbidden(*a):
        pytest.fail('No puede retirar el lock de un trabajador que acaba de empezar')
    doc = reconcile(svc.control,svc.cloud,forbidden)
    assert doc['runs'][0]['status']=='running'


def test_failed_lock_cleanup_retains_reservation_until_reconciled(execution):
    svc = execution[0]
    r = start(execution)
    svc.cloud.rows = [{'completionTime':now()}]
    svc.control.patch(r['id'], {'worker':'synthetic','lock_generation':'123','reconciled':None})
    def failure(*a):
        raise TimeoutError('synthetic')
    assert reconcile(svc.control,svc.cloud,failure)['runs'][0]['status']=='reconciling'
    with pytest.raises(Conflict):
        start(execution)
    svc.control.patch(r['id'], {'reconciled':None})
    assert reconcile(svc.control,svc.cloud,lambda *a:None)['runs'][0]['status']=='interrupted'



def test_missing_expired_execution_reconciles_after_stale_heartbeat(execution):
    from requests import HTTPError, Response
    svc = execution[0]
    r = start(execution)
    def missing(worker):
        response = Response()
        response.status_code=404
        raise HTTPError(response=response)
    svc.cloud.execution = missing
    svc.control.patch(r['id'], {'worker':'expired-job','created':'2020-01-01T00:00:00+00:00','reconciled':None})
    assert reconcile(svc.control,svc.cloud)['runs'][0]['status'] in ACTIVE
    def stale(doc):
        doc['runs'][0].update(updated='2020-01-01T00:00:00+00:00',reconciled=None)
    svc.control.change(stale)
    assert reconcile(svc.control,svc.cloud)['runs'][0]['status']=='interrupted'



def test_browser_starts_only_chosen_search_and_reload_reuses_run(execution, chromium):
    from urllib.parse import urlsplit
    from playwright.sync_api import expect
    svc = execution[0]
    client = TestClient(app)
    context = chromium.new_context(viewport={'width':1200,'height':900})
    page = context.new_page()
    errors=[]
    requests=[]
    page.on('pageerror', lambda exc:errors.append(str(exc)))
    def route_request(route):
        req=route.request
        url=urlsplit(req.url)
        response=client.request(req.method,url.path + ('?' + url.query if url.query else ''),content=req.post_data_buffer,headers={k:v for k,v in req.headers.items() if k.lower() in {'content-type','origin'}},follow_redirects=False)
        if req.method == 'POST':
            requests.append((response.status_code,response.text))
        route.fulfill(status=response.status_code,headers={k:v for k,v in response.headers.items() if k.lower() not in {'content-length','content-encoding'}},body=response.content)
    page.route('**/*',route_request)
    try:
        page.goto('http://127.0.0.1/v0.6/ejecuciones')
        page.get_by_label('Seleccionar Norte',exact=True).check()
        page.get_by_role('button',name='Iniciar ejecución',exact=True).click()
        try:
            expect(page.locator('[data-execution-report]')).to_contain_text('Esperando Job')
        except AssertionError:
            pytest.fail(str({'errors':errors,'responses':requests,'notice':page.locator('[data-start-error]').inner_text()}))
        assert len(svc.cloud.launched)==1
        run=svc.control.get(svc.cloud.launched[0])
        assert [b['id_busqueda'] for b in run['searches']]==[B]
        page.reload()
        expect(page.locator('[data-execution-report]')).to_contain_text(run['id'])
        assert len(svc.cloud.launched)==1
    finally:
        context.close()



def test_final_persistence_phase_does_not_claim_estimate_was_exceeded():
    assert 'por estimar' in remaining(empty(), {'status':'saving','searches':[{'status':'extracted'}]})
    assert 'reconcilia' in remaining(empty(), {'status':'reconciling','searches':[{'status':'interrupted'}]})
