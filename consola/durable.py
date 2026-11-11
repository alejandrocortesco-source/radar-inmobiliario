"""Frontera durable web: snapshot confirmado antes de emitir la respuesta.

Solo para el servicio Cloud Run. La exclusión remota es compartida con job.py;
no depende de max-instances ni de recibir SIGTERM. Las tareas ASGI se completan
antes del checkpoint y antes de responder (incluido Gemini manual).
"""
import asyncio
import hashlib
import logging
import os
import tempfile
from pathlib import Path

from google.api_core.exceptions import PreconditionFailed
from starlette.concurrency import run_in_threadpool
from starlette.responses import HTMLResponse
from wasi.durable import ARCHIVOS, EstadoGCS

RUTAS = {'METRO_DB': 'metro.sqlite', 'WASI_DB': 'wasi.sqlite',
         'FINCARAIZ_DB': 'fincaraiz.sqlite', 'RADAR_CRM_DB': 'metro-consola.sqlite'}


def firma(carpeta):
    result = {}
    for nombre in ARCHIVOS:
        for sufijo in ('', '-wal'):
            ruta = Path(carpeta) / (nombre + sufijo)
            if ruta.is_file():
                result[nombre + sufijo] = hashlib.sha256(ruta.read_bytes()).hexdigest()
    return result


class WebDurable:
    def __init__(self, app, estado_factory=None, data_dir=None):
        self.app = app
        self.local = asyncio.Lock()
        self.factory = estado_factory or (lambda: EstadoGCS(
            os.environ['RADAR_STATE_BUCKET'], os.getenv('RADAR_STATE_OBJECT', 'radar/state.tar.gz')))
        self.data_dir = data_dir or os.getenv('RADAR_DATA_DIR', '/data')

    async def __call__(self, scope, receive, send):
        path = scope.get('path', '')
        if scope['type'] != 'http' or path == '/health' or path.startswith(('/v0.4/static/', '/consola/static/')):
            return await self.app(scope, receive, send)
        async with self.local:
            estado = None
            adquirido = False
            error = None
            mensajes = []
            anteriores = {k: os.environ.get(k) for k in RUTAS}
            try:
                Path(self.data_dir).mkdir(parents=True, exist_ok=True)
                estado = self.factory()
                await run_in_threadpool(estado.__enter__)
                adquirido = True
                with tempfile.TemporaryDirectory(prefix='request-', dir=self.data_dir) as carpeta:
                    await run_in_threadpool(estado.cargar, carpeta)
                    for key, nombre in RUTAS.items():
                        os.environ[key] = str(Path(carpeta) / nombre)
                    antes = await run_in_threadpool(firma, carpeta)

                    async def retener(message):
                        mensajes.append(message)

                    # Incluye BackgroundTasks: no hay trabajo pendiente al responder.
                    await self.app(scope, receive, retener)
                    if await run_in_threadpool(firma, carpeta) != antes:
                        await run_in_threadpool(estado.guardar, carpeta)
            except PreconditionFailed:
                error = 'Radar está ocupado con otra operación o una captura. Intenta de nuevo en unos minutos.'
            except Exception as exc:
                logging.getLogger(__name__).error('durable_request_failed type=%s', type(exc).__name__)
                error = 'No se pudo confirmar el almacenamiento durable. Vuelve a consultar antes de repetir una operación.'
            finally:
                for key, value in anteriores.items():
                    if value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = value
                if adquirido:
                    try:
                        await run_in_threadpool(estado.__exit__, None, None, None)
                    except Exception as exc:
                        logging.getLogger(__name__).error('durable_unlock_failed type=%s', type(exc).__name__)
                        error = 'Almacenamiento temporalmente ocupado; requiere revisar el bloqueo durable.'
            if error:
                response = HTMLResponse('<!doctype html><html lang="es"><meta charset="utf-8">'
                    '<meta name="viewport" content="width=device-width,initial-scale=1">'
                    '<title>Radar temporalmente ocupado</title><main style="max-width:42rem;margin:10vh auto;padding:1rem;font:1.1rem system-ui">'
                    '<h1>Radar temporalmente ocupado</h1><p>' + error + '</p>'
                    '<p><a href="/v0.6/">Volver al inicio</a></p></main></html>',
                    status_code=503, headers={'Retry-After': '30', 'Cache-Control': 'no-store'})
                return await response(scope, receive, send)
            for message in mensajes:
                await send(message)
