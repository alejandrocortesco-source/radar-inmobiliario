(() => {
  const form = document.querySelector('[data-plan-form]');
  const preview = document.querySelector('[data-plan-preview]');
  let timer, sequence = 0;
  function visibility() {
    const f = form.elements.frequency.value;
    form.querySelector('[data-weekly]').hidden = f !== 'weekly';
    form.querySelector('[data-once]').hidden = f !== 'once';
    form.elements.date.required = f === 'once';
  }
  async function update() {
    const current = ++sequence;
    try {
      const response = await fetch('/v0.6/ejecuciones/programaciones/previsualizar', {method:'POST', credentials:'same-origin', body:new URLSearchParams(new FormData(form))});
      const result = await response.json();
      if (current !== sequence) return;
      form.querySelectorAll('[data-field-error]').forEach(e => { e.textContent = result.errors?.[e.dataset.fieldError] || ''; });
      for (const [field, name] of Object.entries({name:'name', frequency:'frequency', date:'date', time:'hour', keys:'schedule_search', days:'days'})) {
        form.querySelectorAll(`[name="${name}"]`).forEach(e => e.setAttribute('aria-invalid', result.errors?.[field] ? 'true' : 'false'));
      }
      preview.textContent = response.ok ? `${result.summary}. Próxima ejecución prevista: ${result.next} · Bogotá${form.elements.enabled.checked ? '' : ' (si se activa)'}.` : 'Revisa los campos indicados para calcular la próxima ejecución.';
      form.querySelector('button[value="create"],button[value="edit"]').disabled = !response.ok;
    } catch (_) {
      preview.textContent = 'No se pudo calcular la vista previa. Puedes usar el botón Vista previa para volver a consultar.';
      form.querySelector('button[value="create"],button[value="edit"]').disabled = true;
    }
  }
  const choices = form ? [...form.querySelectorAll('[name="schedule_search"]')] : [];
  function countSearches() {
    const count = choices.filter(e => e.checked && !e.disabled).length;
    const counter = form?.querySelector('[data-search-count]');
    if (counter) counter.textContent = `${count} ${count === 1 ? 'búsqueda seleccionada' : 'búsquedas seleccionadas'}`;
  }
  form?.querySelectorAll('[data-select-searches],[data-clear-searches]').forEach(button => {
    button.hidden = false;
    button.addEventListener('click', () => {
      choices.forEach(e => {if (!e.disabled) e.checked = button.hasAttribute('data-select-searches') && e.dataset.eligible === '1';});
      form.dispatchEvent(new Event('input', {bubbles:true}));
    });
  });
  countSearches();
  form?.addEventListener('input', () => {visibility(); countSearches(); clearTimeout(timer); sequence++; timer = setTimeout(update, 180);});
  if (form) {visibility(); form.querySelector('button[value="create"],button[value="edit"]').disabled = true; if (document.querySelector('#plan-editor').open) update();}
  document.querySelector('#plan-editor')?.addEventListener('toggle', () => {if (document.querySelector('#plan-editor').open) {const focused = document.activeElement; if (focused === document.body || focused?.tagName === 'SUMMARY') form.elements.name.focus(); update();}});
  const activity = document.querySelector('[data-plan-activity]');
  let polling = activity?.dataset.hasActive === '1', busy = false, pollTimer;
  async function poll() {
    if (!polling || document.hidden || busy) return;
    busy = true;
    try {
      const response = await fetch('/v0.6/ejecuciones/estado' + (new URLSearchParams(location.search).has('historial') ? '?historial='+encodeURIComponent(new URLSearchParams(location.search).get('historial')) : ''), {cache:'no-store',credentials:'same-origin'});
      if (!response.ok) throw Error();
      const data = await response.json();
      activity.innerHTML = data.activity_html;
      document.querySelector('[data-running-count]').textContent = data.running_count;
      polling = Boolean(data.active);
      document.querySelector('[data-plan-poll]').textContent = 'Actividad actualizada.';
    } catch (_) {document.querySelector('[data-plan-poll]').textContent = 'Estado por verificar. Vuelve a cargar para consultar el resultado.'; activity.querySelectorAll('.run-state').forEach(e => {e.textContent = 'Estado por verificar';});}
    finally {busy = false; if (polling && !document.hidden) pollTimer = setTimeout(poll,15000);}
  }
  document.addEventListener('visibilitychange', () => {clearTimeout(pollTimer); if (!document.hidden) poll();});
  if (polling) pollTimer = setTimeout(poll,15000);
})();
