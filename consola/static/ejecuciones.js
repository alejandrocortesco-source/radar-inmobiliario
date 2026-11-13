'use strict';
const form = document.querySelector('[data-execution-form]');
const boxes = Array.from(document.querySelectorAll('[data-search]'));
const all = document.querySelector('[data-select-all]');
const start = document.querySelector('[data-start]');
function selection() {
  const valid = boxes.filter(b => b.checked && !b.disabled).length;
  if (start) start.disabled = !valid;
  const message = document.querySelector('[data-selection-status]');
  if (message) message.textContent = valid ? `${valid} búsquedas seleccionadas.` : 'Selecciona al menos una búsqueda activa.';
  const eligible = boxes.filter(b => !b.disabled);
  if (all) {all.checked = eligible.length > 0 && valid === eligible.length; all.indeterminate = valid > 0 && valid < eligible.length;}
}
all?.addEventListener('change', () => {boxes.filter(b => !b.disabled).forEach(b => b.checked = all.checked); selection();});
boxes.forEach(b => b.addEventListener('change', selection));
form?.addEventListener('submit', async event => {
  event.preventDefault();
  const chosen = boxes.filter(b => b.checked && !b.disabled).map(b => JSON.parse(b.value));
  if (start) start.disabled = true;
  const error = document.querySelector('[data-start-error]');
  error.hidden = true;
  try {
    const response = await fetch('/v0.6/ejecuciones', {method: 'POST', credentials: 'same-origin',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({request_id: form.elements.request_id.value, searches: chosen})});
    if (!response.headers.get('content-type')?.includes('application/json')) throw Error();
    const data = await response.json();
    if (!response.ok) {error.textContent = data.detail || 'No se pudo iniciar. Consulta el seguimiento antes de repetir.'; error.hidden = false; return;}
    location.assign(data.url);
  } catch (_) {error.textContent = 'No se pudo confirmar la solicitud. Recarga el seguimiento antes de repetirla; el Job puede haberse iniciado.'; error.hidden = false;}
  finally {form.dataset.submitting = '0'; form.removeAttribute('aria-busy'); selection();}
});
selection();
const report = document.querySelector('[data-execution-report]');
const message = document.querySelector('[data-poll-message]');
let timer, busy = false, active = Boolean(report?.dataset.activeRun);
async function poll() {
  clearTimeout(timer);
  if (!active || document.hidden || busy) return;
  busy = true;
  try {
    const run = report.dataset.reportRun;
    const response = await fetch('/v0.6/ejecuciones/estado' + (run ? '?run=' + encodeURIComponent(run) : ''), {cache: 'no-store', credentials: 'same-origin'});
    if (!response.ok || !response.headers.get('content-type')?.includes('application/json')) throw Error();
    const data = await response.json();
    // HTML renderizado y escapado por Jinja en una ruta del mismo origen.
    report.innerHTML = data.html;
    document.querySelector('[data-active-notice]').innerHTML = data.notice_html;
    document.querySelector('[data-execution-history]').innerHTML = data.history_html;
    message.textContent = 'Seguimiento actualizado. Las consultas se pausan al ocultar esta pestaña.';
    if (!data.active) {active = false; location.replace(location.href); return;}
  } catch (_) {message.textContent = 'No se pudo actualizar el seguimiento. El Job puede continuar; volveremos a consultar.';}
  finally {busy = false; if (active && !document.hidden) timer = setTimeout(poll, 15000);}
}
document.addEventListener('visibilitychange', () => {clearTimeout(timer); if (!document.hidden && active) poll();});
if (active && !document.hidden) timer = setTimeout(poll, 15000);
