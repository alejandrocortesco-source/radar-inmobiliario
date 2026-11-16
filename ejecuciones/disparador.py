"""Disparador IAM privado; OIDC verificado además dentro de la aplicación."""
import os
import json
import logging
from uuid import uuid4
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool
from google.oauth2.id_token import verify_oauth2_token
from google.auth.transport.requests import Request as GoogleRequest
from .servicio import ServicioEjecuciones
from .programacion import Programacion, InvalidOccurrence, scheduler_identity, scheduled_time
from .scheduler import Scheduler

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)


def authenticate(header):
    from .entorno import settings
    environment = settings()
    target = os.environ.get('RADAR_SCHEDULE_TARGET')
    if not target or not header or not header.startswith('Bearer '):
        raise ValueError('Credencial requerida')
    claims = verify_oauth2_token(header[7:], GoogleRequest(), audience=target)
    if claims.get('email') != environment.caller or claims.get('email_verified') is not True:
        raise ValueError('Identidad no permitida')


@app.get('/health')
def health():
    return {'ok':True}


@app.post('/trigger')
async def trigger(request: Request):
    diagnostic = {'event': 'scheduler_request', 'request_id': str(uuid4())}
    def record(code, accepted=False):
        logger.log(logging.INFO if accepted else logging.WARNING,
                   json.dumps(dict(diagnostic, code=code), ensure_ascii=True))
    try:
        await run_in_threadpool(authenticate, request.headers.get('authorization'))
    except Exception:
        record('authentication_failed')
        return JSONResponse({'detail':'No autorizado'}, 401)
    try:
        body = await request.body()
        if len(body) > 1024:
            raise InvalidOccurrence('body_too_large')
        try:
            payload = json.loads(body)
        except (ValueError, UnicodeError):
            raise InvalidOccurrence('invalid_json') from None
        if not isinstance(payload, dict) or 'revision' not in payload:
            raise InvalidOccurrence('missing_revision')
        revision = payload['revision']
        if not isinstance(revision, str) or not revision or len(revision) > 40:
            raise InvalidOccurrence('invalid_revision')
        scheduler = Scheduler()
        job, form = scheduler_identity(request.headers.get('x-cloudscheduler-jobname'), scheduler.name)
        diagnostic.update(job_format=form, canonical_job=job)
        date = scheduled_time(request.headers.get('x-cloudscheduler-scheduletime'))
        diagnostic['scheduled_at'] = date
        run = await run_in_threadpool(lambda: Programacion(ServicioEjecuciones(), scheduler).deliver(job, revision, date))
        diagnostic['run_id'] = run['id']
        record('durable_' + run['status'], accepted=True)
        response = {'id':run['id'], 'status':run['status']}
        if 'occurrences' in run:
            response['occurrences'] = [{'id':r['id'], 'status':r['status']} for r in run['occurrences']]
            diagnostic['occurrences'] = len(run['occurrences'])
        return JSONResponse(response, 202)
    except (ValueError, KeyError, TypeError) as exc:
        code = exc.code if isinstance(exc, InvalidOccurrence) else 'occurrence_validation_failed'
        record(code)
        return JSONResponse({'detail':'Ocurrencia inválida', 'code':code, 'request_id':diagnostic['request_id']}, 422)
    except Exception:
        record('durable_reservation_unconfirmed')
        return JSONResponse({'detail':'No se confirmó la reserva durable'}, 503)
