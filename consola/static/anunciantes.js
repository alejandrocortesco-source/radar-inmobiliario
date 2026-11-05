"use strict";
(() => {
  const dialog = document.createElement('dialog');
  dialog.id = 'advertiser-panel';
  dialog.setAttribute('aria-labelledby', 'advertiser-panel-title');
  dialog.innerHTML = '<header><h2 id="advertiser-panel-title">Anunciante</h2><button type="button" data-advertiser-close aria-label="Cerrar anunciante">Cerrar ×</button></header><div class="advertiser-body" aria-live="polite"></div>';
  document.body.append(dialog);
  const body = dialog.querySelector('.advertiser-body');
  let origin, controller;
  dialog.addEventListener('close', () => { controller?.abort(); origin?.focus({preventScroll:true}); });
  dialog.querySelector('button').addEventListener('click', () => dialog.close());
  async function load(url) {
    controller?.abort(); controller = new AbortController();
    body.textContent = 'Cargando anunciante…';
    try {
      const response = await fetch(url, {signal:controller.signal});
      if (!response.ok) throw Error();
      const html = new DOMParser().parseFromString(await response.text(), 'text/html');
      const content = html.querySelector('[data-advertiser-content]');
      if (!content) throw Error();
      body.replaceChildren(content); body.scrollTop = 0;
    } catch (error) {
      if (error.name === 'AbortError') return;
      body.textContent = 'No se pudo consultar el anunciante. ';
      const retry = document.createElement('button'); retry.textContent = 'Reintentar';
      retry.onclick = () => load(url); body.append(retry);
    }
  }
  // Captura antes de los manejadores históricos de fichas y paneles.
  document.addEventListener('click', e => {
    const ficha = e.target.closest('#advertiser-panel a[href^="/v0.4/inmuebles/"]');
    if (ficha && e.button === 0 && !e.ctrlKey && !e.metaKey && !e.shiftKey && !e.altKey) {
      dialog.close();
      return;
    }
    const link = e.target.closest('[data-advertiser], [data-advertiser-page]');
    if (!link || e.button !== 0 || e.ctrlKey || e.metaKey || e.shiftKey || e.altKey) return;
    e.preventDefault(); e.stopImmediatePropagation();
    if (!dialog.open) { origin = link; dialog.showModal(); }
    load(link.href);
  }, true);
})();
