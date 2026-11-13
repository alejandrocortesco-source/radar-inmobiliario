"""API Cloud Run limitada al proyecto, región y Job configurados por el operador."""
import os
import re
import google.auth
from google.auth.transport.requests import AuthorizedSession

PARENT = 'projects/radar-inmobiliario-co/locations/us-central1'


class CloudRun:
    def __init__(self, job=None, session=None):
        self.job = job or os.getenv('RADAR_EXECUTION_JOB', 'radar-manual')
        if not re.fullmatch(r'radar-manual(?:-review)?', self.job):
            raise ValueError('Job manual no permitido')
        self.name = PARENT + '/jobs/' + self.job
        if session is None:
            credentials, _ = google.auth.default(scopes=['https://www.googleapis.com/auth/cloud-platform'])
            session = AuthorizedSession(credentials)
        self.session = session

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


def reconcile(control, cloud, unlock=None):
    from .control import ACTIVE, age, now
    doc = control.read()[0]
    r = next((r for r in doc['runs'] if r['status'] in ACTIVE), None)
    if not r or (r.get('reconciled') and age(r['reconciled']) < 60):
        return doc
    # Reserva CAS limita la consulta remota a una por minuto, entre instancias.
    claimed = False
    def claim(d):
        nonlocal claimed
        claimed = False
        current = next(x for x in d['runs'] if x['id'] == r['id'])
        if current['status'] in ACTIVE and (not current.get('reconciled') or age(current['reconciled']) >= 60):
            current['reconciled'] = now()
            claimed = True
    control.change(claim)
    if not claimed:
        return control.read()[0]
    try:
        if isinstance(cloud, CloudRun) and cloud.job != r['job']:
            cloud = CloudRun(r['job'])
        if r.get('worker'):
            try:
                executions = [cloud.execution(r['worker'])]
            except Exception as exc:
                # Una ejecución eliminada/expirada no deja el control activo para siempre.
                if getattr(getattr(exc, 'response', None), 'status_code', None) != 404 or age(r['updated']) < 600:
                    raise
                executions = cloud.executions(r['id'])
        else:
            executions = cloud.executions(r['id'])
        if any(not terminal(e) for e in executions):
            # Falta de heartbeat no implica fallo si Cloud Run aún lo tiene activo.
            def note(d):
                current = next(x for x in d['runs'] if x['id'] == r['id'])
                current['reconciliation_note'] = ('Sin actualización reciente del trabajador. Cloud Run confirma que el Job sigue activo.' if age(current['updated']) > 120 else None)
            control.change(note)
            return control.read()[0]
        resolved = bool(executions)
        if not resolved and age(r['created']) < 600:
            return control.read()[0]
        # Sin Job después de 10 min: cerrar/fencear la reserva; un Job tardío no podrá reclamarla.
        # No relanzar una solicitud ambigua. El próximo clic requiere un ID nuevo.
        observed_worker = r.get('worker')
        def fence(d):
            current = next(x for x in d['runs'] if x['id'] == r['id'])
            if current['status'] not in ACTIVE or current.get('worker') != observed_worker or current['updated'] != r['updated']:
                return None  # Un trabajador reclamó la reserva después de consultar Cloud Run.
            current.update(status='reconciling', phase='Reconciliando cierre y bloqueo')
            return current
        closed = control.change(fence)
        if closed is None:
            return control.read()[0]
        # La reserva está revocada antes de limpiar; un Job tardío no puede reclamarla.
        if unlock and (closed.get('lock_generation') or closed.get('lock_token')):
            unlock(closed.get('lock_generation'), closed.get('lock_token'))
        def finish(d):
            current = next(x for x in d['runs'] if x['id'] == r['id'])
            if current['status'] != 'reconciling' or current.get('worker') != observed_worker:
                return
            current.update(status='interrupted', phase='Job terminado sin cierre confirmado', finished=now(), updated=now(),
                           error='Infraestructura: ejecución terminada o lanzamiento no confirmado; se conserva el último snapshot confirmado.')
            for b in current['searches']:
                if b['status'] in {'running', 'extracted'}:
                    b.update(status='interrupted', finished=now())
                elif b['status'] == 'pending':
                    b.update(status='not_run', error='No ejecutada por interrupción de infraestructura')
        control.change(finish)
    except Exception:
        # Fallo de consulta no prueba fallo del Job ni permite liberar su bloqueo.
        def note(d):
            current = next(x for x in d['runs'] if x['id'] == r['id'])
            current['reconciliation_note'] = 'No se pudo consultar Cloud Run. Se conserva la reserva hasta reconciliar; el Job puede seguir activo.'
        control.change(note)
    return control.read()[0]
