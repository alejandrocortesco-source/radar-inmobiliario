import asyncio
import json
import logging
import random
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.parse import urlsplit

from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout

from .extraction import (ExtractionError, Restricted, detail_from_records, fingerprint,
                         flight_records, listing_from_records, listing_links,
                         normalize_detail, sanitize)
from .storage import Store, dumps, now
from .paths import DEFAULT_DB
from .resource_monitor import ResourceMonitor, print_summary
from .prices import search_identity, listing_price, same_price

log = logging.getLogger('metro')
DEFAULT_URL = 'https://www.metrocuadrado.com/inmuebles/venta/bogota/la-carolina?search=form'


@dataclass
class Config:
    url: str = DEFAULT_URL
    db: str = str(DEFAULT_DB)
    headed: bool = False
    concurrency: int = 2
    delay: float = 1.5
    timeout: int = 45000
    retries: int = 2
    max_pages: int | None = None
    max_details: int | None = None
    resume: int | None = None
    metrics_dir: str | None = None
    resource_interval: float = 0.2
    urls: list[str] | None = None
    listing_currency: str | None = 'COP'  # Confirmado por el usuario para estas búsquedas.

    def validate(self):
        for url in self.urls or [self.url]:
            if urlsplit(url).hostname not in ('www.metrocuadrado.com','metrocuadrado.com') or urlsplit(url).scheme not in ('http','https'):
                raise ValueError('Sólo URLs HTTP(S) de Metrocuadrado')
        if self.listing_currency not in (None,'COP','USD','EUR'):
            raise ValueError('Moneda de listado no compatible')
        if not 1 <= self.concurrency <= 4 or self.delay < 0.5 or self.timeout < 1000 or not 0 <= self.retries <= 5:
            raise ValueError('Concurrencia 1–4, pausa >=0.5, timeout >=1000 y reintentos 0–5')
        if any(v is not None and v < 1 for v in (self.max_pages,self.max_details)):
            raise ValueError('Los límites de prueba deben ser positivos')
        import math
        if not math.isfinite(self.resource_interval) or not 0.05 <= self.resource_interval <= 60:
            raise ValueError('Intervalo de recursos entre 0.05 y 60 segundos')


async def check_access(page, response=None):
    if response and response.status in (401,403,429):
        raise Restricted(f'Acceso restringido HTTP {response.status}')
    if response and response.status >= 400:
        raise ExtractionError(f'HTTP {response.status}')
    title = (await page.title()).lower()
    text = (await page.locator('body').inner_text(timeout=5000)).lower()
    markers = ('verify you are human','verifica que eres humano','access denied','request blocked',
               'unusual traffic','just a moment','comprueba que eres humano')
    if any(x in title or x in text for x in markers):
        raise Restricted('CAPTCHA o página de bloqueo detectada')
    # Los scripts recaptcha normales del sitio no equivalen a un desafío visible.
    challenge = page.locator('iframe[src*="captcha"]').filter(visible=True)
    if await challenge.count():
        raise Restricted('Desafío CAPTCHA visible')


async def records(page):
    return flight_records(await page.locator('script:not([src])').all_text_contents())


async def wait_data(page, extract, timeout):
    deadline = time.monotonic() + timeout/1000
    last = None
    while time.monotonic() < deadline:
        await check_access(page)
        try:
            return extract(await records(page))
        except ExtractionError as exc:
            last = exc
        await asyncio.sleep(0.3)
    raise ExtractionError(f'Tiempo agotado esperando datos públicos: {last}')


class Scraper:
    def __init__(self, config):
        config.validate()
        self.cfg = config
        self.store = Store(config.db)
        self.stopping = asyncio.Event()
        self.rate_lock = asyncio.Lock()
        self.next_request = 0.0
        self.run_id = config.resume

    def event(self, kind, context, level='info'):
        self.store.event(self.run_id,kind,sanitize(context),level)
        log.log(logging.ERROR if level == 'error' else logging.INFO,'%s %s',kind,dumps(sanitize(context)))

    async def pace(self):
        async with self.rate_lock:
            await asyncio.sleep(max(0,self.next_request-time.monotonic()))
            self.next_request = time.monotonic()+self.cfg.delay+random.uniform(0,self.cfg.delay/2)

    async def goto(self, page, url):
        for attempt in range(self.cfg.retries+1):
            await self.pace()
            try:
                response = await page.goto(url,wait_until='domcontentloaded',timeout=self.cfg.timeout)
                await check_access(page,response)
                return
            except Restricted:
                raise
            except Exception as exc:
                self.event('navigation_retry',{'url':url,'attempt':attempt+1,'error':str(exc)[:1000]},'error')
                if attempt == self.cfg.retries:
                    raise

    async def ready_listing(self,page):
        await page.evaluate('window.scrollTo(0, document.body.scrollHeight / 2)')
        await page.locator('.rc-pagination-item-active').wait_for(state='attached',timeout=self.cfg.timeout)
        await page.locator('.property-list__results a[href*="/inmueble/"]').first.wait_for(state='attached',timeout=self.cfg.timeout)

    async def advance(self, page, captures, previous):
        old_active = (await page.locator('.rc-pagination-item-active').inner_text()).strip()
        captures.clear()
        await page.locator('.rc-pagination-next').scroll_into_view_if_needed()
        # Click normal: si hay un muro/modal se registra, no se fuerza a través de él.
        await self.pace()
        await page.locator('.rc-pagination-next').click(timeout=self.cfg.timeout)
        deadline = time.monotonic()+self.cfg.timeout/1000
        while time.monotonic() < deadline:
            await check_access(page)
            active = page.locator('.rc-pagination-item-active')
            new_active = (await active.inner_text()).strip() if await active.count() else None
            if new_active and new_active != old_active and captures:
                batch = captures[-1]
                if fingerprint(batch) != previous:
                    self.event('pagination_verified',{'from':old_active,'to':new_active,
                                                      'results':len(batch['results'])})
                    return batch
            await asyncio.sleep(0.3)
        raise ExtractionError('Paginador sin cambio confirmado de página activa e identificadores')

    async def discover(self, context, source_url=None):
        source_url = source_url or self.cfg.url
        search_url = search_identity(source_url)
        saved = self.store.pages(self.run_id,search_url)
        search = next(s for s in self.store.searches(self.run_id) if s['search_url']==search_url)
        if search['listing_complete']:
            return
        page = await context.new_page()
        captures = []
        async def capture(response):
            if urlsplit(response.url).hostname == 'www.metrocuadrado.com' and urlsplit(response.url).path == '/rest-search/search':
                try:
                    data = await response.json()
                    if isinstance(data,dict) and isinstance(data.get('results'),list):
                        captures.append(sanitize(data))
                except Exception as exc:
                    self.event('response_parse_error',{'error':str(exc)[:500]},'error')
        page.on('response',capture)
        try:
            await self.goto(page,source_url)
            batch = await wait_data(page,listing_from_records,self.cfg.timeout)
            advertised = {
                'totalHits':batch.get('totalHits'),'totalEntries':batch.get('totalEntries'),
                'source':'flight.initialResults'}
            self.store.update_search(self.run_id,search_url,advertised=advertised)
            if batch.get('results') == [] and batch.get('highlights') in (None,[]) and batch.get('totalHits') == batch.get('totalEntries') == 0:
                if saved:
                    raise ExtractionError('El listado cambió a vacío desde el checkpoint; cree otra ejecución')
                self.store.save_page(self.run_id,1,'1',page.url,'empty',[],None,search_url=search_url)
                self.store.update_search(self.run_id,search_url,complete=True)
                self.event('empty_search_verified',{'search_url':search_url,'source':'initialResults totals=0'})
                return
            # El consentimiento observado cubre el paginador. No envía formularios.
            accept = page.get_by_text('Aceptar',exact=True)
            if await accept.count() and await accept.first.is_visible():
                await accept.first.click(timeout=5000)
            await self.ready_listing(page)
            seen = set()
            number = 1
            while not self.stopping.is_set():
                fp = fingerprint(batch)
                if fp in seen:
                    raise ExtractionError('Página de resultados repetida; se detiene el bucle')
                seen.add(fp)
                active = (await page.locator('.rc-pagination-item-active').inner_text()).strip()
                if active != str(number):
                    raise ExtractionError(f'Página activa inesperada: {active}, esperada {number}')
                links = listing_links(batch)
                if not batch['results']:
                    raise ExtractionError('Listado vacío inesperado; no se declara completo')
                # El DOM virtualizado sólo ofrece una muestra; se verifica contra el JSON.
                dom_links = await page.locator('.property-list__results a[href*="/inmueble/"]').evaluate_all('(els)=>els.map(e=>e.href.split("?")[0])')
                if not dom_links or not set(dom_links) <= {x['url'] for x in links}:
                    raise ExtractionError('DOM y respuesta de resultados no coinciden')
                next_node = page.locator('.rc-pagination-next')
                if await next_node.count() != 1:
                    raise ExtractionError('Paginador siguiente ausente o ambiguo')
                disabled = await next_node.get_attribute('aria-disabled') == 'true'
                next_action = None if disabled else {'kind':'click','selector':'.rc-pagination-next','active':active}
                if number <= len(saved):
                    if saved[number-1]['fingerprint'] != fp:
                        raise ExtractionError('La búsqueda cambió desde el checkpoint. Cree una nueva ejecución para evitar omisiones.')
                    old_links = json.loads(saved[number-1]['links_json'])
                    old_prices = {x['id']:listing_price(x,self.cfg.listing_currency) for x in old_links}
                    for item in links:
                        current = listing_price(item,self.cfg.listing_currency)
                        previous = old_prices.get(item['id'])
                        equal = same_price(previous,current) if previous and previous.get('status') == current.get('status') == 'valid' else previous == current
                        if not equal:
                            raise ExtractionError('Cambió un precio desde el checkpoint; cree otra ejecución')
                    self.event('checkpoint_replayed',{'page':number})
                else:
                    self.store.save_page(self.run_id,number,active,page.url,fp,links,next_action,search_url=search_url)
                    self.event('page_saved',{'page':number,'links':len(links),'main_results':len(batch['results']),
                                             'ignored_recommended':len(batch.get('recommended') or [])})
                if disabled:
                    # Sólo el botón deshabilitado confirmado marca fin del listado.
                    main_ids = {x['id'] for stored in self.store.pages(self.run_id,search_url)
                                for x in json.loads(stored['links_json']) if x.get('group')=='results'}
                    expected = advertised['totalHits']
                    if isinstance(expected,int) and not isinstance(expected,bool) and len(main_ids) != expected:
                        raise ExtractionError(f'Cobertura incompleta: {len(main_ids)} identificadores principales frente a {expected} anunciados')
                    self.store.update_search(self.run_id,search_url,complete=True)
                    break
                if self.cfg.max_pages and number >= self.cfg.max_pages:
                    self.event('page_limit',{'limit':self.cfg.max_pages})
                    break
                batch = await self.advance(page,captures,fp)
                number += 1
        finally:
            await page.close()

    async def detail(self, context, job):
        page = await context.new_page()
        try:
            for _ in range(job['attempts'],self.cfg.retries+1):
                if self.stopping.is_set():
                    return
                self.store.attempt(self.run_id,job['property_id'])
                try:
                    # Cada intento de ficha tiene una sola navegación; límite total persistente.
                    await self.pace()
                    response = await page.goto(job['url'],wait_until='domcontentloaded',timeout=self.cfg.timeout)
                    await check_access(page,response)
                    raw = await wait_data(page,lambda r:detail_from_records(r,job['property_id']),self.cfg.timeout)
                    visible = await page.locator('body').inner_text()
                    ld = []
                    for text in await page.locator('script[type="application/ld+json"]').all_text_contents():
                        try:
                            ld.append(json.loads(text))
                        except ValueError:
                            self.event('invalid_json_ld',{'id':job['property_id']},'error')
                    media = await page.evaluate('''(id)=>({
                      photos:[...document.querySelectorAll('img')].map(e=>e.currentSrc||e.src).filter(s=>s.includes('/'+id+'/')),
                      videos:[...document.querySelectorAll('video,video source')].map(e=>e.src).filter(Boolean),
                      embeds:[...document.querySelectorAll('iframe[src]')].map(e=>e.src).filter(s=>/youtube|vimeo|matterport|tour|360/i.test(s)&& !/captcha/i.test(s))
                    })''',job['property_id'])
                    data = normalize_detail(raw,job['url'],visible,ld,sanitize(media))
                    if not data['normalized']['title'] or not data['normalized']['description']:
                        data['quality']='partial'
                        data['errors'].append({'field':'core','error':'Título o descripción no disponibles'})
                    self.store.validate_detail_price(self.run_id,job['property_id'],data)
                    self.store.result(self.run_id,job['property_id'],data['quality'],data)
                    self.event('detail_saved',{'id':job['property_id'],'quality':data['quality'],
                                               'photos':len(data['photos'])})
                    return
                except Restricted as exc:
                    self.store.result(self.run_id,job['property_id'],'blocked',error=str(exc))
                    self.event('access_restricted',{'id':job['property_id'],'error':str(exc)},'error')
                    self.stopping.set()
                    return
                except Exception as exc:
                    self.store.result(self.run_id,job['property_id'],'failed',error=str(exc)[:2000])
                    self.event('detail_error',{'id':job['property_id'],'error':str(exc)[:1000]},'error')
        finally:
            await page.close()

    async def process_details(self, context):
        jobs = self.store.pending(self.run_id,self.cfg.retries+1)
        if self.cfg.max_details:
            jobs = jobs[:self.cfg.max_details]
        queue = asyncio.Queue()
        for job in jobs:
            queue.put_nowait(job)
        async def worker():
            while not self.stopping.is_set():
                try:
                    job = queue.get_nowait()
                except asyncio.QueueEmpty:
                    return
                await self.detail(context,job)
        await asyncio.gather(*(worker() for _ in range(self.cfg.concurrency)))

    async def run(self):
        # Envuelve la ejecución existente; no cambia descubrimiento ni extracción.
        monitor = None
        status = 'failed'
        try:
            try:
                monitor = ResourceMonitor(
                    self.cfg.metrics_dir or Path(self.cfg.db).resolve().parent/'metrics',
                    interval=self.cfg.resource_interval,
                ).start()
            except Exception as exc:
                log.warning('No se pudo iniciar el monitor de recursos: %s', exc)
            result = await self._run()
            status = result['status']
            return result
        except (KeyboardInterrupt, asyncio.CancelledError):
            status = 'interrupted'
            raise
        finally:
            if monitor:
                try:
                    self.resource_usage = monitor.finish(run_id=self.run_id, status=status, config=asdict(self.cfg))
                    print_summary(self.resource_usage, monitor.summary_path)
                except Exception as exc:
                    log.warning('No se pudo finalizar el monitor de recursos: %s', exc)

    async def _run(self):
        if self.run_id:
            run = self.store.run(self.run_id)
            self.cfg.url = run['url']
            self.cfg.urls = [s['source_url'] for s in self.store.searches(self.run_id)]
            previous_config = json.loads(run['config_json'])
            if 'listing_currency' in previous_config:
                self.cfg.listing_currency = previous_config['listing_currency']
            # Los intentos previos fallidos siguen contándose al reanudar.
            self.store.update_run(self.run_id,status='running',finished=None)
        else:
            self.run_id = self.store.new_run(self.cfg.url,asdict(self.cfg))
        print(f'Ejecución {self.run_id}',flush=True)
        self.event('run_started',{'resume':bool(self.cfg.resume),'effective_config':asdict(self.cfg)})
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=not self.cfg.headed)
                try:
                    context = await browser.new_context(locale='es-CO',viewport={'width':1366,'height':900})
                    async def resources(route):
                        if route.request.resource_type in ('image','media','font'):
                            await route.abort()
                        else:
                            await route.continue_()
                    await context.route('**/*',resources)
                    for search in self.store.searches(self.run_id):
                        try:
                            await self.discover(context,search['source_url'])
                        except Restricted:
                            raise
                        except Exception as exc:
                            # Una búsqueda incompleta impide contar ausencias en toda la ejecución.
                            self.event('listing_incomplete',{'search_url':search['search_url'],'error':str(exc)[:1500]},'error')
                    self.store.plan_incremental(self.run_id)
                    await self.process_details(context)
                finally:
                    await browser.close()
            summary = self.store.summary(self.run_id)
            good = sum(summary['statuses'].get(s,0) for s in ('success','unchanged'))
            status = 'blocked' if self.stopping.is_set() else (
                'completed' if summary['listing_complete'] and good == summary['unique'] and not summary['listing_conflicts'] else 'incomplete')
            self.store.update_run(self.run_id,status=status,finished=now())
            self.store.finalize_absences(self.run_id)
            self.event('incremental_summary',self.store.summary(self.run_id)['classifications'])
            self.event('run_finished',{'status':status})
        except Restricted as exc:
            self.store.update_run(self.run_id,status='blocked',finished=now())
            self.event('access_restricted',{'error':str(exc)},'error')
        except BaseException as exc:
            self.store.update_run(self.run_id,status='interrupted' if isinstance(exc,(KeyboardInterrupt,asyncio.CancelledError)) else 'failed',finished=now())
            self.event('run_error',{'type':type(exc).__name__,'error':str(exc)[:1000]},'error')
            if isinstance(exc,(KeyboardInterrupt,asyncio.CancelledError)):
                raise
        return self.store.summary(self.run_id)
