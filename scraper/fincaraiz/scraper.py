"""Tercera fuente sobre el motor incremental común de Radar."""
import asyncio
import hashlib
import json
import os
from dataclasses import dataclass, field
from catalogo.fuentes.fincaraiz import identidad
from metro.scraper import Scraper, Config, DEFAULT_URL
from metro.storage import Store
from metro.extraction import ExtractionError, Restricted
from .browser import leer, listado, siguiente
from .extraction import normalizar


class FincaraizStore(Store):
    def __init__(self, path):
        super().__init__(path, normalizar_busqueda=identidad)

    def result(self, run_id, property_id, status, data=None, error=None):
        if status == 'success' and data:
            with self.connect() as db:
                row = db.execute('SELECT data_json FROM properties WHERE id=?', (property_id,)).fetchone()
            previous_doc = json.loads(row[0]) if row and row[0] else {}
            previous = previous_doc.get('normalized', {})
            missing = [k for k, v in previous.items() if v is not None and k in data['normalized'] and data['normalized'][k] is None]
            if previous_doc.get('photos') and not data.get('photos'):
                missing.append('photos')
            if missing:
                data['quality'] = status = 'partial'
                data['errors'].extend({'field': k, 'error': 'Dato antes disponible ausente; se conserva la ficha fiable anterior'} for k in missing)
        return super().result(run_id, property_id, status, data, error)


@dataclass
class FincaraizConfig(Config):
    searches: dict = field(default_factory=dict)
    concurrency: int = 1

    def validate(self):
        Config(url=DEFAULT_URL, concurrency=self.concurrency, delay=self.delay, timeout=self.timeout,
               retries=self.retries, max_pages=self.max_pages, max_details=self.max_details,
               resource_interval=self.resource_interval).validate()
        if not self.searches and not self.resume:
            raise ValueError('No hay búsquedas activas de Fincaraíz')
        for key, c in self.searches.items():
            if identidad(c['url_efectiva']) != key or not isinstance(c.get('filtros'), dict):
                raise ValueError('Configuración de Fincaraíz inconsistente')


class FincaraizScraper(Scraper):
    store_type = FincaraizStore

    def __init__(self, config):
        super().__init__(config)
        if config.resume:
            config.searches = json.loads(self.store.run(config.resume)['config_json'])['searches']
        self.publicados = {}

    async def goto(self, page, url):
        # Backoff acotado, manteniendo el control común de bloqueo/CAPTCHA.
        for attempt in range(self.cfg.retries + 1):
            try:
                from metro.scraper import check_access
                await self.pace()
                response = await page.goto(url, wait_until='domcontentloaded', timeout=self.cfg.timeout)
                await check_access(page, response)
                return
            except Restricted:
                raise
            except Exception:
                if attempt == self.cfg.retries:
                    raise
                await asyncio.sleep(min(2 ** attempt, 8))

    async def discover(self, context, source_url=None):
        key = identidad(source_url or self.cfg.url)
        search = next(s for s in self.store.searches(self.run_id) if s['search_url'] == key)
        if search['listing_complete']:
            return
        config = self.cfg.searches[key]
        saved = self.store.pages(self.run_id, key)
        page = await context.new_page()
        try:
            url, number, seen, fingerprints = config['url_efectiva'], 1, set(), set()
            total = None
            while not self.stopping.is_set():
                await self.goto(page, url)
                filters, links, info = listado(await leer(page))
                if filters != config['filtros'] or info['currentPage'] != number:
                    raise ExtractionError('El portal no conserva filtros o página esperados')
                if total is not None and total != info['total']:
                    raise ExtractionError('El total cambió durante el recorrido')
                total = info['total']
                self.store.update_search(self.run_id, key, advertised={'totalHits': total, 'source': 'fincaraiz.searchFast'})
                fp = hashlib.sha256(json.dumps([(l['id'], l['raw']['businessType'], l['raw'].get('mvalorventa'), l['raw'].get('mvalorarriendo')) for l in links], sort_keys=True).encode()).hexdigest()
                ids = {i['id'] for i in links}
                if fp in fingerprints or (links and not ids - seen):
                    raise ExtractionError('Página repetida o sin progreso')
                fingerprints.add(fp); seen.update(ids)
                next_url = await siguiente(page, config['url_efectiva'], info)
                if number <= len(saved):
                    if fp != saved[number - 1]['fingerprint']:
                        raise ExtractionError('Cambió el listado desde el checkpoint; inicia una nueva ejecución')
                else:
                    self.store.save_page(self.run_id, number, str(number), page.url, fp, links,
                                         {'url': next_url} if next_url else None, search_url=key)
                for l in links:
                    self.publicados[l['id']] = l['raw']['fincaraiz']
                self.event('fincaraiz_page_saved', {'source': key, 'page': number, 'results': len(links)})
                if next_url is None:
                    if len(seen) != total or number != max(1, info['lastPage']) or len(saved) > number:
                        raise ExtractionError('Cobertura incompleta: no se confirman ausencias')
                    self.store.update_search(self.run_id, key, complete=True)
                    break
                if self.cfg.max_pages and number >= self.cfg.max_pages:
                    break
                url, number = next_url, number + 1
        finally:
            await page.close()

    async def detail(self, context, job):
        page = None
        try:
            for attempt in range(job['attempts'], self.cfg.retries + 1):
                if self.stopping.is_set():
                    return
                self.store.attempt(self.run_id, job['property_id'])
                try:
                    raw = self.publicados.get(job['property_id'])
                    # El listado inspeccionado ya incluye ficha técnica, originales e imágenes.
                    sufficient = raw and raw.get('technicalSheet') and raw.get('description') and isinstance(raw.get('images'), list)
                    if not sufficient:
                        if page is None:
                            page = await context.new_page()
                        await self.goto(page, job['url'])
                        pp = await leer(page)
                        raw = pp.get('data')
                        if not isinstance(raw, dict):
                            raise ExtractionError('Ficha pública ausente')
                        raw = {**raw, 'technicalSheet': pp.get('technicalSheet', raw.get('technicalSheet', []))}
                    data = normalizar(raw, job['url'])
                    self.store.validate_detail_price(self.run_id, job['property_id'], data)
                    self.store.result(self.run_id, job['property_id'], data['quality'], data)
                    return
                except Restricted:
                    self.store.result(self.run_id, job['property_id'], 'blocked', error='fincaraiz_access_blocked')
                    self.stopping.set(); return
                except Exception as exc:
                    self.store.result(self.run_id, job['property_id'], 'failed', error=type(exc).__name__)
                    if attempt < self.cfg.retries:
                        await asyncio.sleep(min(2 ** attempt, 8))
        finally:
            if page:
                await page.close()

    async def update_matching(self):
        from oportunidades.automatizacion import despues_scraper
        from metro.paths import DEFAULT_DB
        await asyncio.to_thread(despues_scraper, os.getenv('METRO_DB', str(DEFAULT_DB)))
