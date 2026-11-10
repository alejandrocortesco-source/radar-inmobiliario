(() => {
  const form = document.querySelector('[data-source-form]');
  if (!form) return;
  const data = JSON.parse(document.getElementById('wasi-options').textContent);
  const geo = ['id_pais', 'id_dpto', 'id_ciudad', 'id_localidad', 'id_zona'];
  const source = form.querySelector('[data-source-select]');
  function toggle() {
    const wasi = source.value === 'wasi';
    const fr = source.value === 'fincaraiz';
    form.querySelector('[data-fr-fields]').hidden = !fr;
    form.querySelectorAll('[data-fr-control]').forEach(e => e.disabled = !fr);
    form.querySelector('[data-metro-field]').hidden = wasi || fr;
    form.elements.url.disabled = wasi || fr;
    form.elements.url.required = !wasi && !fr;
    form.querySelector('[data-wasi-fields]').hidden = !wasi;
    form.querySelectorAll('[data-wasi-control]').forEach(e => e.disabled = !wasi);
  }
  function frMode() {
    const criteria = form.elements.fr_modo.value === 'criterios';
    form.querySelector('[data-fr-url]').hidden = criteria;
    form.querySelector('[data-fr-criteria]').hidden = !criteria;
    form.elements.fr_url.required = source.value === 'fincaraiz' && !criteria;
  }
  source.addEventListener('change', () => { toggle(); frMode(); });
  form.elements.fr_modo.addEventListener('change', frMode);
  geo.forEach((field, index) => form.elements[field].addEventListener('change', () => {
    geo.slice(index + 1).forEach(child => {
      const select = form.elements[child];
      select.replaceChildren(new Option('Seleccionar / Todos', ''));
      const parents = geo.slice(0, geo.indexOf(child)).map(p => form.elements[p].value);
      (data[child + ':' + parents.join('/')] || []).forEach(o => select.add(new Option(o.label, o.value)));
    });
  }));
  toggle();
  frMode();
})();
