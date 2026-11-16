() => {
  window.popupCounts = {closed:0, business:0, search:0, next:0};
  window.addAnnouncement = ({mode='normal', text='Noticia del portal', remaining=1}={}) => {
    const host=document.createElement('div');
    host.className=mode==='unknown'?'unknown-window':(mode==='sibling-root'?'productfruits--container-root':'productfruits--container');
    host.style='height:0;width:100%;display:block';
    const bg=document.createElement('div'); bg.className='pfruits-announcement-popup-container';
    bg.style='position:fixed;inset:0;z-index:99999;background:rgba(0,0,0,.2)';
    const dialog=document.createElement('div');dialog.className='pfruits-announcement-popup-v3';
    dialog.setAttribute('role','dialog');dialog.style='position:absolute;top:60px;left:80px;width:500px;height:240px;background:white';
    const content=document.createElement('p');content.textContent=text;dialog.append(content);
    const close=document.createElement('button');close.className='modern-close-btn';
    close.setAttribute('aria-label','Close dialog');close.textContent='×';
    if(mode==='hidden')close.style.display='none';
    if(mode==='disabled')close.disabled=true;
    if(mode==='wrong-name')close.setAttribute('aria-label','Continuar');
    close.onclick=()=>{
      popupCounts.closed++;
      if(mode==='stuck')return;
      if(mode==='residual-background'){dialog.remove();return;}
      host.remove();
      if(remaining>1)addAnnouncement({mode,text:'Otra promoción posterior',remaining:remaining-1});
    };
    dialog.append(close);
    if(mode==='ambiguous')dialog.append(close.cloneNode(true));
    const commercial=document.createElement('button');commercial.textContent='Renovar con promoción';
    commercial.onclick=()=>popupCounts.business++;dialog.append(commercial);
    bg.append(dialog);host.append(bg);document.body.append(host);
    if(mode==='two-dialogs')bg.append(dialog.cloneNode(true));
  };
  const search=document.querySelector('#advanced_search');
  if(search){const before=search.onclick;search.onclick=e=>{popupCounts.search++;before?.(e)};}
  const next=document.querySelector('#properties_table_next');
  if(next){const before=next.onclick;next.onclick=e=>{popupCounts.next++;before?.(e)};}
}