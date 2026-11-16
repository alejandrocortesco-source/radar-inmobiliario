"""Página y API de control: no consultan el catálogo SQLite durante una captura."""
import json
import copy
import os
from uuid import uuid4
from fastapi import APIRouter, Request
from starlette.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse, RedirectResponse
from .v06 import templates
from ejecuciones.control import ACTIVE, Conflict, measurements, age, valid_id
from ejecuciones.servicio import ServicioEjecuciones
from ejecuciones.resultados import COUNT_KEYS, presentation

PATH = '/v0.6/ejecuciones'
LABELS = {'skipped': 'Omitida', 'reconciling': 'Reconciliando cierre', 'launching': 'Solicitando Job', 'uncertain': 'Lanzamiento por confirmar', 'queued': 'Esperando Job',
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
    if run['status'] == 'reconciling':
        return 'Tiempo restante no disponible mientras se reconcilia el cierre con Cloud Run.'
    if not any(b['status'] in {'pending', 'running'} for b in run['searches']):
        return 'Confirmando cierre y guardado remoto. Tiempo restante: por estimar.'
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


def tracking(run):
    if not run or run['status'] not in ACTIVE:
        return None
    confirmed = run.get('verification', {}).get('state') == 'active'
    names = [b['nombre'] + ' · ' + b['fuente'] for b in run['searches'] if b['status'] == 'running']
    if not names:
        names = [b['nombre'] + ' · ' + b['fuente'] for b in run['searches'][:2]]
    return {'confirmed': confirmed,
            'title': 'Actualización en curso' if confirmed else 'Verificando el estado de una actualización anterior',
            'names': '; '.join(names),
            'state': LABELS.get(run['status'], run['status']) if confirmed else 'Cierre o lanzamiento por confirmar'}


def context(doc, requested=None):
    doc = copy.deepcopy(doc)
    for r in doc['runs']:
        r['searches'] = [presentation(b) for b in r['searches']]
    runs = sorted(doc['runs'], key=lambda r: r['created'], reverse=True)
    active = next((r for r in runs if r['status'] in ACTIVE), None)
    run = next((r for r in runs if r['id'] == requested), None) if requested else (active or (runs[0] if runs else None))
    searches = []
    for b in doc['searches']:
        entry = next(((r,s) for r in runs for s in r['searches'] if (s['fuente'], s['id_busqueda']) == (b['fuente'], b['id_busqueda']) and s.get('started')), None)
        history = entry[1] if entry else None
        last_tracking = tracking(entry[0]) if entry else None
        last_label = 'Por verificar' if last_tracking and not last_tracking['confirmed'] else None
        searches.append(dict(b, token=json.dumps([b['fuente'], b['id_busqueda']], ensure_ascii=False),
                             measurement=measurements(doc, b), last=history or b.get('legacy_last'), last_label=last_label))
    totals = {k: (sum(b[k] for b in run['searches']) if all(b.get(k) is not None for b in run['searches']) else None) for k in COUNT_KEYS} if run else {}
    return {'totals': totals, 'searches': searches, 'runs': runs, 'active': active, 'run': run,
            'labels': LABELS, 'duration': duration, 'age': age, 'tracking': tracking,
            'active_tracking': tracking(active), 'run_tracking': tracking(run),
            'remaining': remaining(doc, run), 'catalog_updated': doc.get('catalog_updated')}


def _control_dashboard():
    # El dashboard ya está dentro de WebDurable: no restaurar otro snapshot aquí.
    if not os.getenv('K_SERVICE') or not os.getenv('RADAR_STATE_BUCKET'):
        return {'runs': [], 'searches': []}
    return ServicioEjecuciones().control.read()[0]


def resumen_dashboard(catalogo):
    from ejecuciones.mediciones import previous
    from pathlib import Path
    aviso = None
    try:
        doc = _control_dashboard()
    except Exception:
        doc = {'runs': [], 'searches': []}
        aviso = 'El seguimiento no está disponible temporalmente. Se muestra la última captura conocida.'
    rows = []
    for b in catalogo.listar_busquedas():
        last = None
        run = None
        for r in sorted(doc['runs'], key=lambda r: r['created'], reverse=True):
            found = next((x for x in r['searches'] if (x['fuente'],x['id_busqueda']) == (b['fuente'],b['id_busqueda'])), None)
            if found:
                last, run = found, r
                break
        if last is None and catalogo.busquedas:
            last, _ = previous(Path(catalogo.busquedas.ruta).parent, b)
        state = last['status'] if last else None
        active = run is not None and run['status'] in ACTIVE
        if not b.get('activa', True):
            label, cls = 'Inactiva', ''
        elif active:
            label, cls = ('Por verificar' if age(run['updated']) > 120 else ('En espera' if state == 'pending' else LABELS.get(state, 'En ejecución'))), 'verify'
        elif state == 'running':
            label, cls = 'Sin cierre confirmado', 'verify'
        else:
            label = LABELS.get(state, 'Sin ejecutar')
            cls = 'verified' if state == 'completed' else ('verify' if state in {'failed','partial','interrupted'} else '')
        date = (last.get('started') or last.get('finished') or (run.get('created') if run else None)) if last else None
        rows.append(dict(b, estado=label, clase=cls, fecha=date,
                         href=PATH + ('?run=' + run['id'] if run else ''),
                         prioridad=2 if active else (1 if last is None and b.get('activa',True) else 0)))
    rows.sort(key=lambda b:(b['prioridad'],b['fecha'] or '',b['nombre']), reverse=True)
    return rows[:3], aviso


def crear_router():
    router = APIRouter(prefix=PATH, include_in_schema=False)

    def render(request, status=200, error=None, doc=None, warning=None, schedule=None):
        return templates.TemplateResponse(request=request, name='ejecuciones06.html', status_code=status,
            context={**context(doc or {'runs': [], 'searches': []}, request.query_params.get('run')),
                     'error': error, 'warning': warning, 'request_id': str(uuid4()),
                     'schedule': schedule, 'configured': bool(os.getenv('RADAR_STATE_BUCKET'))})

    @router.get('')
    def page(request: Request):
        if not os.getenv('RADAR_STATE_BUCKET'):
            return render(request, warning='El lanzamiento durable requiere configurar Cloud Run y Cloud Storage. No se ejecutará scraping desde la web local.')
        try:
            svc = ServicioEjecuciones()
            doc, warning = svc.overview(refresh=True)
            doc = svc.report(doc, request.query_params.get('run'))
            schedule = None
            if os.getenv('RADAR_SCHEDULE_TARGET'):
                from ejecuciones.programacion import Programacion
                from ejecuciones.scheduler import Scheduler
                schedule = Programacion(svc, Scheduler()).read(doc)
            return render(request, doc=doc, warning=warning, schedule=schedule)
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

    @router.post('/programacion')
    async def schedule_update(request: Request):
        from ejecuciones.programacion import Programacion
        from ejecuciones.scheduler import Scheduler
        if not os.getenv('RADAR_SCHEDULE_TARGET'):
            return JSONResponse({'detail': 'Programación no configurada.'}, 503)
        try:
            raw = await request.body()
            if len(raw) > 65536:
                raise ValueError('Configuración demasiado grande.')
            from urllib.parse import parse_qs
            data = parse_qs(raw.decode(), keep_blank_values=True)
            keys = [json.loads(v) for v in data.get('schedule_search', [])]
            days = [int(v) for v in data.get('days', [])]
            action = data.get('action', ['save'])[0]
            expected = data.get('revision', [''])[0]
            svc = ServicioEjecuciones()
            program = Programacion(svc, Scheduler())
            await run_in_threadpool(lambda: program.save(keys, days, data.get('time', [''])[0], action, expected))
            return RedirectResponse(PATH + '?programacion=guardada#programacion', 303)
        except (ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
            message = str(exc) if isinstance(exc, ValueError) else 'Configuración inválida.'
            status = 409 if isinstance(exc, Conflict) else 422
        except Exception:
            message, status = 'No se confirmó Scheduler. No se confirma la programación activa. Recarga y vuelve a guardar o pausa para recuperar el estado.', 503
        svc = ServicioEjecuciones()
        doc = svc.control.read()[0]
        schedule = Programacion(svc, Scheduler()).read(doc)
        return render(request, status, error=message, doc=doc, schedule=schedule)

    @router.get('/estado')
    def status(request: Request, run: str | None = None):
        try:
            if run is not None and not valid_id(run):
                return JSONResponse({'detail': 'Identificador inválido.'}, 422)
            svc = ServicioEjecuciones()
            doc, _ = svc.overview()
            doc = svc.report(doc, run)
            ctx = context(doc, run)
            if run and ctx['run'] is None:
                return JSONResponse({'detail': 'Ejecución no encontrada o fuera de retención.'}, 404)
            ctx['request'] = request
            html = templates.env.get_template('_ejecucion06.html').render(ctx)
            history = templates.env.get_template('_ejecuciones_historial06.html').render(ctx)
            notice = templates.env.get_template('_ejecucion_aviso06.html').render(ctx)
            return JSONResponse({'active': ctx['active']['id'] if ctx['active'] else None, 'run': ctx['run'], 'html': html, 'history_html': history, 'notice_html': notice},
                                headers={'Cache-Control': 'no-store'})
        except Exception:
            return JSONResponse({'detail': 'Seguimiento temporalmente no disponible; esto no significa que el Job haya fallado.'}, 503, headers={'Cache-Control': 'no-store'})
    return router
