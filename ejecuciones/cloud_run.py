"""API Cloud Run limitada al proyecto, región y Job configurados por el operador."""
import os
import re
import copy
import time
import threading
from functools import lru_cache
import google.auth
from google.auth.transport.requests import AuthorizedSession

PARENT = 'projects/radar-inmobiliario-co/locations/us-central1'


class CloudRun:
    def __init__(self, job=None, session=None):
        from .entorno import settings
        self.environment = settings()
        self.job = job or os.getenv('RADAR_EXECUTION_JOB', 'radar-manual')
        if not re.fullmatch(r'radar-manual(?:-review)?', self.job):
            raise ValueError('Job manual no permitido')
        self.name = self.environment.parent + '/jobs/' + self.job
        if session is None:
            credentials, _ = google.auth.default(scopes=['https://www.googleapis.com/auth/cloud-platform'])
            session = AuthorizedSession(credentials)
        self.session = session
        self._observations = {}
        self._observation_lock = threading.Lock()

    def request(self, method, path, **kwargs):
        # requests/AuthorizedSession no reintenta POST de infraestructura por timeout.
        response = self.session.request(method, 'https://run.googleapis.com/v2/' + path, timeout=12, **kwargs)
        response.raise_for_status()
        return response.json()

    def launch(self, run_id):
        from .control import valid_id
        if not valid_id(run_id):
            raise ValueError('Identificador inválido')
        op = self.request('POST', self.name + ':run', json={'overrides': {'containerOverrides': [
            {'args': ['--execution', run_id], 'env': [{'name': 'RADAR_RUN_ID', 'value': run_id}]}], 'taskCount': 1}})
        return op.get('name')

    def observe(self, run, force=False):
        """Caché de lectura, nunca mecanismo durable de ejecución ni permiso para lanzar."""
        from .control import now, age
        key = (run['id'], run.get('worker'))
        with self._observation_lock:
            cached = self._observations.get(key)
            if cached and not force and time.monotonic() - cached[0] < 60:
                return copy.deepcopy(cached[1])
            result = {'state': 'unknown', 'checked': now(), 'finished': None, 'job_result': None}
            try:
                if run.get('worker'):
                    try:
                        executions = [self.execution(run['worker'])]
                    except Exception as exc:
                        if getattr(getattr(exc, 'response', None), 'status_code', None) != 404 or age(run['updated']) < 600:
                            raise
                        executions = self.executions(run['id'])
                else:
                    executions = self.executions(run['id'])
                if any(not terminal(e) for e in executions):
                    result['state'] = 'active'
                elif executions:
                    result['state'] = 'terminal'
                    result['finished'] = max((e.get('completionTime') for e in executions if e.get('completionTime')), default=None)
                    result['job_result'] = 'failed' if any(e.get('failedCount', 0) or any(c.get('type') == 'Completed' and (c.get('state') == 'CONDITION_FAILED' or c.get('status') == 'False') for c in e.get('conditions', [])) for e in executions) else 'finished'
                else:
                    result['state'] = 'missing'
            except Exception:
                # No copiar mensajes/credenciales del SDK. Un error de lectura nunca libera.
                result['reason'] = 'remote_lookup_failed'
            if len(self._observations) >= 32 and key not in self._observations:
                self._observations.pop(next(iter(self._observations)))
            self._observations[key] = (time.monotonic(), result)
            return copy.deepcopy(result)

    def execution(self, worker):
        if not isinstance(worker, str) or not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,127}', worker):
            raise ValueError('Referencia de ejecución inválida')
        return self.request('GET', self.name + '/executions/' + worker)

    def executions(self, run_id):
        result, token = [], None
        while True:
            page = self.request('GET', self.name + '/executions', params={'pageSize': 100, **({'pageToken': token} if token else {})})
            for e in page.get('executions', []):
                env = [v for c in e.get('template', {}).get('containers', []) for v in c.get('env', [])]
                if any(v.get('name') == 'RADAR_RUN_ID' and v.get('value') == run_id for v in env):
                    result.append(e)
            token = page.get('nextPageToken')
            if not token:
                return result



def terminal(execution):
    return bool(execution.get('completionTime')) or any(
        c.get('type') == 'Completed' and c.get('state') in {'CONDITION_SUCCEEDED', 'CONDITION_FAILED'}
        for c in execution.get('conditions', []))


@lru_cache(maxsize=2)
def cloud_configurado(job):
    return CloudRun(job)


def reconcile(control, cloud, unlock=None, force=False):
    from .control import ACTIVE, age, now
    doc = control.read()[0]
    r = next((r for r in doc['runs'] if r['status'] in ACTIVE), None)
    if not r:
        return doc
    if cloud.job != r['job']:
        cloud = cloud_configurado(r['job'])
    observation = cloud.observe(r, force=force)
    # Observación solo en la respuesta. La web no modifica el control de un Job vivo:
    # compatible también con el ejecutor anterior que conservaba un Blob fijado.
    r['verification'] = observation
    if observation['state'] in {'active', 'unknown'}:
        r['reconciliation_note'] = ('Sin actualización reciente del trabajador; Cloud Run confirma que el Job sigue activo.'
            if observation['state'] == 'active' and age(r['updated']) > 120 else
            ('No se pudo confirmar el estado remoto. Se conserva la protección hasta verificarlo.' if observation['state'] == 'unknown' else None))
        return doc
    if observation['state'] == 'missing' and age(r['created']) < 600:
        r['reconciliation_note'] = 'Verificando el lanzamiento. Todavía no aparece una ejecución confirmada en Cloud Run.'
        return doc
    observed_worker = r.get('worker')
    def fence(d):
        current = next(x for x in d['runs'] if x['id'] == r['id'])
        if current['status'] not in ACTIVE or current.get('worker') != observed_worker or current['updated'] != r['updated']:
            return None
        current.update(status='reconciling', phase='Reconciliando cierre y bloqueo', verification=observation)
        return current
    closed = control.change(fence)
    if closed is None:
        return control.read()[0]
    try:
        if unlock and (closed.get('lock_generation') or closed.get('lock_token')):
            unlock(closed.get('lock_generation'), closed.get('lock_token'))
    except Exception:
        # Sigue reservado, sin convertir un error de limpieza en permiso para capturar.
        result = control.read()[0]
        current = next(x for x in result['runs'] if x['id'] == r['id'])
        current['verification'] = dict(observation, state='unknown')
        current['reconciliation_note'] = 'El Job terminó, pero el cierre del bloqueo requiere otra comprobación. Se conserva la protección.'
        return result
    def finish(d):
        current = next(x for x in d['runs'] if x['id'] == r['id'])
        if current['status'] != 'reconciling' or current.get('worker') != observed_worker:
            return
        finished = observation.get('finished') or now()
        current.update(status='interrupted', phase='Job terminado sin cierre confirmado', finished=finished, updated=now(),
                       reconciled=now(), verification=observation, job_result=observation.get('job_result'),
                       reconciliation_note=None,
                       error='Cloud Run terminó sin confirmar el cierre y el guardado final. Se conserva el último snapshot confirmado.')
        for b in current['searches']:
            if b['status'] in {'running', 'extracted'}:
                b.update(status='interrupted', finished=finished)
            elif b['status'] == 'pending':
                b.update(status='not_run', error='No ejecutada por interrupción de infraestructura')
    control.change(finish)
    return control.read()[0]
