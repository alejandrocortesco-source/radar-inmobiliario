"use strict";
document.querySelectorAll("[data-property-photo]").forEach((image) => {
  const placeholder = image.parentElement.querySelector(".photo-fallback");
  const fail = () => { image.hidden = true; if (placeholder) placeholder.setAttribute("aria-hidden", "false"); };
  const loaded = () => { image.hidden = false; if (placeholder) placeholder.setAttribute("aria-hidden", "true"); };
  image.addEventListener("error", fail);
  image.addEventListener("load", loaded);
  if (image.complete) { if (image.naturalWidth) loaded(); else fail(); }
});
const form = document.querySelector("[data-filter-form]");
if (form) {
  form.addEventListener("submit", () => {
    // Los campos vacíos equivalen a no restringir ese atributo.
    for (const input of form.elements) {
      if (input.name && typeof input.value === "string" && !input.value.trim()) input.disabled = true;
    }
  });
  document.querySelectorAll("[data-auto-submit]").forEach((control) => {
    control.addEventListener("change", () => form.requestSubmit());
  });
}
const filters = document.querySelector("[data-filters]");
if (filters) {
  const mobile = window.matchMedia("(max-width: 840px)");
  const adapt = () => { filters.open = !mobile.matches || Boolean(document.querySelector(".notice-error")); };
  adapt();
  mobile.addEventListener("change", adapt);
}
document.querySelectorAll("[data-gallery]").forEach((gallery) => {
  const photos = JSON.parse(gallery.dataset.photos || "[]");
  const main = gallery.querySelector("[data-gallery-main]");
  if (!main || !photos.length) return;
  let index = 0;
  const show = (next) => {
    index = (next + photos.length) % photos.length;
    main.hidden = false;
    main.src = photos[index];
    gallery.querySelector("[data-gallery-count]").textContent = (index + 1) + " / " + photos.length;
    gallery.querySelector("[data-full-photo]").href = photos[index];
    gallery.querySelectorAll("[data-index]").forEach((button) => {
      const active = Number(button.dataset.index) === index;
      button.classList.toggle("selected", active);
      button.setAttribute("aria-pressed", String(active));
    });
  };
  gallery.querySelectorAll("[data-step]").forEach((button) => {
    button.addEventListener("click", () => show(index + Number(button.dataset.step)));
  });
  gallery.querySelectorAll("[data-index]").forEach((button) => {
    button.addEventListener("click", () => show(Number(button.dataset.index)));
  });
  gallery.addEventListener("keydown", (event) => {
    if (event.key === "ArrowRight" || event.key === "ArrowLeft") {
      event.preventDefault();
      show(index + (event.key === "ArrowRight" ? 1 : -1));
    }
  });
});
