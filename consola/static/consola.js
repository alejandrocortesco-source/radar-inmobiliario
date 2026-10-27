"use strict";
const captureForm = document.querySelector('#crm-form');
if (captureForm) {
  const rooms = captureForm.querySelector('[name="habitaciones_min"]');
  const area = captureForm.querySelector('[name="area_min_m2"]');
  function validateMinimum() {
    rooms.setCustomValidity(rooms.value === '' && area.value === '' ? 'Ingresa habitaciones mínimas o área mínima.' : '');
  }
  rooms.addEventListener('input', validateMinimum);
  area.addEventListener('input', validateMinimum);
  validateMinimum();
}
// Mejora progresiva: el select nativo sigue siendo el único valor que se envía.
const locationField = document.querySelector('[data-location-field]');
if (locationField) {
  const city = document.querySelector('#crm_ciudad');
  const nativeLocations = document.querySelector('#crm_ubicaciones');
  const enhanced = locationField.querySelector('.location-enhanced');
  const picker = locationField.querySelector('[data-location-picker]');
  const search = locationField.querySelector('[data-location-search]');
  const tags = locationField.querySelector('[data-location-tags]');
  const notice = locationField.querySelector('[data-location-notice]');
  const choices = [...locationField.querySelectorAll('[data-location-row]')];
  const options = [...nativeLocations.options];
  const normalizeLocation = value => value.normalize('NFKD').replace(/[\u0300-\u036f]/g, '').toLocaleLowerCase().trim().replace(/\s+/g, ' ');
  const cityKey = () => city.tagName === 'SELECT' ? city.selectedOptions[0]?.dataset.cityKey || '' : city.dataset.cityKey;
  function filterChoices() {
    const term = normalizeLocation(search.value);
    let visible = 0;
    choices.forEach(row => {
      row.hidden = row.dataset.city !== cityKey() || !normalizeLocation(row.querySelector('span').textContent).includes(term);
      if (!row.hidden) visible++;
    });
    locationField.querySelector('[data-location-empty]').hidden = visible > 0;
  }
  function syncSelection() {
    tags.replaceChildren();
    options.filter(o => o.selected && !o.disabled).forEach(option => {
      const tag = document.createElement('span');
      tag.className = 'location-tag';
      const name = option.textContent.split(' · ')[0];
      const label = document.createElement('span');
      label.textContent = name + (option.dataset.legacy === '1' ? ' (guardado fuera del catálogo)' : '');
      const remove = document.createElement('button');
      remove.type = 'button'; remove.textContent = '×'; remove.setAttribute('aria-label', 'Quitar ' + name);
      remove.addEventListener('click', () => { option.selected = false; syncSelection(); });
      tag.append(label, remove); tags.append(tag);
    });
    choices.forEach(row => {
      row.querySelector('input').checked = options.some(o => o.selected && !o.disabled && o.dataset.city === row.dataset.city && o.dataset.key === row.dataset.key);
    });
    const count = nativeLocations.selectedOptions.length;
    locationField.querySelector('[data-location-count]').textContent = count ? `${count} seleccionados` : '';
    filterChoices();
  }
  choices.forEach(row => row.querySelector('input').addEventListener('change', event => {
    const option = options.find(o => o.dataset.city === row.dataset.city && o.dataset.key === row.dataset.key);
    option.selected = event.target.checked; syncSelection();
  }));
  city.addEventListener('change', () => {
    picker.open = false;
    captureForm.querySelector('[name="ubicaciones_ciudad"]').value = cityKey();
    const previous = options.filter(o => o.selected);
    options.forEach(o => { o.selected = false; o.disabled = o.dataset.city !== cityKey(); });
    const removed = [];
    previous.forEach(o => {
      const valid = options.find(v => v.dataset.city === cityKey() && v.dataset.key === o.dataset.key && v.dataset.legacy !== '1');
      if (valid) valid.selected = true; else removed.push(o.textContent.split(' · ')[0]);
    });
    search.value = '';
    notice.textContent = removed.length ? `Se retiraron ubicaciones que no corresponden a la ciudad: ${removed.join(', ')}.` : 'Ubicaciones actualizadas para la ciudad seleccionada.';
    syncSelection();
  });
  search.addEventListener('input', filterChoices);
  picker.addEventListener('toggle', () => { if (picker.open) { filterChoices(); search.focus(); } });
  locationField.querySelector('[data-location-done]').addEventListener('click', () => { picker.open = false; picker.querySelector('summary').focus(); });
  document.addEventListener('click', event => { if (!event.composedPath().includes(locationField)) picker.open = false; });
  picker.addEventListener('keydown', event => { if (event.key === 'Escape') { picker.open = false; picker.querySelector('summary').focus(); } });
  nativeLocations.addEventListener('change', syncSelection);
  locationField.querySelector('.location-fallback').hidden = true;
  enhanced.hidden = false;
  syncSelection();
}
const form = document.querySelector("[data-filter-form]");
const scrollRegion = document.querySelector("[data-catalog-scroll]");
const storageKey = "radar:catalogo";
const address = location.pathname + location.search;
function savePosition() {
  if (!scrollRegion) return;
  try {
    sessionStorage.setItem(storageKey, JSON.stringify({url: address, y: scrollY, x: scrollRegion.scrollLeft}));
  } catch (_) { /* La navegación GET funciona sin almacenamiento del navegador. */ }
}
if (scrollRegion) {
  document.querySelectorAll(".property-link").forEach(link => link.addEventListener("click", savePosition));
  addEventListener("pagehide", savePosition);
  addEventListener("pageshow", () => {
    try {
      const position = JSON.parse(sessionStorage.getItem(storageKey));
      if (position && position.url === address) requestAnimationFrame(() => {
        scrollRegion.scrollLeft = position.x;
        scrollTo(0, position.y);
      });
    } catch (_) { /* Sin almacenamiento, se conserva la URL con los filtros. */ }
  });
}
if (form) {
  form.addEventListener("submit", () => {
    for (const input of form.elements) {
      if (input.name && typeof input.value === "string" && !input.value.trim()) input.disabled = true;
    }
    try { sessionStorage.removeItem(storageKey); } catch (_) {}
  });
  document.querySelectorAll("[data-auto-submit]").forEach(control => {
    control.addEventListener("change", () => form.requestSubmit());
  });
}
// Los paneles nativos siguen funcionando sin JavaScript.
const panels = document.querySelectorAll(".popover");
document.querySelectorAll("[data-price-order]").forEach(link => {
  link.addEventListener("click", event => {
    const operation = document.querySelector("#operacion");
    const currency = document.querySelector("#moneda");
    if (operation.value && currency.value) return;
    event.preventDefault();
    document.querySelector("#orden").value = link.dataset.priceOrder;
    document.querySelector(".price-filter").open = true;
    (operation.value ? currency : operation).focus();
  });
});
panels.forEach(panel => panel.addEventListener("toggle", () => {
  if (panel.open) panels.forEach(other => { if (other !== panel) other.open = false; });
}));
document.addEventListener("keydown", event => {
  if (event.key === "Escape") {
    document.querySelectorAll(".popover[open], .photo-links[open]").forEach(panel => {
      panel.open = false;
      panel.querySelector("summary").focus();
    });
  }
});
document.addEventListener("click", event => {
  if (event.target.closest("[data-price-order]")) return;
  panels.forEach(panel => { if (!panel.contains(event.target)) panel.open = false; });
});
