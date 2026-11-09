"""Wasi reutiliza cola, decisiones, historial, checkpoints y ausencias de Metro."""
import asyncio
import hashlib
import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from catalogo.fuentes.wasi import RED, identidad
from metro.scraper import Scraper, Config
from metro.storage import Store
from metro.prices import listing_price
from metro.extraction import ExtractionError, Restricted
from .auth import autenticar, acceso
from .browser import aplicar, lote, siguiente, ficha, contactos
from .extraction import normalizar


def identidad_tecnica(valor):
    if not isinstance(valor, str) or not valor.startswith('wasi:'):
        raise ValueError('Identidad técnica Wasi inválida')
    return valor


class WasiStore(Store):
    def __init__(self, path):
        super().__init__(path, normalizar_busqueda=identidad_tecnica)


@dataclass
class WasiConfig(Config):
    searches: dict = field(default_factory=dict)
    concurrency: int = 1

    def validate(self):
        # Reutiliza los límites operativos comunes sin pasar URLs Wasi por el
        # validador específico de Metrocuadrado.
        from metro.scraper import DEFAULT_URL
        Config(url=DEFAULT_URL, concurrency=self.concurrency, delay=self.delay,
               timeout=self.timeout, retries=self.retries, resource_interval=self.resource_interval).validate()
        if self.max_pages is not None or self.max_details is not None:
            raise ValueError('Wasi no admite límites de cobertura; utiliza filtros de negocio')
        if not self.searches and not self.resume:
            raise ValueError('No hay búsquedas Wasi registradas')
        for clave, config in self.searches.items():
            if identidad(config) != clave or not config['filtros'].get('id_ciudad') or not (config['filtros'].get('id_localidad') or config['filtros'].get('id_zona')):
                raise ValueError('Configuración Wasi inválida')


def huella(batch):
    return hashlib.sha256(json.dumps([(l['id'], listing_price(l, 'COP')) for l in batch['links']], sort_keys=True).encode()).hexdigest()


class WasiScraper(Scraper):
    store_type = WasiStore

    def __init__(self, config):
        if config.metrics_dir is None:
            config.metrics_dir = str(Path(config.db).resolve().parent / 'metrics' / 'wasi')
        super().__init__(config)
        if config.resume:
            original = json.loads(self.store.run(config.resume)['config_json'])
            config.searches = original['searches']
        self.contact_cache = {}

    async def prepare_context(self, context):
        # Fotorama elimina imágenes fallidas y puede mezclar la galería anterior.
        # Una imagen local vacía conserva su funcionamiento sin descargar fotos.
        async def imagen_local(route):
            if route.request.resource_type == 'image':
                await route.fulfill(status=200, content_type='image/svg+xml',
                    body='<svg xmlns="http://www.w3.org/2000/svg" width="800" height="600"/>')
            else:
                await route.fallback()
        await context.route('**/*', imagen_local)
        estado = await autenticar(context, self.cfg.timeout)
        self.event('wasi_auth', {'state': estado})

    async def abrir(self, context, config):
        page = await context.new_page()
        try:
            await self.pace()
            response = await page.goto(RED, wait_until='domcontentloaded', timeout=self.cfg.timeout)
            await acceso(page, response)
            batch = await aplicar(page, config, self.cfg.timeout, self.pace)
            return page, batch
        except BaseException:
            await page.close()
            raise

    async def discover(self, context, source_url=None):
        clave = source_url or self.cfg.url
        saved = self.store.pages(self.run_id, clave)
        search = next(s for s in self.store.searches(self.run_id) if s['search_url'] == clave)
        if search['listing_complete']:
            return
        page, batch = await self.abrir(context, self.cfg.searches[clave])
        try:
            self.store.update_search(self.run_id, clave, advertised={'totalHits': batch['total'], 'source': 'wasi.DOM'})
            vistos = set()
            while True:
                number = batch['active']
                fingerprint = huella(batch)
                ids = {l['id'] for l in batch['links']}
                if ids & vistos or (number == 1 and batch['start'] not in (0, 1)):
                    raise ExtractionError('Página Wasi repetida o cobertura inconsistente')
                vistos.update(ids)
                if number <= len(saved):
                    if fingerprint != saved[number - 1]['fingerprint']:
                        raise ExtractionError('Cambió el listado Wasi desde el checkpoint; inicia otra ejecución')
                    self.event('checkpoint_replayed', {'source': clave, 'page': number})
                else:
                    self.store.save_page(self.run_id, number, str(number), RED, fingerprint,
                                         batch['links'], {'next': True} if batch['next'] else None, search_url=clave)
                    self.event('wasi_page_saved', {'source': clave, 'page': number, 'results': len(batch['links'])})
                if not batch['next']:
                    if len(vistos) != batch['total'] or batch['end'] != batch['total'] or len(saved) > number:
                        raise ExtractionError('Cobertura Wasi incompleta; no se confirman ausencias')
                    self.store.update_search(self.run_id, clave, complete=True)
                    break
                batch = await siguiente(page, batch, self.cfg.timeout, self.pace)
        finally:
            await page.close()

    async def process_details(self, context):
        # Una segunda pasada de listados permite abrir únicamente los trabajos
        # globales decididos después de deduplicar todas las búsquedas. Con una
        # sesión compartida se procesan secuencialmente para evitar modales cruzados.
        pending = {j['property_id']: j for j in self.store.pending(self.run_id, self.cfg.retries + 1)}
        for clave, config in self.cfg.searches.items():
            if not pending or self.stopping.is_set():
                break
            saved = self.store.pages(self.run_id, clave)
            if not saved:
                continue
            page, batch = await self.abrir(context, config)
            try:
                while True:
                    number = batch['active']
                    if number > len(saved) or huella(batch) != saved[number-1]['fingerprint']:
                        raise ExtractionError('Listado Wasi cambió antes de capturar fichas; reanuda o inicia otra ejecución')
                    for item in batch['links']:
                        job = pending.get(item['id'])
                        if job is None:
                            continue
                        for _ in range(job['attempts'], self.cfg.retries + 1):
                            self.store.attempt(self.run_id, item['id'])
                            fase = 'detail'
                            try:
                                datos = await ficha(page, item['id'], self.cfg.timeout, self.pace)
                                fase = 'company'
                                empresa = item['raw']['wasi'].get('company_id')
                                # El endpoint del panel depende de empresa Y anuncio:
                                # otro inmueble puede tener otro agente, aunque este
                                # no lo tenga. Reutilizar únicamente la consulta exacta.
                                contacto_clave = (empresa, item['id'])
                                contacto = self.contact_cache.get(contacto_clave)
                                if contacto is None:
                                    contacto = await contactos(page, item['id'], self.cfg.timeout, self.pace)
                                    if contacto.get('name') != item['raw']['wasi'].get('company'):
                                        raise ExtractionError('El panel de empresa no corresponde al anunciante')
                                    self.contact_cache[contacto_clave] = contacto
                                fase = 'normalize'
                                data = normalizar(item['id'], datos, item, contacto)
                                self.store.validate_detail_price(self.run_id, item['id'], data)
                                self.store.result(self.run_id, item['id'], data['quality'], data)
                                self.event('wasi_detail_saved', {'id': item['id'], 'quality': data['quality'], 'photos': len(data['photos']), 'gallery_frames': datos.get('gallery_frames')})
                                break
                            except Restricted:
                                self.store.result(self.run_id, item['id'], 'blocked', error='wasi_access_blocked')
                                raise
                            except Exception as exc:
                                # Nada de HTML, request payloads ni excepciones
                                # Playwright potencialmente sensibles en evidencias.
                                self.store.result(self.run_id, item['id'], 'failed', error='wasi_' + fase + '_' + type(exc).__name__)
                                self.event('wasi_detail_error', {'id': item['id'], 'phase': fase, 'step': getattr(exc, 'wasi_step', None), 'error_type': type(exc).__name__}, 'error')
                                # Cierra modales de lectura antes del próximo intento.
                                for close in await page.locator('.modal:visible .top_close a, .modal:visible button.close').all():
                                    await close.click(timeout=self.cfg.timeout)
                        pending.pop(item['id'])
                    if not batch['next'] or not pending:
                        break
                    batch = await siguiente(page, batch, self.cfg.timeout, self.pace)
            finally:
                await page.close()

    async def update_matching(self):
        from oportunidades.automatizacion import despues_scraper
        from metro.paths import DEFAULT_DB
        await asyncio.to_thread(despues_scraper, os.getenv('METRO_DB', str(DEFAULT_DB)))
