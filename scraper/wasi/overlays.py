"""Cierre normal y acotado de anuncios ProductFruits observados; sin contenido comercial."""
import time
from dataclasses import dataclass

from playwright.async_api import Error as BrowserError, TimeoutError as BrowserTimeout
from .diagnostico import WasiListingError
from metro.scraper import check_access

# La raíz observada y el host sin altura pueden ser hermanos. No filtrar su visibilidad.
ROOT = ':is(.productfruits--container, .productfruits--container-root)'
BACKDROP = ROOT + ' .pfruits-announcement-popup-container'
DIALOG = BACKDROP + ' .pfruits-announcement-popup-v3[role="dialog"]'
MAX_CLOSES = 3
MAX_PAGE_CLOSES = 12
HANDLING_MS = 6000
PAGE_HANDLING_MS = 30000
CLOSE_MS = 1500
ACTION_ATTEMPTS = 3


@dataclass
class Budget:
    closes: int = 0
    seconds: float = 0


async def visible_nodes(locator):
    return [node for node in await locator.all() if await node.is_visible()]


async def blocking_background(page):
    # Un fondo puede quedar visible pero con pointer-events:none. Solo se exige
    # que no reciba interacción; un fondo residual interceptable es un fallo.
    return await page.locator(BACKDROP).evaluate_all("""nodes => nodes.some(e => {
        const r=e.getBoundingClientRect(), s=getComputedStyle(e);
        if (!r.width || !r.height || s.visibility==='hidden' || s.display==='none' || s.pointerEvents==='none') return false;
        return [[.5,.5],[.1,.1],[.9,.9],[.1,.9],[.9,.1]].some(([x,y])=>{
            const top=document.elementFromPoint(Math.max(0,Math.min(innerWidth-1,r.left+r.width*x)),
                                              Math.max(0,Math.min(innerHeight-1,r.top+r.height*y)));
            return !!top && (top===e || e.contains(top));
        });
    })""")


async def dismiss_announcements(page, timeout):
    """Hasta tres anuncios consecutivos, sin confundir un mismo cierre fallido con otro anuncio."""
    dialogs = await visible_nodes(page.locator(DIALOG))
    background = await blocking_background(page)
    if not dialogs and not background:
        return 0
    await check_access(page)
    budget = getattr(page, '_radar_announcement_budget', None)
    if budget is None:
        budget = Budget()
        page._radar_announcement_budget = budget
    started = time.monotonic()
    deadline = started + min(timeout, HANDLING_MS, max(0, PAGE_HANDLING_MS-budget.seconds*1000))/1000
    closed = 0
    try:
        while True:
            remaining = int((deadline-time.monotonic())*1000)
            if remaining <= 0 or budget.closes >= MAX_PAGE_CLOSES or closed >= MAX_CLOSES:
                raise WasiListingError('wasi_overlay_limit')
            dialogs = await visible_nodes(page.locator(DIALOG))
            if not dialogs:
                if await blocking_background(page):
                    raise WasiListingError('wasi_overlay_unclosable')
                return closed
            if len(dialogs) != 1:
                raise WasiListingError('wasi_overlay_ambiguous')
            dialog = dialogs[0]
            # Clase, rol, nombre accesible y pertenencia al diálogo son obligatorios.
            closes = dialog.locator('button.modern-close-btn').and_(
                dialog.get_by_role('button', name='Close dialog', exact=True))
            candidates = await visible_nodes(closes)
            if len(candidates) != 1:
                raise WasiListingError('wasi_overlay_ambiguous')
            if not await candidates[0].is_enabled(timeout=max(1, remaining)):
                raise WasiListingError('wasi_overlay_unclosable')
            old = await dialog.element_handle(timeout=max(1, remaining))
            budget.closes += 1
            closed += 1
            try:
                await candidates[0].click(timeout=min(CLOSE_MS, remaining))
                await page.wait_for_function("""e => !e.isConnected || !e.getClientRects().length ||
                    getComputedStyle(e).visibility==='hidden' || getComputedStyle(e).display==='none'""",
                    arg=old, timeout=max(1, min(CLOSE_MS, int((deadline-time.monotonic())*1000))))
            except BrowserError:
                raise WasiListingError('wasi_overlay_unclosable') from None
            # Comprueba también el fondo. Permite el siguiente anuncio si tiene
            # su propio diálogo, pero nunca vuelve a clicar el cierre que falló.
            dialogs = await visible_nodes(page.locator(DIALOG))
            if not dialogs:
                try:
                    await page.wait_for_function("""({background,dialog}) => {
                        const visible=e=>{const s=getComputedStyle(e),r=e.getBoundingClientRect();
                            return !!r.width && !!r.height && s.display!=='none' && s.visibility!=='hidden';};
                        return [...document.querySelectorAll(dialog)].some(visible) ||
                            ![...document.querySelectorAll(background)].some(e=>visible(e) && getComputedStyle(e).pointerEvents!=='none');
                    }""", arg={'background': BACKDROP, 'dialog': DIALOG},
                        timeout=max(1, min(CLOSE_MS, int((deadline-time.monotonic())*1000))))
                except BrowserTimeout:
                    raise WasiListingError('wasi_overlay_unclosable') from None
                if await visible_nodes(page.locator(DIALOG)):
                    continue  # El fondo pasó a otro anuncio reconocido durante la espera.
                return closed
    finally:
        budget.seconds += time.monotonic()-started
        try:
            from .diagnostico import current
            diagnostic=current.get()
            if closed and diagnostic and len([r for r in diagnostic.records if r.get('outcome')=='recovered'])<8:
                record={'source':'wasi','radar_run':__import__('os').getenv('RADAR_RUN_ID'),
                    'technical_run':diagnostic.scraper.run_id,'search':diagnostic.scraper.cfg.url,
                    'stage':'recognized_popup','last_completed':diagnostic.last,'outcome':'recovered',
                    'message':'Anuncio reconocido cerrado por el mecanismo existente.', 'code':'wasi_overlay_recovered',
                    'recovered':True,'closed':closed,'duration_ms':round((time.monotonic()-started)*1000),'timeout_ms':min(timeout,HANDLING_MS)}
                diagnostic.records.append(record);diagnostic.emit(record)
        except Exception:
            pass


async def prepare_interaction(page, target, timeout):
    await dismiss_announcements(page, timeout)
    try:
        await target.scroll_into_view_if_needed(timeout=min(timeout, 1000))
        await target.click(trial=True, timeout=min(timeout, 1000))
    except BrowserError:
        # Puede haber aparecido entre la inspección y el ensayo sin despacho.
        if not await dismiss_announcements(page, timeout):
            raise WasiListingError('wasi_interaction_blocked') from None
        try:
            await target.click(trial=True, timeout=min(timeout, 1000))
        except BrowserError:
            raise WasiListingError('wasi_interaction_blocked') from None


async def normal_click(page, target, timeout, changed=None):
    """Un solo despacho. Solo reintenta si un anuncio impidió despachar el clic."""
    deadline = time.monotonic() + timeout/1000
    for attempt in range(ACTION_ATTEMPTS):
        remaining = int((deadline-time.monotonic())*1000)
        if remaining <= 0:
            raise WasiListingError('wasi_interaction_blocked')
        await prepare_interaction(page, target, remaining)
        if attempt and changed and await changed():
            return  # La verificación exterior decidirá si el estado obtenido es correcto.
        handle = await target.element_handle(timeout=max(1, int((deadline-time.monotonic())*1000)))
        if handle is None:
            raise WasiListingError('wasi_interaction_uncertain')
        await handle.evaluate("""e => {
            e.__radarClickSent=false;
            e.__radarClickObserver=()=>{e.__radarClickSent=true};
            e.addEventListener('click',e.__radarClickObserver,{capture:true,once:true});
        }""")
        try:
            try:
                # Handle fija el mismo nodo en que se instaló el observador.
                await handle.click(timeout=max(1, min(1000, int((deadline-time.monotonic())*1000))))
            except BrowserError:
                try:
                    sent = await handle.evaluate('e => e.__radarClickSent')
                except BrowserError:
                    # Un cambio de documento impide saber si hubo despacho. No repetir.
                    raise WasiListingError('wasi_interaction_uncertain') from None
                if sent or (changed and await changed()):
                    await dismiss_announcements(page, max(1, int((deadline-time.monotonic())*1000)))
                    return
                if not await dismiss_announcements(page, max(1, int((deadline-time.monotonic())*1000))):
                    raise WasiListingError('wasi_interaction_blocked') from None
                continue
            try:
                sent = await handle.evaluate('e => e.__radarClickSent')
            except BrowserError:
                raise WasiListingError('wasi_interaction_uncertain') from None
            if not sent and not (changed and await changed()):
                if await dismiss_announcements(page, max(1, int((deadline-time.monotonic())*1000))):
                    continue
                raise WasiListingError('wasi_interaction_uncertain')
            await dismiss_announcements(page, max(1, int((deadline-time.monotonic())*1000)))
            return
        finally:
            try:
                await handle.evaluate("e => e.removeEventListener('click',e.__radarClickObserver,true)")
            except BrowserError:
                pass  # Navegación confirmada o contexto perdido: nunca repetir para limpiar.
    raise WasiListingError('wasi_overlay_limit')
