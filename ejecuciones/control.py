"""Registro acotado en GCS. CAS evita actualizaciones perdidas entre web y Job."""
import copy
import json
import os
import time
from datetime import datetime, timezone
from uuid import UUID
from google.api_core.exceptions import NotFound, PreconditionFailed

ACTIVE = {'launching', 'uncertain', 'queued', 'running', 'saving', 'reconciling'}
TERMINAL = {'completed', 'partial', 'failed', 'interrupted', 'skipped'}
SOURCES = {'metrocuadrado', 'wasi', 'fincaraiz'}
MAX_HISTORY = 100
RETENTION_DAYS = 30
MAX_SELECTION = 100

class Conflict(ValueError):
    pass

class IntegrityError(RuntimeError):
    pass


def now():
    return datetime.now(timezone.utc).isoformat()


def age(value):
    return max(0, (datetime.now(timezone.utc) - datetime.fromisoformat(value)).total_seconds())


def valid_id(value):
    try:
        return str(UUID(value)) == value
    except (ValueError, TypeError, AttributeError):
        return False


def empty():
    return {'version': 1, 'searches': [], 'catalog_updated': None, 'runs': []}


def prune(doc):
    terminal = sorted((r for r in doc['runs'] if r['status'] in TERMINAL
                       and age(r.get('finished') or r['created']) < RETENTION_DAYS * 86400),
                      key=lambda r: r['created'], reverse=True)[:MAX_HISTORY]
    doc['runs'] = [r for r in doc['runs'] if r['status'] in ACTIVE] + terminal


class ControlGCS:
    def __init__(self, bucket=None, objeto=None, client=None):
        if client is None:
            from google.cloud import storage
            client = storage.Client()
        self.bucket = client.bucket(bucket or os.environ['RADAR_STATE_BUCKET'])
        self.objeto = objeto or os.getenv('RADAR_CONTROL_OBJECT', 'radar/executions/control.json')

    @property
    def blob(self):
        # Un handle reutilizado conserva ?generation=... incluso al hacer reload.
        return self.bucket.blob(self.objeto)

    def read(self):
        blob = self.blob
        try:
            blob.reload(timeout=10)
            generation = int(blob.generation)
            raw = blob.download_as_bytes(if_generation_match=generation, timeout=15)
        except NotFound:
            return empty(), 0
        doc = json.loads(raw)
        if doc.get('version') != 1 or not isinstance(doc.get('runs'), list):
            raise IntegrityError('Registro de ejecuciones incompatible')
        return doc, generation

    def change(self, mutate, *, idle_only=False):
        for attempt in range(8):
            try:
                doc, generation = self.read()
                if idle_only and any(r['status'] in ACTIVE for r in doc['runs']):
                    return None
                before = copy.deepcopy(doc)
                result = mutate(doc)
                prune(doc)
                if doc == before:
                    return copy.deepcopy(result)
                raw = json.dumps(doc, ensure_ascii=False, separators=(',', ':'))
                while len(raw.encode()) > 2_000_000:
                    removable = [r for r in doc['runs'] if r['status'] in TERMINAL]
                    if not removable:
                        raise IntegrityError('Registro de mantenimiento demasiado grande')
                    doc['runs'].remove(min(removable, key=lambda r:r['created']))
                    raw = json.dumps(doc, ensure_ascii=False, separators=(',', ':'))
                self.blob.upload_from_string(raw, content_type='application/json',
                                             if_generation_match=generation, timeout=15)
                return copy.deepcopy(result)
            except PreconditionFailed:
                if attempt == 7:
                    raise Conflict('Otra operación está actualizando el seguimiento. Vuelve a consultar.') from None
                time.sleep(.02 * (attempt + 1))

    def get(self, run_id):
        return next((r for r in self.read()[0]['runs'] if r['id'] == run_id), None)

    def patch(self, run_id, values, worker=None):
        def mutate(doc):
            r = next(r for r in doc['runs'] if r['id'] == run_id)
            if r['status'] not in ACTIVE or (worker and (r.get('worker') != worker or r['status'] == 'reconciling')):
                raise IntegrityError('La ejecución perdió su autorización de escritura')
            r.update(values, updated=now())
            return r
        return self.change(mutate)


def projection(repo, folder=None):
    rows = []
    for b in repo.listar():
        if b['fuente'] not in SOURCES:
            continue
        summary = b['url']
        if b['fuente'] == 'wasi':
            config = repo.configuracion_wasi(b['id_busqueda']) or {}
            from catalogo.fuentes.wasi import LABELS
            labels = config.get('etiquetas', {})
            summary = ' · '.join(f"{LABELS.get(k, k)}: {labels.get(k) or v}" for k, v in config.get('filtros', {}).items() if v) or b['url']
        rows.append({k: b[k] for k in ('fuente', 'id_busqueda', 'nombre', 'url', 'activa')} | {'summary': summary[:700]})
    if folder is not None:
        from .mediciones import previous
        for row in rows:
            row['legacy_last'], row['baseline'] = previous(folder, row)
    return rows


def select(rows, keys):
    if not isinstance(keys, list) or not 1 <= len(keys) <= MAX_SELECTION:
        raise ValueError('Selecciona entre 1 y 100 búsquedas activas.')
    if any(not isinstance(k, list) or len(k) != 2 or any(not isinstance(v, str) for v in k) for k in keys):
        raise ValueError('Selección inválida.')
    unique = list(dict.fromkeys(tuple(k) for k in keys))
    lookup = {(b['fuente'], b['id_busqueda']): b for b in rows}
    if any(k not in lookup or not lookup[k]['activa'] for k in unique):
        raise ValueError('Una búsqueda ya no existe o está inactiva. Recarga y revisa la selección.')
    return [lookup[k] for k in unique]


def reserve(control, request_id, selected, *, automatic=None):
    if not valid_id(request_id):
        raise ValueError('Identificador de solicitud inválido. Recarga la página.')
    def mutate(doc):
        prior = next((r for r in doc['runs'] if r['request_id'] == request_id), None)
        keys = [(b['fuente'], b['id_busqueda']) for b in selected]
        if automatic and not prior and request_id in doc.get('schedule_receipts', {}):
            return {'id': request_id, 'status': 'skipped', 'error': 'Ocurrencia ya reservada; informe fuera de retención.'}, False
        if prior:
            if automatic is None and [(b['fuente'], b['id_busqueda']) for b in prior['searches']] != keys:
                raise Conflict('Esta solicitud ya se utilizó para otra selección.')
            return prior, False
        active = next((r for r in doc['runs'] if r['status'] in ACTIVE), None)
        if active and automatic is None:
            raise Conflict('Ya existe una ejecución incompatible: ' + active['id'] + '. Consulta su seguimiento.')
        r = {'id': request_id, 'request_id': request_id, 'created': now(), 'updated': now(),
             'started': None, 'finished': None, 'status': 'launching', 'phase': 'Solicitando Job',
             'persisted': None, 'snapshot_generation': None, 'worker': None, 'operation': None,
             'job': os.getenv('RADAR_EXECUTION_JOB', 'radar-manual'), 'reconciled': None, 'error': None,
             'searches': [dict({k:v for k,v in b.items() if k not in {'baseline','legacy_last'}}, status='pending', started=None, finished=None, duration=None,
                               processed=None, new=None, changed=None, unchanged=None, error=None) for b in selected]}
        r['origin'] = 'automatic' if automatic else 'manual'
        if automatic:
            from .programacion import occurrence_reason
            reason = occurrence_reason(doc, automatic) or ('Omitida por ejecución en curso.' if active else None)
            r.update(scheduled_at=automatic['scheduled_at'], schedule_revision=automatic['revision'], scheduler_job=automatic['job'], schedule_warning=automatic.get('warning'))
            reason = reason or automatic.get('reason')
            if reason:
                r.update(status='skipped', phase=reason, error=reason, finished=now())
        doc['runs'].append(r)
        if automatic:
            receipts = doc.setdefault('schedule_receipts', {})
            receipts[request_id] = now()
            for key, value in list(receipts.items()):
                if age(value) > 2 * 86400:
                    del receipts[key]
        return r, r['status'] == 'launching'
    return control.change(mutate)


def measurements(doc, search):
    baseline = next((b.get('baseline', []) for b in doc.get('searches', []) if (b['fuente'],b['id_busqueda']) == (search['fuente'],search['id_busqueda'])), [])
    samples = baseline + [b for r in doc['runs'] if r.get('persisted') is True
               for b in r['searches'] if (b['fuente'], b['id_busqueda']) == (search['fuente'], search['id_busqueda'])
               and b['status'] == 'completed' and b.get('duration') is not None]
    samples = list({str(b.get('technical_run') or b.get('finished')): b for b in samples}.values())
    samples.sort(key=lambda b: b.get('finished') or '', reverse=True)
    recent = samples[:5]
    if not recent:
        return {'load': 'Por estimar', 'range': None, 'last': None}
    seconds = max(b['duration'] for b in recent)
    volume = max((b.get('processed') or 0) for b in recent)
    category = 'Pesada' if seconds >= 900 or volume >= 500 else ('Moderada' if seconds >= 180 or volume >= 100 else 'Liviana')
    estimate = [min(b['duration'] for b in recent) * .75, max(b['duration'] for b in recent) * 1.5] if len(recent) >= 3 else None
    return {'load': category, 'range': estimate, 'last': recent[0]}
