"""Orquestación secuencial en el Job; ningún scraper se ejecuta en la web."""
import asyncio
import json
import logging
import os
import signal
import sqlite3
import time
import threading
from google.api_core.exceptions import PreconditionFailed, NotFound
from contextlib import ExitStack, closing
from pathlib import Path
from time import monotonic

from catalogo.persistencia.busquedas import BusquedasSQLite
from metro.scraper import Scraper, Config
from wasi.scraper import WasiScraper
from wasi.__main__ import configuracion as wasi_config
from fincaraiz.scraper import FincaraizScraper
from fincaraiz.__main__ import configuracion as fincaraiz_config
from wasi.durable import EstadoGCS, ARCHIVOS
from wasi.locking import bloqueo
from .control import ControlGCS, IntegrityError, ACTIVE, now, select, projection, valid_id


def scraper_for(repo, folder, search):
    source, key = search['fuente'], search['id_busqueda']
    if source == 'metrocuadrado':
        return Scraper(Config(db=str(folder / 'metro.sqlite'), url=key, urls=[key], concurrency=1))
    if source == 'wasi':
        return WasiScraper(wasi_config(repo, folder / 'wasi.sqlite', ids=[key], concurrency=1))
    return FincaraizScraper(fincaraiz_config(repo, folder / 'fincaraiz.sqlite', ids=[key], concurrency=1))


def metrics(scraper):
    if not scraper.run_id:
        return {}
    summary = scraper.store.summary(scraper.run_id)
    terminal = {'success', 'unchanged', 'partial', 'failed', 'blocked'}
    processed = sum(n for s, n in summary['statuses'].items() if s in terminal)
    with scraper.store.connect() as db:
        counts = dict(db.execute("SELECT classification,count(*) FROM jobs WHERE run_id=? AND status IN ('success','unchanged') GROUP BY classification", (scraper.run_id,)))
        listing_count = db.execute("SELECT count(*) FROM events WHERE run_id=? AND kind='listing_incomplete'", (scraper.run_id,)).fetchone()[0]
        listing = db.execute("SELECT context_json FROM events WHERE run_id=? AND kind='listing_incomplete' ORDER BY id DESC LIMIT 1", (scraper.run_id,)).fetchall()
    from wasi.diagnostico import MESSAGES
    code = json.loads(listing[0][0]).get('code') if listing else None
    code = code if code in MESSAGES else ('listing_unverified' if listing else None)
    listing_error = MESSAGES.get(code, 'Listado incompleto: no se pudo verificar su cobertura.') if listing else None
    return {'listing_error_count': listing_count, 'listing_error': listing_error, 'listing_code': code,
            'listing_complete': bool(summary.get('listing_complete')), 'listing_pages': summary.get('pages'),
            'technical_run': scraper.run_id, 'processed': processed,
            'new': counts.get('new', 0), 'changed': counts.get('modified', 0), 'unchanged': counts.get('unchanged', 0),
            'phase': 'Revisando anuncios' if summary.get('listing_complete') else 'Recorriendo resultados',
            'error_count': summary.get('errors'), 'portal_status': summary['status']}


def check_integrity(folder):
    for name in ARCHIVOS:
        file = folder / name
        if file.exists():
            with closing(sqlite3.connect(file.as_uri() + '?mode=ro', uri=True)) as db:
                if db.execute('PRAGMA quick_check').fetchall() != [('ok',)]:
                    raise IntegrityError('La integridad SQLite no se pudo confirmar')


def run_manual(folder, run_id, control=None, state_factory=None, make_scraper=scraper_for, heartbeat=30):
    if not valid_id(run_id):
        raise ValueError('Identificador de ejecución inválido')
    folder = Path(folder).resolve()
    folder.mkdir(parents=True, exist_ok=True)
    control = control or ControlGCS()
    worker = os.environ.get('CLOUD_RUN_EXECUTION')
    if not worker:
        raise ValueError('La ejecución manual requiere un Job durable')
    state_factory = state_factory or (lambda: EstadoGCS(os.environ['RADAR_STATE_BUCKET'], os.getenv('RADAR_STATE_OBJECT', 'radar/state.tar.gz')))
    claimed = False
    def claim(doc):
        nonlocal claimed
        claimed = False
        r = next((r for r in doc['runs'] if r['id'] == run_id), None)
        if r and r['status'] in {'launching', 'queued', 'uncertain'} and not r.get('worker'):
            r.update(worker=worker, status='running', started=now(), updated=now(), phase='Recuperando snapshot')
            claimed = True
    control.change(claim)
    if not claimed:
        # Incluye reintentos de tarea y ejecuciones tardías tras reconciliación.
        return False
    state = None
    rows = control.get(run_id)['searches']
    for env, name in {'METRO_DB': 'metro.sqlite', 'WASI_DB': 'wasi.sqlite', 'FINCARAIZ_DB': 'fincaraiz.sqlite', 'RADAR_CRM_DB': 'metro-consola.sqlite'}.items():
        os.environ[env] = str(folder / name)
    # Solo logs agregados en este modo. Nunca logs de eventos por anuncio/configuración.
    logging.getLogger('metro').setLevel(logging.CRITICAL)

    def patch(**values):
        return control.patch(run_id, values, worker=worker)

    def save():
        state.asegurar_bloqueo()
        check_integrity(folder)
        state.guardar(folder)
        patch(snapshot_generation=str(state.generacion), persisted=False, phase='Snapshot parcial confirmado')

    async def capture(repo):
        for b in rows:
            # Revalida otra vez contra el snapshot autoritativo al comenzar el Job.
            b.update(status='running', started=now(), phase='Preparando portal')
            patch(searches=rows, phase=b['phase'])
            started = monotonic()
            scraper = make_scraper(repo, folder, b)
            task = asyncio.create_task(scraper.run())
            last_save = monotonic()
            try:
                while True:
                    done, _ = await asyncio.wait({task}, timeout=heartbeat)
                    state.asegurar_bloqueo()
                    b.update(metrics(scraper))
                    patch(searches=rows, phase=b.get('phase', 'Extrayendo'))
                    if done:
                        result = await task
                        break
                    if monotonic() - last_save >= 60:
                        await asyncio.to_thread(save)
                        last_save = monotonic()
                b.update(status={'completed': 'extracted', 'incomplete': 'partial', 'interrupted': 'interrupted'}.get(result['status'], 'failed'),
                         finished=now(), duration=round(monotonic() - started, 1), phase='Extracción terminada')
                if b['status'] != 'extracted':
                    b['error'] = b.get('listing_error') or 'Portal: extracción ' + ('parcial' if b['status'] == 'partial' else 'no completada') + '. Revisar antes de repetir.'
                patch(searches=rows)
                await asyncio.to_thread(save)
            finally:
                if not task.done():
                    task.cancel()
                    try:
                        await task
                    except BaseException:
                        pass
        patch(status='saving', phase='Confirmando guardado remoto', searches=rows)
        await asyncio.to_thread(save)

    outcome = 'failed'
    try:
        with ExitStack() as stack:
            stack.enter_context(bloqueo(folder / 'radar-state'))
            # Una petición web puede estar terminando justo después del lanzamiento.
            for attempt in range(13):
                try:
                    state = state_factory()
                    patch(lock_token=state.lock_token)
                    stack.enter_context(state)
                    break
                except PreconditionFailed:
                    if attempt == 12:
                        raise
                    patch(phase='Esperando el bloqueo compartido')
                    time.sleep(5)
            patch(lock_generation=str(state.lock_generacion))
            state.cargar(folder)
            for name in ('metro.sqlite', 'wasi.sqlite', 'fincaraiz.sqlite'):
                stack.enter_context(bloqueo(folder / name))
            repo = BusquedasSQLite(folder / 'metro-consola.sqlite')
            select(projection(repo), [[b['fuente'], b['id_busqueda']] for b in rows])
            root = None
            async def controlled():
                nonlocal root
                root = asyncio.current_task()
                await capture(repo)
            handles_signal = threading.current_thread() is threading.main_thread()
            previous = signal.getsignal(signal.SIGTERM) if handles_signal else None
            if handles_signal:
                signal.signal(signal.SIGTERM, lambda *_: root.cancel() if root else None)
            try:
                asyncio.run(controlled())
            finally:
                if handles_signal:
                    signal.signal(signal.SIGTERM, previous)
            # No publicar éxito hasta guardar y liberar correctamente el bloqueo.
            outcome = 'completed' if all(b['status'] == 'extracted' for b in rows) else (
                'partial' if any(b['status'] in {'extracted', 'partial'} for b in rows) else 'failed')
        for b in rows:
            if b['status'] == 'extracted':
                b['status'] = 'completed'
        patch(status=outcome, searches=rows, finished=now(), phase='Guardado remoto confirmado', persisted=True)
        return True
    except BaseException as exc:
        # Ninguna excepción del SDK/portal se copia al registro: puede contener secretos.
        # El último snapshot confirmado se conserva; no se guarda después de perder el lock.
        interrupted = isinstance(exc, (KeyboardInterrupt, asyncio.CancelledError))
        for b in rows:
            if b['status'] in {'running', 'extracted'}:
                b.update(status='interrupted', finished=now())
            elif b['status'] == 'pending':
                b.update(status='not_run', error='No ejecutada por fallo de infraestructura o configuración')
        needs_cleanup = False
        if state is not None:
            try:
                state.lock.reload(timeout=10)
                generation = int(state.lock.generation)
                if state.lock.download_as_bytes(if_generation_match=generation, timeout=10) == state.lock_token.encode():
                    state.lock.delete(if_generation_match=generation, timeout=10)
            except (NotFound, PreconditionFailed):
                pass
            except Exception:
                needs_cleanup = True
        try:
            patch(status='reconciling' if needs_cleanup else ('interrupted' if interrupted else 'failed'), searches=rows, finished=now(), persisted=False,
                  phase='Requiere revisión', error='Infraestructura o persistencia: ' + type(exc).__name__ + '. Se detuvo el flujo; no se confirma el guardado final.')
        except Exception:
            pass  # La reconciliación cerrará el registro con el estado real de Cloud Run.
        return False
