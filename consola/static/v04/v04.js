"use strict";
(() => {
  const surface = document.querySelector('#surface');
  let origin = null, active = null, pending = null;
  const announce = message => { document.querySelector('#announcement').textContent = message; };
  const store = {get(k) {try{return sessionStorage.getItem('v04:'+k);}catch{return null;}},set(k,v){try{sessionStorage.setItem('v04:'+k,v);}catch{}}};
  const params = new URLSearchParams(location.search);
  const positionKey=()=>{const q=new URLSearchParams(location.search);q.delete('panel');return location.pathname+'?'+q;};
  addEventListener('pagehide',()=>store.set('position:'+positionKey(),JSON.stringify({y:scrollY,x:document.querySelector('main .table-scroll')?.scrollLeft||0})));
  const restore=()=>{try{const p=JSON.parse(store.get('position:'+positionKey()));if(p){scrollTo(0,p.y);const region=document.querySelector('main .table-scroll');if(region)region.scrollLeft=p.x;}}catch{}};
  requestAnimationFrame(restore);
  const matching = !!document.querySelector('.opportunity-summary');
  const key = matching ? 'matching' : 'catalogo';
  if (!params.has('panel') && !document.querySelector('.detail')) store.set(key, location.pathname+location.search);
  document.querySelectorAll('[data-context]').forEach(a => {
    const saved = store.get(a.dataset.context); if (saved) a.href = saved;
  });
  document.querySelectorAll('[data-new],[data-management]').forEach(a => {
    const url = new URL(location.href); url.hash = '';url.searchParams.set('panel',a.hasAttribute('data-new')?'nueva':'clientes');
    if(a.hasAttribute('data-new'))url.searchParams.delete('oportunidad');
    a.href=url.pathname+url.search;
  });
  function snapshot(dialog){return JSON.stringify([...dialog.querySelectorAll('form')].map(f=>[...new FormData(f)]));}
  function dirty(dialog){return dialog.dataset.initial !== snapshot(dialog);}
  function setup(dialog) {
    dialog.dataset.initial=snapshot(dialog);
    const primary=dialog.querySelector('#crm-form');
    const primaryInitial=primary ? JSON.stringify([...new FormData(primary)]) : '';
    dialog.addEventListener('cancel', e=>{e.preventDefault();close(dialog);});
    dialog.addEventListener('input',()=>{const s=dialog.querySelector('[data-comment-status]');if(s)s.textContent='Cambios sin guardar';});
    dialog.querySelectorAll('form:not([data-comment-form])').forEach(f=>f.addEventListener('submit',event=>{
      if(f.classList.contains('client-picker')&&primary&&JSON.stringify([...new FormData(primary)])!==primaryInitial){
        event.preventDefault();pending=()=>location.assign(f.action+'?'+new URLSearchParams(new FormData(f)));
        close(dialog);return;
      }
      dialog.dataset.initial=snapshot(dialog);
    }));
  }
  function finish(dialog) {
    dialog.close();active=null;dialog.querySelector('.discard').hidden=true;
    origin?.focus();
    if(dialog.id==='editor'){
      const u=new URL(location.href);u.searchParams.delete('panel');history.replaceState(null,'',u.pathname+u.search);
    }
    if(pending){const f=pending;pending=null;f();}
  }
  function close(dialog){
    if(dialog.querySelector('[data-saving="1"]')){announce('Espera a que termine el guardado del comentario.');return;}
    if(dirty(dialog)){dialog.querySelector('.discard').hidden=false;dialog.querySelector('[data-continue]').focus();return;}
    finish(dialog);
  }
  function show(title,content,drawer=false){
    if(active){pending=()=>show(title,content,drawer);close(active);return;}
    surface.classList.toggle('drawer',drawer);surface.querySelector('#surface-title').textContent=title;
    surface.querySelector('.surface-content').replaceChildren(content);surface.showModal();active=surface;setup(surface);
  }
  const editor=document.querySelector('#editor');
  if(editor){origin=document.querySelector(params.get('panel')==='editar'?'a[href*="panel=editar"]':params.get('panel')==='clientes'?'[data-management]':'[data-new]');editor.removeAttribute('open');editor.showModal();active=editor;setup(editor);}
  // Inline discard controls keep the current draft and avoid nested confirmations.
  document.addEventListener('click',async e=>{
    if(e.target.closest('[data-close]')){close(e.target.closest('dialog'));return;}
    if(e.target.closest('[data-continue]')){pending=null;e.target.closest('.discard').hidden=true;e.target.closest('dialog').querySelector('input,textarea,button').focus();return;}
    if(e.target.closest('[data-discard]')){finish(e.target.closest('dialog'));return;}
    const t=e.target.closest('[data-surface]');
    if(t){origin=t;show(t.textContent,document.querySelector('#'+t.dataset.surface).content.cloneNode(true));return;}
    const link=e.target.closest('a');if(!link||e.ctrlKey||e.metaKey||e.shiftKey||link.target==='_blank'||link.hasAttribute('download'))return;
    const url=new URL(link.href,location.href);
    if(url.origin!==location.origin)return;
    if(url.pathname.startsWith('/v0.4/inmuebles/')||url.pathname.startsWith('/v0.4/clientes/')){
      e.preventDefault();origin=link;
      if(active&&dirty(active)){pending=()=>link.click();close(active);return;}
      if(active)finish(active);
      const content=document.createElement('div');content.setAttribute('role','status');content.textContent='Cargando…';
      const isDetail=url.pathname.includes('/inmuebles/');show(isDetail?'Detalle del inmueble':'Editar cliente',content,isDetail);
      try{
        const response=await fetch(url);const html=await response.text();
        if(!response.ok)throw Error('No se pudo consultar. Vuelve a intentar.');
        const parsed=new DOMParser().parseFromString(html,'text/html');const main=parsed.querySelector('#editor .surface-content')||parsed.querySelector('main');
        if(!surface.open)return;
        surface.querySelector('.surface-content').replaceChildren(...main.childNodes);setup(surface);
        if(url.hash==='#comentario'){surface.querySelector('#comentario').scrollIntoView();surface.querySelector('#comment-text').focus();}
        surface.dataset.inmueble=url.pathname.split('/').pop();
      }catch(error){content.textContent=error.message;const retry=document.createElement('button');retry.textContent='Reintentar';retry.onclick=()=>{finish(surface);link.click();};content.append(retry);}
      return;
    }
    if(active&&dirty(active)) {e.preventDefault();pending=()=>location.assign(url);close(active);}
  });
  document.addEventListener('submit',async e=>{
    const form=e.target.closest('[data-comment-form]');if(!form)return;e.preventDefault();
    const input=form.querySelector('textarea'),status=form.querySelector('[data-comment-status]'),button=form.querySelector('button');
    const text=input.value;status.textContent='Guardando…';button.disabled=true;form.dataset.saving='1';
    try{
      const response=await fetch('/v0.4/comentarios/'+encodeURIComponent(form.dataset.id),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({texto:text})});
      if(!response.ok)throw Error();await response.json();
      status.textContent=input.value===text?'Guardado':'Guardado; hay nuevos cambios sin guardar';
      if(input.value===text&&active)active.dataset.initial=snapshot(active);
      document.querySelectorAll('[data-detail-comment]').forEach(link=>{if(new URL(link.href).pathname.endsWith('/'+form.dataset.id))link.textContent=text?'Ver comentario':'Agregar';});
      announce('Comentario guardado');
    }catch{status.textContent='No se pudo guardar. El texto se conserva; pulsa Guardar comentario para reintentar.';}
    finally{button.disabled=false;delete form.dataset.saving;}
  });
  // Shared v0.3 code supplies validation and the real location selector.
  document.querySelectorAll('[data-filters]>summary').forEach(s=>s.textContent='Más filtros');
  document.querySelectorAll('#filtros,.matching-controls form').forEach(form=>form.addEventListener('submit',()=>{
    announce('Actualizando resultados…');document.querySelectorAll('main .table-scroll').forEach(region=>{region.setAttribute('aria-busy','true');region.style.opacity='.4';});
  }));
  addEventListener('beforeunload',e=>{if(active&&dirty(active)){e.preventDefault();e.returnValue='';}});
})();
