"""Reproduce generaciones reales del SDK instalado, sin red ni recursos cloud."""
import json
from urllib.parse import unquote
from uuid import uuid4

import pytest
from google.auth.credentials import AnonymousCredentials
from google.cloud import storage
from google.api_core.exceptions import NotFound, PreconditionFailed

from ejecuciones.control import ControlGCS, reserve, Conflict, now
from ejecuciones.cloud_run import reconcile
from ejecuciones.servicio import ServicioEjecuciones
from wasi.durable import EstadoGCS
from consola.tests.test_ejecuciones import execution, start


@pytest.fixture
def versioned(monkeypatch):
    client = storage.Client(project='synthetic', credentials=AnonymousCredentials())
    versions, latest, requests = {}, {}, []
    def metadata(method, path, query_params=None, **kw):
        assert method == 'GET'
        name = unquote(path.split('/o/', 1)[1])
        requests.append(dict(query_params or {}))
        gen = int((query_params or {}).get('generation') or latest.get(name, 0))
        if not gen or gen not in versions.get(name, {}):
            raise NotFound('synthetic')
        return {'name': name, 'bucket': 'synthetic', 'generation': str(gen)}
    def upload(blob, data, if_generation_match, **kw):
        current = latest.get(blob.name, 0)
        if int(if_generation_match) != current:
            raise PreconditionFailed('synthetic race')
        gen = max(versions.get(blob.name, {0: None})) + 1
        versions.setdefault(blob.name, {})[gen] = data.encode() if isinstance(data, str) else data
        latest[blob.name] = gen
        blob._properties['generation'] = str(gen)
    def download(blob, if_generation_match, **kw):
        gen = blob.generation or latest.get(blob.name, 0)
        if int(if_generation_match) != gen:
            raise PreconditionFailed('synthetic race')
        if not gen or gen not in versions.get(blob.name, {}):
            raise NotFound('synthetic')
        return versions[blob.name][gen]
    def delete(blob, if_generation_match, **kw):
        # The SDK's generation query can address a historical object. Retain versions
        # here to expose that hazard; a fresh handle must check the live generation.
        gen = blob.generation or latest.get(blob.name, 0)
        if not gen:
            raise NotFound('synthetic')
        if int(if_generation_match) != gen:
            raise PreconditionFailed('synthetic race')
        if latest.get(blob.name) == gen:
            latest.pop(blob.name)
    monkeypatch.setattr(client._connection, 'api_request', metadata)
    monkeypatch.setattr(storage.Blob, 'upload_from_string', upload)
    monkeypatch.setattr(storage.Blob, 'download_as_bytes', download)
    monkeypatch.setattr(storage.Blob, 'delete', delete)
    return client, latest, requests


def test_sdk_reload_reuses_historical_generation_but_control_reads_live(versioned):
    client, latest, requests = versioned
    control = ControlGCS('synthetic', client=client)
    control.change(lambda d: d.update(catalog_updated='first'))
    legacy_handle = control.blob
    legacy_handle.reload()
    old = legacy_handle.generation
    other_web = ControlGCS('synthetic', client=client)
    other_web.change(lambda d: d.update(catalog_updated='second'))
    # Confirm the actual SDK's historical behavior that the old adapter missed.
    legacy_handle.reload()
    assert legacy_handle.generation == old
    assert requests[-1]['generation'] == old
    assert json.loads(legacy_handle.download_as_bytes(if_generation_match=old))['catalog_updated'] == 'first'
    assert control.read()[0]['catalog_updated'] == 'second'
    assert 'generation' not in requests[-1]


def test_cas_retry_refreshes_generation_and_preserves_competing_write(versioned, monkeypatch):
    client, _, _ = versioned
    control = ControlGCS('synthetic', client=client)
    control.change(lambda d: d.update(catalog_updated='initial'))
    original = storage.Blob.upload_from_string
    competed = []
    def race(blob, *args, **kw):
        if not competed:
            competed.append(True)
            ControlGCS('synthetic', client=client).change(lambda d: d.update(searches=[{'marker':'web'}]))
        return original(blob, *args, **kw)
    monkeypatch.setattr(storage.Blob, 'upload_from_string', race)
    control.change(lambda d: d.update(catalog_updated='worker'))
    doc, _ = control.read()
    assert doc['catalog_updated'] == 'worker' and doc['searches'] == [{'marker':'web'}]


def test_lock_checks_live_object_and_never_removes_replacement(versioned):
    client, latest, _ = versioned
    old = EstadoGCS('synthetic', client=client).__enter__()
    original = old.lock_generacion
    old.__exit__()
    replacement = EstadoGCS('synthetic', client=client).__enter__()
    assert replacement.lock_generacion != original
    with pytest.raises(RuntimeError, match='perdió'):
        old.asegurar_bloqueo()
    with pytest.raises(PreconditionFailed):
        old.__exit__()
    assert latest['radar/state.tar.gz.lock'] == replacement.lock_generacion
    replacement.asegurar_bloqueo()
    replacement.__exit__()
    with pytest.raises(NotFound):
        replacement.asegurar_bloqueo()


def test_web_observer_does_not_invalidate_legacy_worker_handle(execution, versioned):
    client, _, _ = versioned
    svc = execution[0]
    svc.control = ControlGCS('synthetic', client=client)
    run, _ = reserve(svc.control, str(uuid4()), [{'fuente':'metrocuadrado','id_busqueda':'synthetic','nombre':'Sintética','url':'synthetic','activa':True}])
    svc.control.patch(run['id'], {'status':'running','worker':'legacy-worker'})
    pinned = svc.control.blob
    pinned.reload()
    initial = pinned.generation
    svc.cloud.rows = [{'name':'legacy-worker'}]
    # Repeated page loads and JSON polling are observational even with stale history.
    for _ in range(3):
        doc, _ = svc.overview(refresh=True)
        assert doc['runs'][0]['verification']['state'] == 'active'
    assert svc.control.read()[1] == initial
    payload = json.loads(pinned.download_as_bytes(if_generation_match=initial))
    payload['runs'][0]['phase'] = 'Heartbeat del ejecutor anterior'
    pinned.upload_from_string(json.dumps(payload), if_generation_match=initial)
    assert svc.control.get(run['id'])['phase'] == 'Heartbeat del ejecutor anterior'


def test_launch_acknowledgment_does_not_overwrite_worker_claim(execution):
    svc = execution[0]
    def claimed(key):
        svc.control.patch(key, {'worker':'fast-worker','status':'running'})
        return 'operation/synthetic'
    svc.cloud.launch = claimed
    run = start(execution)
    assert run['worker'] == 'fast-worker' and run['status'] == 'running'


@pytest.mark.parametrize('remote', ['active','unknown'])
def test_active_or_uncertain_never_unlocks_or_changes_control(execution, remote):
    svc = execution[0]
    run = start(execution)
    svc.control.patch(run['id'], {'status':'running','worker':'alive','lock_generation':'1','updated':'2020-01-01T00:00:00+00:00'})
    svc.cloud.rows = [{'name':'alive'}]
    svc.cloud.failure = remote == 'unknown'
    before = svc.control.read()[1]
    def forbidden(*args):
        pytest.fail('No liberar un proceso vivo o desconocido')
    result = reconcile(svc.control, svc.cloud, forbidden)
    assert result['runs'][0]['verification']['state'] == remote
    assert svc.control.read()[1] == before
    with pytest.raises(Conflict):
        start(execution)


def test_terminal_record_preserves_completion_time_and_unrelated_lock(execution):
    svc, _, _, factory, _ = execution
    run = start(execution)
    old = factory().__enter__()
    svc.control.patch(run['id'], {'worker':'ended','lock_generation':str(old.lock_generacion),'status':'running'})
    old.__exit__()
    live = factory().__enter__()
    completed = '2026-11-13T10:28:10.004012Z'
    svc.cloud.rows = [{'name':'ended','completionTime':completed,'failedCount':1}]
    doc = reconcile(svc.control, svc.cloud, svc.unlock)
    assert doc['runs'][0]['status'] == 'interrupted'
    assert doc['runs'][0]['finished'] == completed
    assert doc['runs'][0]['job_result'] == 'failed'
    assert doc['runs'][0]['persisted'] is not True
    live.asegurar_bloqueo()
    with pytest.raises(Conflict):
        start(execution)
    live.__exit__()


def test_banner_uses_remote_evidence_and_hides_technical_id_in_detail(execution):
    from fastapi.testclient import TestClient
    from metro.web import app
    svc = execution[0]
    run = start(execution)
    client = TestClient(app)
    html = client.get('/v0.6/ejecuciones').text
    assert 'Verificando el estado de una actualización anterior' in html
    assert 'Hay una ejecución incompatible en curso' not in html
    assert '<summary>Detalle técnico</summary>' in html
    assert 'Ver seguimiento' in html and 'Carolina' in html
    svc.cloud.rows = [{'name':'active'}]
    svc.cloud._observations.clear()
    data = client.get('/v0.6/ejecuciones/estado').json()
    assert 'Actualización en curso' in data['notice_html']
    assert 'Cloud Run confirma que el Job está activo.' in data['notice_html']
    assert run['id'] not in data['notice_html'].split('Ver seguimiento')[0].split('href=')[0]


def test_idle_maintenance_racing_worker_claim_never_overwrites_control(versioned, monkeypatch):
    client, _, _ = versioned
    control = ControlGCS('synthetic', client=client)
    control.change(lambda d: d.update(catalog_updated='old'))
    original = storage.Blob.upload_from_string
    raced = []
    def claim(blob, *args, **kw):
        if not raced:
            raced.append(True)
            reserve(ControlGCS('synthetic', client=client), str(uuid4()), [])
        return original(blob, *args, **kw)
    monkeypatch.setattr(storage.Blob, 'upload_from_string', claim)
    control.change(lambda d: d.update(catalog_updated='maintenance'), idle_only=True)
    doc, _ = control.read()
    assert doc['catalog_updated'] == 'old'
    assert len(doc['runs']) == 1 and doc['runs'][0]['status'] == 'launching'


def test_original_worker_failure_is_reproduced_when_web_changes_generation(versioned):
    client, _, _ = versioned
    current = ControlGCS('synthetic', client=client)
    run, _ = reserve(current, str(uuid4()), [])
    current.patch(run['id'], {'status':'running','worker':'synthetic-worker'})
    class PreviousAdapter(ControlGCS):
        @property
        def blob(self):
            if not hasattr(self, '_pinned'):
                self._pinned = super().blob
            return self._pinned
    worker = PreviousAdapter('synthetic', client=client)
    worker.read()
    # Same durable metadata write made by the former web reconciler during capture.
    current.patch(run['id'], {'reconciled':now()})
    with pytest.raises(Conflict):
        worker.patch(run['id'], {'phase':'heartbeat'}, worker='synthetic-worker')
    assert current.get(run['id'])['status'] == 'running'
    # Repaired adapter sees the competing generation and can record its heartbeat.
    current.patch(run['id'], {'phase':'heartbeat'}, worker='synthetic-worker')
    assert current.get(run['id'])['phase'] == 'heartbeat'
