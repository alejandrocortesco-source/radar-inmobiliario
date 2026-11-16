# Diagnóstico por etapas Wasi — 16/11/2026

Base limpia 9c01f9a, rama codex/ejecuciones-manuales y clon autorizados conservados.
Evidencia previa: captura automática 1f6df037-7dbc-55e1-a216-23d6bc6034c2,
Wasi run 6: authenticated, listing_incomplete/wasi_listing_unverified; cero páginas,
listing_complete=0 y absence_applied=0. No permite atribuir causa a popup o sesión.
El wrapper discover perdía las excepciones originales de filtros, resumen, tabla y
paginador. Las condiciones booleanas de lote agotaban su espera y acababan igual.

Instrumentación sin cambios de filtros, clics, retiros o reintentos: contexto por
tarea del scraper; etapas authentication, network_access/network_authentication,
filter:campo, before_search, search_click, table_refresh/table_mutation, summary_read,
filter_verify/summary_verify:campo, first_page, next_page, detail y cobertura.
Cada fallo conserva última etapa completada, inicio/duración, timeout pasado,
acción/condición, intento, tipo de excepción y mensaje fijo saneado. Causa desconocida
se presenta explícitamente como causa_no_determinada. No se deduce la causa de la
clase TimeoutError. Advertencias recuperadas se distinguen mediante finish y el
resultado final; no se captura cada ficha exitosa. Los originales históricos no
se enriquecen ni reescriben retrospectivamente.

Evidencia permitida: path conocido sin query, estado/count/hit del control,
igualdad y valores numéricos de filtro (texto libre solo longitud), filas/IDs
numéricos hasta 100, paginador/processing, contador de mutaciones, tokens de resumen
permitidos, presencia de login/diálogo/anuncio/verificación. Hasta 12 metadatos de
peticiones ajax: host/path sin query ni IDs numéricos, método, HTTP y duración.
No cuerpos, HTML, HAR, trazas, contactos, cookies o credenciales. Observación antes
de cerrar la página. El viewport completo se omite porque contiene datos de cuenta
/anunciantes; solo se intenta PNG de un select fijo de filtro, nunca login o ficha.
No manipula el DOM para sanear imágenes ni altera el manejo actual de anuncios.
CAPTCHA/acceso restringido conserva las guardas actuales y detiene el portal.

Persistencia: eventos wasi_diagnostic en SQLite técnico y agregado aditivo del
control para la UI. JSON privado en radar/diagnostics/wasi/ID_RADAR/N.json y, si es
seguro, PNG de select; referencia gs:// visible en el desplegable, sin URL pública.
Máximo ocho fallos detallados por lote Wasi, 32 KiB por JSON, 100 KiB por PNG,
100 etapas en memoria y máximo 12 eventos de red; captura/subida como máximo 15 s.
Errores auxiliares se anotan por tipo y nunca cambian la excepción ni el resultado.
Retención WASI_DIAGNOSTIC_DAYS: 14 por defecto, configurable entre 1 y 90 días.
Limpieza oportunista al subir un fallo, hasta 100 eventos antiguos y sus objetos
referenciados, sin listar bucket o modificar lifecycle/IAM. Sin nuevas ejecuciones
no hay limpieza autónoma; generaciones históricas/soft delete siguen la política
existente del bucket. No se promete borrado inmediato de versiones históricas.

UI: etapa fallida y explicación breve, detalles JSON saneados desplegables y refs
privadas. Datos ausentes en históricos permanecen ausentes. Sin cambio de diseño.

Pruebas de esta tarea: 102 regresiones Wasi/anuncios/ejecuciones aprobadas (196,64 s),
11 escenarios nuevos Chromium aislados aprobados (17,15 s), sin portales reales.
El formulario de login sintético se corrigió para ser visible; no cambió el scraper.
La evidencia de la única ejecución real autorizada se añadirá tras cerrar su Job.

Reversión: devolver web privada a radar-programacion-20261116-61b65b8 y Job a
us-central1-docker.pkg.dev/radar-inmobiliario-co/radar/jobs@sha256:d46281a68d306745e897c561f5b07ef198a9b4ace4257d6ca8eee5f16a7f6043
tras comprobar ausencia de capturas activas; no modificar porcentajes de producción,
Scheduler, IAM, IAP ni restaurar bases. Campos/eventos son aditivos. El disparador
Scheduler conserva su imagen corregida de ID; no actualizarlo ni revertirlo.
