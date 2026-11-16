"""Códigos fijos: nunca contienen HTML, valores de filtros ni errores de Playwright."""
from metro.extraction import ExtractionError

MESSAGES = {
    'wasi_search_overlay': 'Listado no obtenido: una ventana del portal bloqueó el botón Buscar.',
    'wasi_overlay_unclosable': 'Listado incompleto: el anuncio de ProductFruits o su fondo no pudieron despejarse de forma segura.',
    'wasi_search_unconfirmed': 'Listado no obtenido: no se pudo confirmar el botón Buscar.',
    'wasi_overlay_ambiguous': 'Listado incompleto: anuncio ProductFruits sin un único cierre visible y reconocido.',
    'wasi_overlay_limit': 'Listado incompleto: se alcanzó el límite de cierres o tiempo de anuncios ProductFruits.',
    'wasi_interaction_blocked': 'Listado incompleto: una ventana desconocida o un control no disponible impide continuar.',
    'wasi_interaction_uncertain': 'Listado incompleto: no se pudo confirmar si la interacción terminó; no se repitió para evitar duplicados.',
    'wasi_listing_unverified': 'Listado incompleto: no se pudieron confirmar los filtros o la cobertura del portal.',
}

class WasiListingError(ExtractionError):
    def __init__(self, code):
        self.wasi_code = code if code in MESSAGES else 'wasi_listing_unverified'
        super().__init__(MESSAGES[self.wasi_code])


# Contexto por tarea del scraper; sin cambios en las decisiones del navegador.
import contextvars
import time
import json
import os
import re
from datetime import datetime, timezone, timedelta
from urllib.parse import urlsplit

current = contextvars.ContextVar('wasi_diagnostic', default=None)

class Diagnostic:
    def __init__(self, scraper):
        self.scraper = scraper
        self.last = None
        self.records = []
        self.attempts = {}
        self.failures = 0
        self.active = []
        self.network = []

    def emit(self, record):
        try:
            self.scraper.event('wasi_diagnostic', record, 'warning' if record.get('outcome')=='failed' else 'info')
        except Exception:
            pass  # Nunca sustituye el error del portal.

    async def observe(self, page, selector=None, expected=None):
        result = {'visual_omitted':'viewport puede contener datos personales; solo control de filtro permitido'}
        if page is None:
            return result
        try:
            u=urlsplit(page.url)
            result['path']=u.path if u.hostname=='wasi.co' and u.path in {'/usuario/inmuebles/red','/login-usuario.htm'} else 'other_path'
            result['dom']=await page.evaluate(r"""() => ({
              mutationCounter:document.querySelector('#properties_table tbody')?.__radarVersion ?? null,
              summaryTokens:['Colombia','Cundinamarca','Bogotá','Usaquén','La Carolina','Apartamento','Vender'].filter(t=>(document.querySelector('#title_filter')?.textContent||'').includes(t)),
              rows:document.querySelectorAll('#properties_table tbody tr[id]').length,
              ids:[...document.querySelectorAll('#properties_table tbody tr[id]')].slice(0,100).map(e=>e.id).filter(x=>/^\d+$/.test(x)),
              active:(document.querySelector('#properties_table_paginate .current')?.textContent||'').replace(/[^0-9]/g,'').slice(0,6),
              nextDisabled:document.querySelector('#properties_table_next')?.classList.contains('disabled'),
              processing:!!document.querySelector('#properties_table_processing')?.getClientRects().length,
              login:!!document.querySelector('#login-form'),
              dialogCount:[...document.querySelectorAll('[role=dialog]')].filter(e=>e.getClientRects().length).length,
              recognizedAnnouncement:!!document.querySelector('.pfruits-announcement-popup-v3[role=dialog]'),
              security:!!document.querySelector('iframe[src*=recaptcha],iframe[src*=hcaptcha],input[autocomplete=one-time-code]')})""")
            if selector:
                node=page.locator(selector)
                count=await node.count()
                result['control']={'count':count}
                if count==1:
                    result['control'].update(visible=await node.is_visible(),enabled=await node.is_enabled(timeout=500))
                    if expected is not None:
                        actual=await node.input_value(timeout=500)
                        # Valores numéricos de filtros; texto libre solo igualdad/longitud.
                        safe=lambda x:x if re.fullmatch(r'[0-9]{0,12}',str(x)) else {'length':len(str(x))}
                        result['filter']={'expected':safe(expected),'actual':safe(actual),'equal':actual==expected}
                    result['control']['options']=await node.evaluate("e=>[...(e.options||[])].slice(0,60).map(o=>o.value).filter(v=>/^[0-9]{0,12}$/.test(v))")
                    result['control']['hit']=await node.evaluate("""e=>{const r=e.getBoundingClientRect(),t=document.elementFromPoint(r.x+r.width/2,r.y+r.height/2);return !t?'outside':t===e||e.contains(t)?'self':t.closest('.productfruits--container,.productfruits--container-root')?'productfruits':'other'}""")
            result['network']=self.network[-12:]
        except Exception as exc:
            result['observation_error']=type(exc).__name__
        return result

    async def save_failure(self, record, page, selector):
        self.failures+=1
        if self.failures>8:
            return
        try:
            record['observed']=await self.observe(page,selector)
        except Exception as auxiliary:
            record['observation_error']=type(auxiliary).__name__
        record['cause']=record['code'] if record['exception']!='unexpected' else 'causa_no_determinada'
        # Artefacto privado JSON; captura visual solo del select fijo, nunca login/fichas.
        try:
            from google.cloud import storage
            if not os.getenv('K_SERVICE') and not os.getenv('CLOUD_RUN_JOB'):
                return
            client=storage.Client();bucket=client.bucket(os.environ['RADAR_STATE_BUCKET'])
            prefix='radar/diagnostics/wasi/'+os.environ.get('RADAR_RUN_ID',os.environ.get('CLOUD_RUN_EXECUTION','unknown'))+'/'
            name=prefix+str(self.failures)+'.json'
            record['artifact']='gs://'+bucket.name+'/'+name
            days=max(1,min(90,int(os.getenv('WASI_DIAGNOSTIC_DAYS','14'))))
            record['expires_at']=(datetime.now(timezone.utc)+timedelta(days=days)).isoformat()
            raw=json.dumps(record,ensure_ascii=True).encode()
            if len(raw)>32768:raise ValueError('diagnostic_size_limit')
            import asyncio
            await asyncio.to_thread(bucket.blob(name).upload_from_string,raw,content_type='application/json',if_generation_match=0,timeout=10)
            # Solo select numérico conocido: no viewport de cuenta, login o fichas.
            if page is not None and selector and selector.startswith('.advanced-search #') and record.get('before',{}).get('filter',{}).get('equal') is not None:
                node=page.locator(selector)
                tag=await node.evaluate('e=>e.tagName')
                if tag=='SELECT':
                    image=await node.screenshot(timeout=1000)
                    if len(image)<=100000:
                        image_name=prefix+str(self.failures)+'.png'
                        await asyncio.to_thread(bucket.blob(image_name).upload_from_string,image,content_type='image/png',if_generation_match=0,timeout=10)
                        record['visual_artifact']='gs://'+bucket.name+'/'+image_name
            # Retención específica por referencias propias, sin listar ni cambiar lifecycle.
            with self.scraper.store.connect() as db:
                rows=db.execute("SELECT id,context_json FROM events WHERE kind='wasi_diagnostic' AND time<? ORDER BY id LIMIT 100",((datetime.now(timezone.utc)-timedelta(days=days)).isoformat(),)).fetchall()
                for row in rows:
                    old=json.loads(row[1]);expiry=old.get('expires_at')
                    if expiry and datetime.fromisoformat(expiry)<datetime.now(timezone.utc):
                        for field in ('artifact','visual_artifact'):
                            ref=old.get(field,'');base='gs://'+bucket.name+'/radar/diagnostics/wasi/'
                            if ref.startswith(base):
                                try:
                                    await asyncio.to_thread(bucket.blob(ref.split(bucket.name+'/',1)[1]).delete,timeout=5)
                                except Exception as cleanup:
                                    if type(cleanup).__name__!='NotFound':raise
                        db.execute("DELETE FROM events WHERE id=? AND kind='wasi_diagnostic'",(row[0],))
        except Exception as exc:
            record['artifact_error']=type(exc).__name__

    async def step(self, stage, action, operation, page=None, timeout=None, selector=None, expected=None):
        self.attempts[stage]=self.attempts.get(stage,0)+1
        start=time.monotonic()
        record={'source':'wasi','radar_run':os.getenv('RADAR_RUN_ID'), 'worker':os.getenv('CLOUD_RUN_EXECUTION'),
                'technical_run':self.scraper.run_id,'search':self.scraper.cfg.url,
                'stage':stage,'last_completed':self.last,'started':datetime.now(timezone.utc).isoformat(),
                'timeout_ms':timeout,'action':action,'expected':'operación y validación de '+stage,
                'attempt':self.attempts[stage]}
        before=await self.observe(page,selector,expected) if page is not None and stage.startswith(('table_refresh','search_click','filter','summary')) else None
        if stage=='table_refresh':self.table_before=before
        if stage=='table_mutation':before=getattr(self,'table_before',before)
        try:
            value=await operation
        except Exception as exc:
            if not getattr(exc,'wasi_diagnosed',False):
                record.update(outcome='failed',duration_ms=round((time.monotonic()-start)*1000),
                    code=getattr(exc,'wasi_code',None) or stage+'_unverified',
                    exception=('timeout' if 'Timeout' in type(exc).__name__ else 'validation' if isinstance(exc,ExtractionError) else 'unexpected'),
                    exception_type=type(exc).__name__,message='No se confirmó la condición de la etapa; mensaje original omitido por privacidad.',
                    before=before,recovered=False)
                import asyncio
                try:
                    await asyncio.wait_for(self.save_failure(record,page,selector),timeout=15)
                except Exception as auxiliary:
                    record['artifact_error']=type(auxiliary).__name__
                if self.failures<=8:
                    self.records.append(record);self.emit(record)
                exc.wasi_diagnosed=True
            raise
        else:
            self.last=stage
            self.records.append(dict(record,outcome='completed',duration_ms=round((time.monotonic()-start)*1000)))
            self.records=[r for r in self.records if r['outcome']=='failed'][-8:]+[r for r in self.records if r['outcome']=='recovered'][-8:]+[r for r in self.records if r['outcome']=='completed'][-84:]
            return value

    def finish(self, success):
        for record in self.records:
            if record['outcome']=='failed':
                record.update(recovered=success,affects_result=not success)
                self.emit(record)
        if success:
            self.emit({'source':'wasi','stage':'listing_complete','outcome':'completed','last_completed':self.last,'recovered':any(r['outcome'] in {'failed','recovered'} for r in self.records)})

async def step(stage, action, operation, page=None, timeout=None, selector=None, expected=None):
    diagnostic=current.get()
    if diagnostic is None:
        return await operation
    return await diagnostic.step(stage,action,operation,page,timeout,selector,expected)


async def failed(stage,page,timeout,exc):
    async def again():
        raise exc
    try:
        await step(stage,'operación del navegador',again(),page,timeout)
    except Exception:
        pass
