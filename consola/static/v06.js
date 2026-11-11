'use strict';
// Guarda la URL completa del catálogo, incluidos filtros, orden y paginación.
document.querySelectorAll('[data-catalog-link]').forEach(link => {
  try {const u = sessionStorage.getItem('radar:v06:catalogo'); if (u && u.startsWith('/v0.4/?')) link.href = u;} catch (_) {}
});
document.querySelectorAll('form[method="post"]').forEach(form => form.addEventListener('submit', event => {
  if (form.dataset.submitting === '1') {event.preventDefault(); return;}
  form.dataset.submitting = '1';
  form.setAttribute('aria-busy', 'true');
  // No deshabilitar campos: el envío nativo debe conservar todos los valores.
}));
const statusNode = document.querySelector('[data-match-status]');
if (statusNode?.dataset.poll === '1') {
  let attempts = 0;
  const timer = setInterval(async () => {
    try {
      const response = await fetch(`/v0.6/oportunidades/${encodeURIComponent(statusNode.dataset.opportunity)}/estado`);
      if (!response.ok) throw Error();
      const state = await response.json();
      if (state.estado === 'listo' || state.estado === 'interrumpida') {
        clearInterval(timer);
        if (state.fecha !== statusNode.dataset.initialTime || statusNode.dataset.initialState === 'procesando') {
          // Carga las explicaciones nuevas sin reenviar formularios.
          const url = new URL(location.href); url.searchParams.delete('evaluando'); url.searchParams.delete('recalculando'); url.searchParams.delete('guardado');
          location.replace(url);
        }
      } else if (state.estado === 'procesando') {
        statusNode.textContent = 'Evaluando candidatos. Puedes seguir navegando.';
      }
    } catch (_) {
      statusNode.textContent = 'No pudimos consultar el progreso. Recarga la ficha para volver a intentar.';
    }
    if (++attempts >= 180) {clearInterval(timer); statusNode.textContent = 'El cálculo está tardando más de lo esperado. Recarga la ficha para consultar; otra llamada requiere un clic en Evaluar con Gemini.';}
  }, 2000);
}
