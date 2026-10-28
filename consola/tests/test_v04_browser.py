"""Comprobaciones de flujo real, borradores, red fallida y navegación de contextos."""
import pytest
from playwright.sync_api import expect
from test_browser import servidor, pagina, seleccionar_barrio


def crear(page, url):
    c=page.request.post(url+'/api/clientes',data={'nombre':'Mónica'}).json()
    datos={'cliente_id':c['id'],'necesidades':{'operacion':'compra','tipo':'casa','ciudad':'Bogotá','barrios':['La Carolina'],'presupuesto_max':'110000000','habitaciones_min':3}}
    return [page.request.post(url+'/api/oportunidades',data=datos).json()['id'] for _ in range(2)]


def test_comentario_error_recarga_dos_oportunidades_y_borrador(servidor,pagina):
    page=pagina;url=servidor;o,otro=crear(page,url)
    page.goto(url+'/v0.4/?oportunidad='+o)
    link=page.locator('[data-detail-comment]').first
    href=link.get_attribute('href');identificador=href.split('/inmuebles/')[1].split('?')[0]
    link.click();expect(page.locator('#surface')).to_be_visible()
    expect(page.locator('#comment-text')).to_be_focused()
    page.locator('#comment-text').fill('Buena luz')
    page.route('**/v0.4/comentarios/**',lambda route:route.fulfill(status=503,body='fallo'))
    page.get_by_role('button',name='Guardar comentario').click()
    expect(page.locator('[data-comment-status]')).to_contain_text('No se pudo guardar')
    expect(page.locator('#comment-text')).to_have_value('Buena luz')
    page.locator('#surface [data-close]').click()
    expect(page.locator('#surface .discard')).to_be_visible()
    page.get_by_role('button',name='Seguir editando').click()
    page.unroute('**/v0.4/comentarios/**')
    page.get_by_role('button',name='Guardar comentario').click()
    expect(page.locator('[data-comment-status]')).to_have_text('Guardado')
    page.locator('#surface [data-close]').click();expect(link).to_be_focused()
    page.reload();page.locator('[data-detail-comment]').first.click()
    expect(page.locator('#comment-text')).to_have_value('Buena luz')
    page.locator('#surface [data-close]').click()
    page.goto(url+'/v0.4/?oportunidad='+otro)
    page.locator(f'[data-detail-comment][href*="{identificador}"]').click()
    expect(page.locator('#comment-text')).to_have_value('Buena luz')
    page.locator('#comment-text').fill('Descartar este borrador')
    page.keyboard.press('Escape');page.get_by_role('button',name='Descartar cambios').click()
    page.goto(url+'/v0.4/')
    page.locator(f'[data-detail-comment][href*="{identificador}"]').click()
    expect(page.locator('#comment-text')).to_have_value('Buena luz')


@pytest.mark.parametrize('w,h',[(1366,768),(1440,900),(390,844)])
def test_contextos_editor_detalle_y_sin_desbordamiento(servidor,pagina,w,h):
    page=pagina;url=servidor;o,_=crear(page,url)
    page.set_viewport_size({'width':w,'height':h})
    page.goto(url+'/v0.4/?limit=12&offset=12')
    first=page.locator('.property-link').first.get_attribute('href')
    page.goto(url+'/v0.4/?oportunidad='+o+'&match_orden=precio_desc')
    page.get_by_role('link',name='Catálogo completo',exact=True).click()
    assert 'offset=12' in page.url
    assert first==page.locator('.property-link').first.get_attribute('href')
    page.get_by_role('link',name='Coincidencias',exact=True).click()
    assert 'match_orden=precio_desc' in page.url
    assert page.locator('main table.catalog-table').count()==1
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
    page.get_by_role('link',name='Editar',exact=True).click()
    expect(page.locator('#editor')).to_be_visible()
    assert 'match_orden=precio_desc' in page.url
    page.locator('#crm_nombre').fill('Borrador de prueba')
    page.locator('#editor [data-close]').click()
    expect(page.locator('#editor .discard')).to_be_visible()
    page.get_by_role('button',name='Seguir editando').click()
    expect(page.locator('#crm_nombre')).to_have_value('Borrador de prueba')
    page.locator('#editor [data-close]').click();page.get_by_role('button',name='Descartar cambios').click()
    page.locator('.match-property-link').first.click()
    expect(page.locator('#surface')).to_be_visible()
    assert page.locator('#surface dialog').count()==0
    page.keyboard.press('Escape');expect(page.locator('#surface')).not_to_be_visible()


def test_captura_guardar_buscar_y_recuperar_cliente(servidor,pagina):
    page=pagina;url=servidor
    page.goto(url+'/v0.4/');page.get_by_role('link',name='+ Nueva',exact=True).click()
    page.locator('#crm_nombre').fill('Cliente navegador')
    page.locator('#crm_tipo').select_option('casa')
    if page.locator('select#crm_ciudad').count():page.locator('#crm_ciudad').select_option(label='Bogotá')
    page.locator('#crm_presupuesto').fill('110000000')
    page.locator('#crm_habitaciones_min').fill('3')
    seleccionar_barrio(page,True)
    page.get_by_role('button',name='Guardar y buscar coincidencias').click()
    expect(page.locator('.opportunity-summary')).to_contain_text('Cliente navegador')
    page.get_by_role('button',name='Diagnóstico',exact=True).click()
    expect(page.locator('#surface .diagnostic-table')).to_be_visible()
    page.keyboard.press('Escape')
    page.get_by_role('link',name='Editar',exact=True).click()
    page.locator('#crm_presupuesto').fill('109000000')
    page.get_by_role('button',name='Guardar cambios',exact=True).click()
    expect(page.locator('main')).to_contain_text('criterios anteriores')
    assert page.locator('main table.catalog-table').count()==0
    page.get_by_role('link',name='Buscar coincidencias',exact=True).click()
    expect(page.locator('main table.catalog-table')).to_be_visible()
    page.get_by_role('link',name='Clientes y oportunidades',exact=True).click()
    page.locator('#editor').get_by_role('link',name='Editar cliente',exact=True).click()
    expect(page.locator('#surface')).to_contain_text('todas sus oportunidades')
    assert page.locator('dialog[open]').count()==1
    page.locator('#surface input[name=nombre]').fill('Cliente actualizado')
    page.get_by_role('button',name='Guardar cliente',exact=True).click()
    expect(page.locator('#crm_nombre')).to_have_value('Cliente actualizado')
