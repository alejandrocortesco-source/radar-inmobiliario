import asyncio,json
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
from playwright.async_api import async_playwright
from wasi.diagnostico import Diagnostic,current,step
from wasi.browser import seleccionar,lote,cambio,_validation_failure
from wasi.auth import acceso
from wasi.overlays import prepare_interaction
from metro.extraction import ExtractionError
from test_wasi_announcements import setup_page

@pytest.mark.parametrize('case', ['filter','summary','popup','no_refresh','invalid_table','pagination','auth','unexpected','evidence_failure','popup_recovered','empty'])
def test_precise_stages_and_privacy(case):
 async def run():
  records=[]
  scraper=SimpleNamespace(run_id=7,cfg=SimpleNamespace(url='wasi:synthetic'),event=lambda kind,record,*args:records.append(dict(record)))
  diag=Diagnostic(scraper);token=current.set(diag)
  async with async_playwright() as p:
   browser=await p.chromium.launch()
   page=await setup_page(browser)
   try:
    if case=='evidence_failure':
     page.evaluate=AsyncMock(side_effect=RuntimeError('PASSWORD=secret COOKIE=secret'))
    async def operation():
     if case=='filter':return await seleccionar(page,'id_ciudad','999','No existe',80)
     if case=='summary':raise ExtractionError('Resumen no coincide SECRET_TOKEN')
     if case=='popup':
      await page.evaluate("addAnnouncement({mode:'unknown'})")
      return await prepare_interaction(page,page.locator('#advanced_search'),100)
     if case=='no_refresh':return await cambio(page,'#properties_table tbody',lambda:asyncio.sleep(0),80)
     if case in {'invalid_table','pagination'}:return await lote(page,80,active=99)
     if case=='auth':
      await page.set_content('<form id="login-form"><input value="synthetic"></form>')
      return await acceso(page)
     if case in {'unexpected','evidence_failure'}:raise RuntimeError('Authorization=SECRET_TOKEN')
     if case=='popup_recovered':
      await page.evaluate("addAnnouncement({mode:'normal'})")
      return await prepare_interaction(page,page.locator('#advanced_search'),2000)
     if case=='empty':
      await page.set_content('<button id="advanced_search">Buscar</button><div id="properties_table_info">0 a 0 de 0 inmuebles</div><table id="properties_table"><tbody></tbody></table>')
      return await lote(page,200)
    if case in {'popup_recovered','empty'}:
     result=await step(case,'operación sintética',operation(),page,200)
     if case=='empty':assert result['total']==0
     diag.finish(True)
     assert not any(r.get('outcome')=='failed' for r in records)
    else:
     with pytest.raises(Exception):await step(case,'operación sintética',operation(),page,80)
     diag.finish(False)
     record=records[-1];assert record['stage']==case and record['outcome']=='failed'
     assert record['duration_ms']>=0 and record['attempt']==1 and record['affects_result']
     assert record['code']==case+'_unverified' or record['code'].startswith('wasi_')
     assert 'SECRET_TOKEN' not in json.dumps(records) and 'PASSWORD' not in json.dumps(records)
     assert record.get('observed') is not None
   finally:
    current.reset(token);await browser.close()
 asyncio.run(run())
