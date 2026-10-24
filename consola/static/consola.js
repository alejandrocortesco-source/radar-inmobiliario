"use strict";
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
