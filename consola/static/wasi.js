(() => {
  const form = document.querySelector('[data-source-form]');
  if (!form) return;
  const data = JSON.parse(document.getElementById('wasi-options').textContent);
  const geo = ['id_pais', 'id_dpto', 'id_ciudad', 'id_localidad', 'id_zona'];
  const source = form.querySelector('[data-source-select]');
  function toggle() {
    const wasi = source.value === 'wasi';
    form.querySelector('[data-metro-field]').hidden = wasi;
    form.elements.url.disabled = wasi;
    form.elements.url.required = !wasi;
    form.querySelector('[data-wasi-fields]').hidden = !wasi;
    form.querySelectorAll('[data-wasi-control]').forEach(e => e.disabled = !wasi);
  }
  source.addEventListener('change', toggle);
  geo.forEach((field, index) => form.elements[field].addEventListener('change', () => {
    geo.slice(index + 1).forEach(child => {
      const select = form.elements[child];
      select.replaceChildren(new Option('Seleccionar / Todos', ''));
      const parents = geo.slice(0, geo.indexOf(child)).map(p => form.elements[p].value);
      (data[child + ':' + parents.join('/')] || []).forEach(o => select.add(new Option(o.label, o.value)));
    });
  }));
  toggle();
})();
