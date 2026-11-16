"""API Scheduler con destino fijo, OIDC y un único recurso administrado."""
import base64
import json
import os
import google.auth
from google.auth.transport.requests import AuthorizedSession
from .programacion import cron
from .cloud_run import PARENT


class Scheduler:
    def __init__(self, session=None):
        from .entorno import settings
        self.environment = settings()
        self.parent = self.environment.parent
        self.name = self.parent + '/jobs/radar-weekly-review'
        self.url = os.environ.get('RADAR_SCHEDULE_TARGET', '')
        self.account = self.environment.caller
        if session is None:
            credentials, _ = google.auth.default(scopes=['https://www.googleapis.com/auth/cloud-platform'])
            session = AuthorizedSession(credentials)
        self.session = session

    def request(self, method, path='', **kw):
        response = self.session.request(method, 'https://cloudscheduler.googleapis.com/v1/'+self.name+path, timeout=12, **kw)
        if response.status_code == 404 and method == 'GET':
            return None
        response.raise_for_status()
        return response.json() if response.content else {}

    def get(self):
        return self.request('GET')

    def payload(self, cfg):
        if not self.url.startswith('https://radar-schedule-review-') or not self.url.endswith('.run.app'):
            raise ValueError('Destino privado de programación no configurado.')
        return dict(name=self.name, description='Radar Central: calendario general de revisión', schedule=cron(cfg), timeZone='America/Bogota',
                    attemptDeadline='120s', retryConfig=dict(retryCount=2, maxRetryDuration='600s', minBackoffDuration='30s', maxBackoffDuration='120s'),
                    httpTarget=dict(uri=self.url+'/trigger', httpMethod='POST', headers={'Content-Type':'application/json'},
                                    body=base64.b64encode(json.dumps({'revision':cfg['revision']}).encode()).decode(),
                                    oidcToken=dict(serviceAccountEmail=self.account, audience=self.url)))

    def matches(self, remote, cfg):
        expected = self.payload(cfg)
        target = remote.get('httpTarget', {})
        return (remote.get('schedule') == expected['schedule'] and remote.get('timeZone') == 'America/Bogota'
                and all(target.get(k) == expected['httpTarget'][k] for k in ('uri','httpMethod','body','oidcToken')))

    def sync(self, cfg):
        remote = self.get()
        if not cfg['enabled'] and remote is None:
            return  # Guardar desactivada no crea ni ejecuta recursos.
        if remote and remote.get('state') == 'ENABLED':
            self.request('POST', ':pause', json={})
        if cfg['days'] and cfg['keys']:
            payload = self.payload(cfg)
            if remote:
                self.request('PATCH', params={'updateMask':'description,schedule,timeZone,httpTarget,retryConfig,attemptDeadline'}, json=payload)
            else:
                # Se crea solo ante Activar explícito; el gate CAS permanece cerrado.
                response = self.session.request('POST', 'https://cloudscheduler.googleapis.com/v1/'+self.parent+'/jobs', json=payload, timeout=12)
                response.raise_for_status()
            remote = self.get()
            if not self.matches(remote or {}, cfg):
                raise RuntimeError('Scheduler no confirmó la configuración')
        if cfg['enabled']:
            remote = self.get()
            if remote.get('state') == 'PAUSED':
                self.request('POST', ':resume', json={})
        remote = self.get()
        if remote and remote.get('state') != ('ENABLED' if cfg['enabled'] else 'PAUSED'):
            raise RuntimeError('Scheduler no confirmó el estado')
