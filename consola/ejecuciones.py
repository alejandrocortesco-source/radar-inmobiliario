"""Página y API de control: no consultan el catálogo SQLite durante una captura."""
import json
import os
from uuid import uuid4
from fastapi import APIRouter, Request
from starlette.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse, RedirectResponse
from .v06 import templates
from ejecuciones.control import ACTIVE, Conflict, measurements, age, valid_id
from ejecuciones.servicio import ServicioEjecuciones

PATH = '/v0.6/ejecuciones'
LABELS = {'reconciling': 'Reconciliando cierre', 'launching': 'Solicitando Job', 'uncertain': 'Lanzamiento por confirmar', 'queued': 'Esperando Job',
          'running': 'En ejecución', 'saving': 'Confirmando guardado', 'completed': 'Completada', 'partial': 'Parcial',
          'failed': 'Fallida', 'interrupted': 'Interrumpida', 'pending': 'Pendiente', 'not_run': 'No ejecutada',
          'extracted': 'Extracción terminada; guardado final pendiente'}


def duration(value):
    if value is None:
        return 'No disponible'
    minutes = max(0, round(value / 60))
    return 'Menos de 1 min' if minutes < 1 else f'{minutes} min'


def remaining(doc, run):
    if not run or run['status'] not in ACTIVE:
        return None
    low = high = 0
    for b in run['searches']:
        if b['status'] not in {'pending', 'running'}:
            continue
        estimate = measurements(doc, b)['range']
        if not estimate:
            return 'Tiempo restante: por estimar. Se requieren tres ejecuciones completas de cada búsqueda pendiente.'
        spent = age(b['started']) if b.get('started') else 0
        low += max(0, estimate[0] - spent)
        high += max(0, estimate[1] - spent)
    if high <= 0:
        return 'La ejecución superó el rango orientativo; esperando la confirmación del portal y del guardado.'
    return f'Tiempo restante orientativo: {duration(low)} a {duration(high)}. Depende del portal y del volumen.'


def context(doc, requested=None):
    runs = sorted(doc['runs'], key=lambda r: r['created'], reverse=True)
    active = next((r for r in runs if r['status'] in ACTIVE), None)
    run = next((r for r in runs if r['id'] == requested), None) if requested else (active or (runs[0] if runs else None))
    searches = []
    for b in doc['searches']:
        history = next((s for r in runs for s in r['searches'] if (s['fuente'], s['id_busqueda']) == (b['fuente'], b['id_busqueda']) and s.get('started')), None)
        searches.append(dict(b, token=json.dumps([b['fuente'], b['id_busqueda']], ensure_ascii=False),
                             measurement=measurements(doc, b), last=history or b.get('legacy_last')))
    totals = {k: (sum(b[k] for b in run['searches']) if all(b.get(k) is not None for b in run['searches']) else None) for k in ('processed','new','changed','unchanged')} if run else {}
    return {'totals': totals, 'searches': searches, 'runs': runs, 'active': active, 'run': run,
            'labels': LABELS, 'duration': duration, 'age': age,
            'remaining': remaining(doc, run), 'catalog_updated': doc.get('catalog_updated')}


def crear_router():
    router = APIRouter(prefix=PATH, include_in_schema=False)

    def render(request, status=200, error=None, doc=None, warning=None):
        return templates.TemplateResponse(request=request, name='ejecuciones06.html', status_code=status,
            context={**context(doc or {'runs': [], 'searches': []}, request.query_params.get('run')),
                     'error': error, 'warning': warning, 'request_id': str(uuid4()),
                     'configured': bool(os.getenv('RADAR_STATE_BUCKET'))})

    @router.get('')
    def page(request: Request):
        if not os.getenv('RADAR_STATE_BUCKET'):
            return render(request, warning='El lanzamiento durable requiere configurar Cloud Run y Cloud Storage. No se ejecutará scraping desde la web local.')
        try:
            doc, warning = ServicioEjecuciones().overview(refresh=True)
            return render(request, doc=doc, warning=warning)
        except Exception:
            return render(request, 503, error='No se pudo consultar el registro durable. Vuelve a cargar la página; no se inició ninguna captura.')

    @router.post('')
    async def start(request: Request):
        try:
            if int(request.headers.get('content-length', '0')) > 65536:
                raise ValueError('Selección demasiado grande.')
            raw = await request.body()
            if len(raw) > 65536:
                raise ValueError('Selección demasiado grande.')
            if request.headers.get('content-type', '').startswith('application/json'):
                data = json.loads(raw)
                keys, request_id = data.get('searches'), data.get('request_id')
            else:
                from urllib.parse import parse_qs
                data = parse_qs(raw.decode())
                keys = [json.loads(v) for v in data.get('search', [])]
                request_id = data.get('request_id', [''])[0]
            if not isinstance(keys, list) or not valid_id(request_id):
                raise ValueError('Solicitud inválida. Recarga y selecciona búsquedas activas.')
            # Valida forma/límites aun al reenviar una solicitud; la existencia se verifica en el snapshot.
            if not keys or len(keys) > 100 or any(not isinstance(k, list) or len(k) != 2 or any(not isinstance(v, str) for v in k) for k in keys):
                raise ValueError('Selecciona entre 1 y 100 búsquedas activas.')
            run = await run_in_threadpool(lambda: ServicioEjecuciones().start(keys, request_id))
            if request.headers.get('content-type', '').startswith('application/json'):
                return JSONResponse({'id': run['id'], 'status': run['status'], 'url': PATH + '?run=' + run['id']}, 202, headers={'Cache-Control': 'no-store'})
            return RedirectResponse(PATH + '?run=' + run['id'], 303)
        except (ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
            return JSONResponse({'detail': str(exc) if isinstance(exc, ValueError) else 'Solicitud inválida.'}, 409 if isinstance(exc, Conflict) else 422)
        except Exception:
            return JSONResponse({'detail': 'No se pudo confirmar la operación. Consulta el seguimiento antes de repetirla.'}, 503)

    @router.get('/estado')
    def status(request: Request, run: str | None = None):
        try:
            if run is not None and not valid_id(run):
                return JSONResponse({'detail': 'Identificador inválido.'}, 422)
            doc, _ = ServicioEjecuciones().overview()
            ctx = context(doc, run)
            if run and ctx['run'] is None:
                return JSONResponse({'detail': 'Ejecución no encontrada o fuera de retención.'}, 404)
            ctx['request'] = request
            html = templates.env.get_template('_ejecucion06.html').render(ctx)
            history = templates.env.get_template('_ejecuciones_historial06.html').render(ctx)
            return JSONResponse({'active': ctx['active']['id'] if ctx['active'] else None, 'run': ctx['run'], 'html': html, 'history_html': history},
                                headers={'Cache-Control': 'no-store'})
        except Exception:
            return JSONResponse({'detail': 'Seguimiento temporalmente no disponible; esto no significa que el Job haya fallado.'}, 503, headers={'Cache-Control': 'no-store'})
    return router
