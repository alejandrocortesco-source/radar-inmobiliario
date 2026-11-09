"""Solo controles normales y DOM observado, sin endpoints privados ni evaluación Vue."""
import asyncio
import re
import time
from urllib.parse import urlsplit

from catalogo.fuentes.wasi import GEO, SELECTS, INPUTS, NUMERIC_INPUTS, TEXT_INPUTS, RED
from metro.extraction import ExtractionError
from .auth import acceso, resolver_sesion_en_uso, AuthBlocked
from .extraction import listado, whatsapp_limpio, publicacion_whatsapp
from playwright.async_api import TimeoutError as BrowserTimeout, Error as BrowserError

SEARCH = '.advanced-search'


def control(campo):
    return SEARCH + ' #' + campo


async def _paso(nombre, operacion):
    try:
        return await operacion
    except Exception as exc:
        # Solo enumera una etapa fija; no conserva mensajes de Playwright,
        # textos de la cuenta ni valores introducidos.
        exc.wasi_step = nombre
        raise


async def cambio(page, selector, accion, timeout):
    # DataTables reemplaza las filas incluso al aplicar los mismos filtros.
    # Observar mutaciones evita confundir los resultados anteriores con el nuevo
    # resultado cuando la URL y la página activa no cambian.
    anterior = await page.locator(selector).element_handle()
    await anterior.evaluate('''e => {
      e.__radarVersion = 0;
      if (e.__radarObserver) e.__radarObserver.disconnect();
      e.__radarObserver = new MutationObserver(() => e.__radarVersion++);
      e.__radarObserver.observe(e, {childList:true,subtree:true,characterData:true});
    }''')
    await accion()
    try:
        await page.wait_for_function('e => !e.isConnected || e.__radarVersion > 0', arg=anterior, timeout=timeout)
        await page.locator(selector).wait_for(state='attached', timeout=timeout)
    except BrowserTimeout:
        raise ExtractionError('Wasi no confirmó la actualización de ' + selector) from None
    await acceso(page)


async def seleccionar(page, campo, valor, etiqueta, timeout, valor_hijo=None):
    try:
        await page.wait_for_function('''a => [...(document.querySelector('.advanced-search #'+a.c)?.options || [])]
          .some(o=>o.value===a.v && (!a.l || o.text.trim()===a.l))''',
          arg={'c': campo, 'v': valor, 'l': etiqueta}, timeout=timeout)
    except BrowserTimeout:
        raise ExtractionError('Wasi no ofrece la opción configurada en ' + campo) from None
    nodo = page.locator(control(campo))
    hijo = GEO[GEO.index(campo)+1] if campo in GEO[:-1] else None
    if await nodo.input_value() == valor:
        # Algunas aperturas muestran Colombia seleccionada pero aún no cargan
        # departamentos. Repetir la selección normal si falta el hijo guardado.
        if not hijo or not valor_hijo or await page.locator(control(hijo)).locator('option').evaluate_all('(es,v)=>es.some(e=>e.value===v)', valor_hijo):
            return
    if hijo and await page.locator(control(hijo)).count():
        await cambio(page, control(hijo), lambda: nodo.select_option(valor, timeout=timeout), timeout)
        await page.wait_for_function('''c=>![...document.querySelector('.advanced-search #'+c).options].some(o=>/Cargando/.test(o.text))''', arg=hijo, timeout=timeout)
    else:
        await nodo.select_option(valor, timeout=timeout)


async def aplicar(page, config, timeout, pace, _session_changes=0):
    if await resolver_sesion_en_uso(page, timeout):
        if _session_changes:
            raise AuthBlocked('auth_session_changed_again: otra sesión interfiere con la captura')
        return await aplicar(page, config, timeout, pace, 1)
    try:
        return await _aplicar(page, config, timeout, pace, _session_changes)
    except (ExtractionError, BrowserError):
        # El aviso puede aparecer después de cargar los controles y bloquear
        # sus opciones dependientes. Una sola toma de sesión autorizada.
        if not _session_changes and await resolver_sesion_en_uso(page, timeout):
            return await aplicar(page, config, timeout, pace, 1)
        raise


async def _aplicar(page, config, timeout, pace, _session_changes=0):
    filtros = config['filtros']
    for campo in SELECTS:
        valor = filtros.get(campo, '')
        if campo == 'id_pais' and not valor:
            raise ExtractionError('País Wasi no configurado')
        # El portal puede no ofrecer localidad para algunas ciudades.
        if campo in GEO and not valor:
            nodo = page.locator(control(campo))
            if not await nodo.count():
                continue
            if await nodo.locator('option[value=""]').count():
                await nodo.select_option('')
            continue
        hijo = GEO[GEO.index(campo)+1] if campo in GEO[:-1] else None
        await seleccionar(page, campo, valor, config.get('etiquetas', {}).get(campo), timeout,
                          filtros.get(hijo) if hijo else None)
    for campo in INPUTS:
        await page.locator(control(campo)).fill(filtros.get(campo, ''))
    await page.locator(control('property_id')).fill('')
    if _session_changes and await page.locator('.modal:visible').filter(has_text='Tu usuario está siendo usado en otros dispositivos').count():
        raise AuthBlocked('auth_session_changed_again: otra sesión interfiere con la captura')
    if await resolver_sesion_en_uso(page, timeout):
        # Usar aquí puede renovar la página. Aplicar de nuevo los mismos filtros
        # antes de buscar; nunca interpretar la recarga como una tabla vacía.
        return await aplicar(page, config, timeout, pace, _session_changes + 1)
    await pace()
    await cambio(page, '#properties_table tbody', lambda: page.locator('#advanced_search').click(timeout=timeout), timeout)
    await page.locator('#properties_table_processing').wait_for(state='hidden', timeout=timeout)
    # Verifica los valores y etiquetas aplicados, además del resumen del portal
    # y una renovación efectiva del listado; la URL común nunca es evidencia.
    actuales = await page.evaluate('''cs => Object.fromEntries(cs.map(c=>{
      const e=document.querySelector('.advanced-search #'+c);return [c,e?.value || ''];}))''', list(SELECTS + INPUTS))
    for campo in SELECTS + INPUTS:
        esperado = filtros.get(campo, '')
        actual = actuales.get(campo, '')
        if campo in NUMERIC_INPUTS:
            actual = re.sub(r'[.,\s]', '', actual)
        if actual != esperado:
            raise ExtractionError('Filtros Wasi no confirmados: ' + campo)
    resumen = await page.locator('#title_filter').inner_text()
    for campo in GEO:
        if filtros.get(campo) and config['etiquetas'][campo] not in resumen:
            raise ExtractionError('Resumen de búsqueda Wasi no confirma ' + campo)
    for campo in TEXT_INPUTS:
        if filtros.get(campo) and filtros[campo] not in resumen:
            raise ExtractionError('Resumen de búsqueda Wasi no confirma ' + campo)
    longitud = page.locator('select[name="properties_table_length"]')
    if await longitud.count():
        disponibles = await longitud.locator('option').evaluate_all('es=>es.map(e=>e.value).filter(v=>/^\\d+$/.test(v) && Number(v)>0)')
        if disponibles:
            mayor = max(disponibles, key=int)
            if await longitud.input_value() != mayor:
                await pace()
                await cambio(page, '#properties_table tbody', lambda: longitud.select_option(mayor, timeout=timeout), timeout)
                await page.locator('#properties_table_processing').wait_for(state='hidden', timeout=timeout)
    return await lote(page, timeout, active=1)


async def _leer_tabla(page):
    raw = await page.evaluate('''() => ({
      info:document.querySelector('#properties_table_info')?.textContent,
      active:document.querySelector('#properties_table_paginate .current')?.textContent || '1',
      next:document.querySelector('#properties_table_next')?.classList.contains('disabled'),
      processing:!!document.querySelector('#properties_table_processing')?.getClientRects().length,
      rows:[...document.querySelectorAll('#properties_table tbody tr[id]')].map(r=>({
        id:r.id,codigo:(r.innerText.match(/Código Wasi:\\s*(\\d+)/)||[])[1],
        title:r.querySelector('td:nth-child(4) a strong')?.textContent,
        info:r.querySelector('td:nth-child(4)')?.innerText || '',
        company:r.querySelector('a[onclick^="openModalDetailsPropertyNetwork"]')?.textContent,
        company_id:(r.querySelector('a[onclick^="openModalDetailsPropertyNetwork"]')?.getAttribute('onclick')?.match(/\\((\\d+)/)||[])[1],
        public_url:[...r.querySelectorAll('a[href]')].find(a=>/^https?:/.test(a.getAttribute('href')) && a.getAttribute('href').split('?')[0].replace(/\\/$/,'').endsWith('/'+r.id))?.href
      }))})''')
    return raw


async def lote(page, timeout=45000, *, active=None, start=None):
    limite = time.monotonic() + timeout / 1000
    ultimo = {}
    while time.monotonic() < limite:
        try:
            await acceso(page)
            raw = await _leer_tabla(page)
        except BrowserError:
            await asyncio.sleep(.2)
            continue
        ultimo = {'info': raw.get('info'), 'next': raw.get('next'), 'rows': len(raw['rows'])}
        info = (raw.get('info') or '').replace('.', '').replace(',', '')
        match = re.search(r'(\d+)\s+a\s+(\d+)\s+de\s+(\d+)\s+inmuebles', info, re.I)
        if match and not raw['processing']:
            inicio, fin, total = map(int, match.groups())
            pagina = int(raw['active'])
            correcto = ((not total and not raw['rows'] and inicio == fin == 0) or
                        (total > 0 and raw['next'] is not None and len(raw['rows']) == fin-inicio+1 and inicio > 0 and fin <= total))
            if correcto and (active is None or pagina == active) and (start is None or inicio == start):
                links = [listado(r) for r in raw['rows']]
                if len({l['id'] for l in links}) != len(links):
                    raise ExtractionError('Códigos repetidos dentro de la página Wasi')
                return {'links': links, 'active': pagina, 'next': bool(total and not raw['next']),
                        'start': inicio, 'end': fin, 'total': total}
        await asyncio.sleep(.2)
    raise ExtractionError('No se pudo verificar el total o el paginador Wasi: ' + repr(ultimo))


async def siguiente(page, previo, timeout, pace):
    await pace()
    await cambio(page, '#properties_table tbody', lambda: page.locator('#properties_table_next').click(timeout=timeout), timeout)
    await page.locator('#properties_table_processing').wait_for(state='hidden', timeout=timeout)
    actual = await lote(page, timeout, active=previo['active'] + 1, start=previo['end'] + 1)
    if actual['active'] != previo['active'] + 1 or actual['start'] != previo['end'] + 1 or actual['total'] != previo['total']:
        raise ExtractionError('Paginación Wasi repetida, alterada o incompleta')
    return actual


async def ficha(page, codigo, timeout, pace):
    imagenes = []
    def observar(request):
        if request.resource_type == 'image' and request.url.startswith('https://image.wasi.co/'):
            imagenes.append(request.url)
    page.on('request', observar)
    try:
        datos = await _ficha(page, codigo, timeout, pace)
        datos['photos'].extend(imagenes)
        return datos
    finally:
        page.remove_listener('request', observar)


async def _ficha(page, codigo, timeout, pace):
    row = page.locator(f'#properties_table tbody tr[id="{codigo}"]')
    await pace()
    # La imagen puede quedar sin dimensiones al bloquear su descarga. El título
    # es un enlace normal a la misma ficha y permanece visible sin multimedia.
    titulo = await row.locator('td:nth-child(4) a strong').inner_text()
    # El código cambia antes de que termine la petición normal de la ficha.
    # Esperar su respuesta (sin leerla ni llamar endpoints directamente) evita
    # atribuir los campos de la ficha anterior al nuevo código.
    coincide = lambda r: urlsplit(r.url).hostname == 'wasi.co' and urlsplit(r.url).path == '/usuario/inmuebles/' + codigo
    async with page.expect_request_finished(coincide, timeout=timeout), page.expect_response(coincide, timeout=timeout) as respuesta:
        await _paso('title_link', row.locator('td:nth-child(4) a[onclick^="show_property_details"]').first.click(timeout=timeout))
    response = await respuesta.value
    if response.status != 200:
        raise ExtractionError('Wasi no completó la carga de la ficha')
    panel = page.locator('.modal:visible .property-details-panels')
    await _paso('detail_heading', panel.locator('h1').wait_for(state='visible', timeout=timeout))
    await _paso('detail_identity', page.wait_for_function('''id => [...document.querySelectorAll('.modal .property-details-panels li')]
      .some(e=>e.textContent.replace(/\\s+/g,' ').trim()==='Código: '+id)''', arg=codigo, timeout=timeout))
    await _paso('detail_title', page.wait_for_function('''t=>[...document.querySelectorAll('.modal')]
      .filter(m=>getComputedStyle(m).display!=='none').some(m=>m.querySelector('.property-details-panels h1')?.textContent.replace(/\\s+/g,' ').trim()===t)''',
      arg=re.sub(r'\s+', ' ', titulo).strip(), timeout=timeout))
    await acceso(page)
    datos = await panel.evaluate('''e => {
      const principal=e.querySelector('.z-content');
      const labels=Object.fromEntries([...principal.querySelectorAll('li')].filter(l=>l.querySelector(':scope > strong') && l.style.display!=='none').map(l=>{
        const k=l.querySelector('strong').textContent.trim(); return [k.replace(/:$/,''),l.textContent.slice(l.textContent.indexOf(k)+k.length).trim()];}));
      return {title:principal.querySelector('h1')?.textContent.trim(),labels,
        description:principal.querySelector('.fotDetails .tab-content .tab-pane:nth-child(2) > div')?.textContent.trim(),
        features:[...principal.querySelectorAll('.fotDetails .tabSubCont li')].map(l=>l.textContent.trim()),
        prices:Object.fromEntries([...principal.querySelectorAll('p.precio')].filter(p=>p.style.display!=='none').map(p=>[p.querySelector('strong')?.textContent.trim(),p.querySelector('span')?.textContent.trim()])),
        photos:[...principal.querySelectorAll('.fotorama img[src]')].map(i=>i.src).filter(s=>s.startsWith('https://image.wasi.co/'))};}''')
    # Las miniaturas son perezosas. Recorre todas, sin descargar los recursos.
    nav = panel.locator('.fotorama__nav__frame')
    if datos['photos'] or await panel.locator('.fotorama img[src]').count():
        # La respuesta y los textos pueden estar listos antes de que Fotorama
        # construya la navegación. No interpretar esa fase como galería vacía.
        await _paso('gallery_ready', nav.first.wait_for(state='attached', timeout=timeout))
    cantidad = await nav.count()
    datos['gallery_frames'] = cantidad
    for i in range(cantidad):
        if i:
            await _paso('gallery_next', panel.locator('.fotorama__arr--next').click(timeout=timeout))
        await _paso('gallery_active', page.wait_for_function('''n=>[...document.querySelectorAll('.modal')].find(m=>getComputedStyle(m).display!=='none')?.querySelectorAll('.fotorama__nav__frame')[n]?.classList.contains('fotorama__active')''', arg=i, timeout=timeout))
        await _paso('gallery_image', page.wait_for_function('''n=>{
          const m=[...document.querySelectorAll('.modal')].find(m=>getComputedStyle(m).display!=='none');
          const thumb=m?.querySelectorAll('.fotorama__nav__frame')[n]?.querySelector('img[src]');
          const stage=m?.querySelector('.fotorama__stage__frame.fotorama__active img[src]');
          const key=s=>{try{return JSON.parse(atob(new URL(s).pathname.slice(1))).key}catch{return s}};
          return !!(thumb?.complete && thumb.naturalWidth && stage?.complete && stage.naturalWidth && key(thumb.src)===key(stage.src));
        }''', arg=i, timeout=timeout))
        datos['photos'].extend(await panel.locator('.fotorama__stage img[src]').evaluate_all('es=>es.map(e=>e.src).filter(s=>s.startsWith("https://image.wasi.co/"))'))
    await page.locator('.modal:visible .top_close a').click(timeout=timeout)
    await panel.wait_for(state='hidden', timeout=timeout)
    return datos


async def contactos(page, codigo, timeout, pace):
    await pace()
    coincide = lambda r: urlsplit(r.url).hostname == 'wasi.co' and urlsplit(r.url).path == '/usuario/ajax-inmuebles/get-company'
    # requestfinished conserva la espera de descarga completa. Response.finished
    # en Playwright 1.55 deja una tarea que falla al cerrar el navegador.
    async with page.expect_request_finished(coincide, timeout=timeout), page.expect_response(coincide, timeout=timeout) as respuesta:
        await page.locator(f'#properties_table tbody tr[id="{codigo}"] a[onclick^="openModalDetailsPropertyNetwork"]').click(timeout=timeout)
    response = await respuesta.value
    if response.status != 200:
        raise ExtractionError('Wasi no completó la carga del contacto')
    panel = page.locator('#modal_company_details_network:visible .modalRedContact')
    await panel.locator('.groupInfo').wait_for(state='visible', timeout=timeout)
    await acceso(page)
    datos = await panel.evaluate('''e=>({name:e.querySelector('h1')?.textContent,
      agent:[...e.querySelectorAll('h2 span')].some(s=>getComputedStyle(s).display!=='none' && s.textContent.trim()),
      labs:Object.fromEntries([...e.querySelectorAll('.groupInfo .lab')].filter(l=>l.style.display!=='none').map(l=>{
        const text=l.querySelector('.text'),phone=text?.querySelector('a[tel],a[href^="tel:"]');
        const label=l.querySelector('.lab-tt')?.textContent;
        return [label,phone && /Teléfono/.test(label) ? phone.textContent.trim() : text?.innerText.trim()];})),
      whatsapp:e.querySelector('a.whatsapp_link')?.getAttribute('href')})''')
    await page.locator('#modal_company_details_network .close').click(timeout=timeout)
    await panel.wait_for(state='hidden', timeout=timeout)
    return {'phone': datos['labs'].get('Teléfono móvil:'), 'local_phone': datos['labs'].get('Teléfono fijo:'),
            'advertiser_address': datos['labs'].get('Ubicación:'), 'whatsapp': whatsapp_limpio(datos.get('whatsapp')),
            'public_url': publicacion_whatsapp(datos.get('whatsapp'), codigo),
            'name': datos.get('name'), 'agent': datos.get('agent', True)}
