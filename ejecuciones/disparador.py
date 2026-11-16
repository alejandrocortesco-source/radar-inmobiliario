"""Disparador IAM privado; OIDC verificado además dentro de la aplicación."""
import os
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool
from google.oauth2.id_token import verify_oauth2_token
from google.auth.transport.requests import Request as GoogleRequest
from .servicio import ServicioEjecuciones
from .programacion import Programacion
from .scheduler import Scheduler

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)


def authenticate(header):
    target = os.environ.get('RADAR_SCHEDULE_TARGET')
    if not target or not header or not header.startswith('Bearer '):
        raise ValueError('Credencial requerida')
    claims = verify_oauth2_token(header[7:], GoogleRequest(), audience=target)
    if claims.get('email') != 'radar-scheduler@radar-inmobiliario-co.iam.gserviceaccount.com' or claims.get('email_verified') is not True:
        raise ValueError('Identidad no permitida')


@app.get('/health')
def health():
    return {'ok':True}


@app.post('/trigger')
async def trigger(request: Request):
    try:
        await run_in_threadpool(authenticate, request.headers.get('authorization'))
    except Exception:
        return JSONResponse({'detail':'No autorizado'}, 401)
    try:
        body = await request.body()
        if len(body) > 1024:
            raise ValueError('Solicitud inválida')
        import json
        payload = json.loads(body)
        job = request.headers.get('x-cloudscheduler-jobname')
        date = request.headers.get('x-cloudscheduler-scheduletime', '')
        revision = payload['revision']
        if not isinstance(revision, str) or len(revision) > 40:
            raise ValueError('Revisión inválida')
        run = await run_in_threadpool(lambda: Programacion(ServicioEjecuciones(), Scheduler()).deliver(job, revision, date))
        return JSONResponse({'id':run['id'], 'status':run['status']}, 202)
    except (ValueError, KeyError, TypeError):
        return JSONResponse({'detail':'Ocurrencia inválida'}, 422)
    except Exception:
        return JSONResponse({'detail':'No se confirmó la reserva durable'}, 503)
