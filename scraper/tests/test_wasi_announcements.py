"""Anuncios reales por estructura; contenido y red exclusivamente sintéticos."""
import asyncio
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from playwright.async_api import async_playwright, ElementHandle, TimeoutError as BrowserTimeout

from metro.extraction import Restricted
from wasi import overlays
from wasi.auth import autenticar
from wasi.browser import aplicar, siguiente, preparar_buscar
from wasi.diagnostico import WasiListingError
from wasi.scraper import WasiConfig, WasiScraper, WasiStore
from catalogo.fuentes.wasi import identidad
from test_wasi import html, config, simulador, descubrir, item, documento

SCRIPT = Path(__file__).with_name('fixtures').joinpath('wasi_announcement.js').read_text(encoding='utf-8')
RECORDS = [{'id': str(i).zfill(3), 'price': '100.000.000'} for i in range(1, 4)]


@pytest.fixture(autouse=True)
def synthetic_secrets(monkeypatch):
    for key in ('WASI_USER_FILE', 'WASI_PASSWORD_FILE', 'WASI_USE_HERE'):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv('WASI_USER', 'synthetic-user')
    monkeypatch.setenv('WASI_PASSWORD', 'synthetic-password')


async def setup_page(browser):
    page = await browser.new_page()
    await page.route('**/*', lambda route: route.abort())
    await page.set_content(html(RECORDS))
    await page.evaluate(SCRIPT)
    return page


@pytest.mark.parametrize('mode,text,expected', [
    ('absent', '', None),
    ('normal', 'Noticia del portal', None),
    ('normal', 'Nueva promoción con otra imagen y título', None),
    ('sibling-root', 'Anuncio bajo raíz hermana del host vacío', None),
    ('hidden', 'Privado', 'wasi_overlay_ambiguous'),
    ('disabled', 'Privado', 'wasi_overlay_unclosable'),
    ('ambiguous', 'Privado', 'wasi_overlay_ambiguous'),
    ('two-dialogs', 'Privado', 'wasi_overlay_ambiguous'),
    ('wrong-name', 'Privado', 'wasi_overlay_ambiguous'),
    ('unknown', 'Privado', 'wasi_interaction_blocked'),
    ('stuck', 'Privado', 'wasi_overlay_unclosable'),
    ('residual-background', 'Privado', 'wasi_overlay_unclosable'),
])
def test_visible_descendants_zero_height_and_fail_safe(mode, text, expected):
    async def run():
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            try:
                page = await setup_page(browser)
                if mode != 'absent':
                    await page.evaluate('arg => addAnnouncement(arg)', {'mode': mode, 'text': text})
                    assert await page.locator('.productfruits--container:visible').count() == 0
                if expected:
                    with pytest.raises(WasiListingError) as exc:
                        await preparar_buscar(page, 2200)
                    assert exc.value.wasi_code == expected
                    assert text not in str(exc.value) and 'Call log' not in str(exc.value)
                else:
                    await preparar_buscar(page, 2200)
                    assert not await overlays.blocking_background(page)
                counts = await page.evaluate('popupCounts')
                assert counts['business'] == counts['search'] == counts['next'] == 0
                assert counts['closed'] == (1 if mode in ('normal','sibling-root','stuck','residual-background') else 0)
            finally:
                await browser.close()
    asyncio.run(run())


@pytest.mark.parametrize('count,expected', [(3, None), (4, 'wasi_overlay_limit')])
def test_consecutive_announcements_are_bounded(count, expected):
    async def run():
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            try:
                page = await setup_page(browser)
                await page.evaluate('remaining => addAnnouncement({remaining})', count)
                if expected:
                    with pytest.raises(WasiListingError) as exc:
                        await overlays.dismiss_announcements(page, 6000)
                    assert exc.value.wasi_code == expected
                else:
                    assert await overlays.dismiss_announcements(page, 6000) == count
                assert await page.evaluate('popupCounts.closed') == min(count, overlays.MAX_CLOSES)
                assert await page.evaluate('popupCounts.business') == 0
            finally:
                await browser.close()
    asyncio.run(run())


def test_page_budget_count_time_and_security():
    async def run():
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            try:
                page = await setup_page(browser)
                for _ in range(overlays.MAX_PAGE_CLOSES):
                    await page.evaluate('addAnnouncement()')
                    assert await overlays.dismiss_announcements(page, 2000) == 1
                await page.evaluate('addAnnouncement()')
                with pytest.raises(WasiListingError, match='límite'):
                    await overlays.dismiss_announcements(page, 2000)
                assert await page.evaluate('popupCounts.closed') == overlays.MAX_PAGE_CLOSES
                await page.close()
                page = await setup_page(browser)
                page._radar_announcement_budget = overlays.Budget(seconds=overlays.PAGE_HANDLING_MS/1000)
                await page.evaluate('addAnnouncement()')
                with pytest.raises(WasiListingError, match='límite'):
                    await overlays.dismiss_announcements(page, 2000)
                assert await page.evaluate('popupCounts.closed') == 0
                await page.close()
                page = await setup_page(browser)
                await page.evaluate("addAnnouncement({text:'verifica que eres humano'})")
                with pytest.raises(Restricted):
                    await overlays.dismiss_announcements(page, 2000)
                assert await page.evaluate('popupCounts.closed') == 0
            finally:
                await browser.close()
    asyncio.run(run())


@pytest.mark.parametrize('target_id,when', [
    ('advanced_search','before'), ('advanced_search','after'),
    ('properties_table_next','before'), ('properties_table_next','after'),
    ('advanced_search','pointerdown'), ('properties_table_next','pointerdown'),
])
def test_late_interception_or_error_after_dispatch_never_duplicates(monkeypatch, target_id, when):
    original = ElementHandle.click
    injected = False

    async def click(handle, **kwargs):
        nonlocal injected
        if not injected and await handle.get_attribute('id') == target_id:
            injected = True
            if when == 'before':
                await handle.evaluate('() => addAnnouncement()')
            elif when == 'pointerdown':
                await handle.evaluate("e => e.addEventListener('pointerdown',()=>addAnnouncement(),{once:true})")
            else:
                await original(handle, **kwargs)
                await handle.evaluate('() => addAnnouncement()')
                raise BrowserTimeout('synthetic error after dispatch')
        return await original(handle, **kwargs)

    monkeypatch.setattr(ElementHandle, 'click', click)

    async def run():
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            try:
                page = await setup_page(browser)
                first = await aplicar(page, config(), 3500, AsyncMock())
                second = await siguiente(page, first, 3500, AsyncMock())
                assert first['active'] == 1 and first['end'] == 2
                assert second['active'] == 2 and second['start'] == 3 and second['total'] == 3
                assert not second['next']
                assert injected
                assert await page.evaluate('popupCounts') == {'closed':1,'business':0,'search':1,'next':1}
            finally:
                await browser.close()
    asyncio.run(run())


def test_recurring_before_search_and_during_list_load_and_pagination():
    async def run():
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            try:
                page = await setup_page(browser)
                await page.evaluate("""() => {
                    addAnnouncement();
                    const search=document.querySelector('#advanced_search'), before=search.onclick;
                    search.onclick=e=>{before(e);setTimeout(()=>addAnnouncement({text:'Otra noticia'}),1)};
                    const next=document.querySelector('#properties_table_next'), nextBefore=next.onclick;
                    next.onclick=e=>{nextBefore(e);addAnnouncement({remaining:2})};
                }""")
                first = await aplicar(page, config(), 3500, AsyncMock())
                second = await siguiente(page, first, 3500, AsyncMock())
                assert second['active'] == 2 and not second['next']
                assert await page.evaluate('popupCounts') == {'closed':4,'business':0,'search':1,'next':1}
                assert not await overlays.blocking_background(page)
            finally:
                await browser.close()
    asyncio.run(run())


def test_announcements_after_login_and_network(monkeypatch):
    async def run():
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            context = await browser.new_context()
            closed = []
            await context.expose_function('trackClose', lambda: closed.append(True))
            await simulador(context, RECORDS)
            # La ruta superior solo instrumenta páginas autenticadas sintéticas.
            async def route(route):
                if 'synthetic_session=1' not in route.request.headers.get('cookie',''):
                    await route.fallback()
                    return
                script = '<script>(' + SCRIPT + ')();addAnnouncement();document.querySelector(".modern-close-btn").addEventListener("click",()=>trackClose());</script>'
                await route.fulfill(status=200,content_type='text/html',body=html(RECORDS)+script)
            await context.route('**/*', route)
            try:
                assert await autenticar(context, 3500) == 'authenticated'
                assert len(closed) == 2
                assert not context.pages
            finally:
                await browser.close()
    asyncio.run(run())


@pytest.mark.parametrize('stage', ['before-search','pagination'])
def test_incomplete_capture_never_applies_absences(tmp_path, stage):
    key = identidad(config())
    cfg = WasiConfig(db=str(tmp_path/'wasi.sqlite'), url=key, urls=[key], searches={key:config()}, timeout=2000, delay=.5)
    store = WasiStore(cfg.db)
    previous = descubrir(store, {key:[item('999')]})
    store.result(previous,'999','success',documento('999'))
    store.update_run(previous,status='completed')
    assert store.finalize_absences(previous)
    with store.connect() as db:
        before = tuple(db.execute("SELECT * FROM search_memberships WHERE property_id='999'").fetchone())

    class Synthetic(WasiScraper):
        async def prepare_context(self, context):
            pass
        async def abrir(self, context, config):
            page = await context.new_page()
            await page.route('**/*',lambda route:route.abort())
            await page.set_content(html(RECORDS))
            await page.evaluate(SCRIPT)
            if stage == 'before-search':
                await page.evaluate("addAnnouncement({mode:'residual-background'})")
            else:
                # Aparece entre preparación y clic: interceptación normal en Siguiente.
                async def pace():
                    if await page.evaluate('popupCounts.search'):
                        await page.evaluate("addAnnouncement({mode:'stuck'})")
                self.pace = pace
            try:
                batch = await aplicar(page, config, self.cfg.timeout, AsyncMock())
                return page, batch
            except BaseException:
                await page.close()
                raise
        async def process_details(self, context):
            pass  # Diagnóstico del listado aislado, sin fichas.

    scraper = Synthetic(cfg)
    summary = asyncio.run(scraper.run())
    assert summary['status'] == 'incomplete' and not summary['listing_complete']
    assert summary['pages'] == (0 if stage == 'before-search' else 1)
    with store.connect() as db:
        assert tuple(db.execute("SELECT * FROM search_memberships WHERE property_id='999'").fetchone()) == before
        assert db.execute('SELECT absence_applied FROM run_searches WHERE run_id=?',(summary['id'],)).fetchone()[0] == 0
    from ejecuciones.worker import metrics
    assert metrics(scraper)['listing_error_count'] == 1
