import pytest
from fastapi.testclient import TestClient
from urllib.parse import urlsplit
from test_ejecuciones import execution,start
from metro.web import app

@pytest.mark.parametrize('width',[1440,768,390])
def test_detail_is_sane_and_responsive(execution,chromium,width):
 svc=execution[0];r=start(execution)
 b=r['searches'][0];b.update(status='partial',wasi_diagnostics=[dict(stage='filter:id_ciudad',message='No se confirmó la condición de la etapa.',code='filter_unverified',observed={'control':{'visible':True}},artifact='gs://synthetic/radar/diagnostics/wasi/test/1.json')])
 svc.control.patch(r['id'],dict(searches=[b],status='partial',finished=r['created']))
 client=TestClient(app);ctx=chromium.new_context(viewport={'width':width,'height':900});page=ctx.new_page()
 def route(route):
  req=route.request;u=urlsplit(req.url);res=client.request(req.method,u.path+('?' +u.query if u.query else ''),content=req.post_data_buffer)
  route.fulfill(status=res.status_code,headers={k:v for k,v in res.headers.items() if k.lower() not in {'content-length','content-encoding'}},body=res.content)
 page.route('**/*',route);page.goto('http://127.0.0.1/v0.6/ejecuciones?run='+r['id'])
 page.get_by_text('Detalle técnico saneado',exact=True).click()
 assert 'filter:id_ciudad' in page.locator('main').inner_text()
 assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
 ctx.close()
