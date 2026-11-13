# Radar Central — ajuste visual del 13 de noviembre de 2026

v0.12.1 implementada en el clon independiente y la rama autorizada
`codex/ejecuciones-manuales`. Runtime web: `e5a61ab579b51fce3ebb3ded94200937324e1064`.

## Resultado disponible

Inicio privado de revisión:
https://ejecuciones-review---radar-dvhqhy5u3q-uc.a.run.app/v0.6/

- El tercer recuadro ahora es Radar Central: hasta tres búsquedas con nombre,
  fuente, fecha disponible y estado breve. Inicio conserva cuatro secciones.
- La navegación y la página Ejecuciones se llaman Radar Central. Su ruta operativa
  `/v0.6/ejecuciones` y la API de seguimiento permanecen.
- El botón Agregar búsquedas abre `/v0.6/ejecuciones/busquedas`, con los formularios
  previos de las tres fuentes, gestión, filtros dependientes y mensajes de error.
  Guardar/editar sigue sin capturar. Los POST anteriores y enlaces de edición
  históricos se conservan, con redirección a la nueva ubicación.
- El recuadro lee el control durable y la última captura técnica disponible;
  prioriza ejecución activa, búsquedas sin captura y últimas fechas conocidas.
  No se inventan fechas de alta. Un estado activo sin actualización reciente
  aparece Por verificar, con acceso a su seguimiento.
- La gestión de búsquedas conserva el bloqueo de snapshot. Solo las dos rutas
  exactas de control evitan ese bloqueo. No cambian scrapers, Jobs ni matching.

## Validación nueva

| Suite | Resultado |
| --- | --- |
| Consola completa | 445 aprobadas |
| Catálogo completo | 249 aprobadas |
| Scraper completo | 122 aprobadas |

Ejecutadas en esta tarea, en procesos separados y con datos sintéticos en `.tmp/`.
Incluyen escritorio 1440×900, tablet 768×1024 y móvil 390×844, ausencia de overflow,
cuatro secciones, nombre de navegación, resumen y estados, formulario reubicado,
alta y vuelta a Radar Central sin lanzar scraping, protección del snapshot y
regresiones de búsquedas Metrocuadrado/Wasi/Fincaraíz. Las cinco pruebas nuevas de
Radar Central están incluidas en consola, no se suman otra vez.

Las primeras comprobaciones detectaron un problema del simulador al seguir un 303
interceptado en Chromium; se corrigió el transporte ASGI de la prueba. Una medición
histórica de ancho se hacía antes de cargar estilos: ahora espera `load`, sin
cambiar el funcionamiento del matching. La última suite completa pasó.
`pip check`, compilación y `git diff --check` correctos. Se conserva la advertencia
conocida de BlockingPortal en Starlette/AnyIO.

Comprobación real por IAP: Inicio muestra las tres búsquedas existentes y estados;
Radar Central y Agregar búsquedas abren correctamente. Solo navegación/consulta:
no se guardó ninguna búsqueda real, no se ejecutó scraping ni Gemini. Los tres GET
sin sesión devuelven 302 a Google. Las altas de prueba usaron snapshots sintéticos.
El control remoto final conserva tres búsquedas y cero ejecuciones manuales.

## Revisión e impacto

Revisión web: `radar-central-20261113`, 0% de tráfico de producción.
`radar-verify-20261111` mantiene el 100%. Tag privado existente `ejecuciones-review`.
Build web SUCCESS: `58c805c6-1eb9-4409-9fa4-46ff80a7313b`.
Imagen: `us-central1-docker.pkg.dev/radar-inmobiliario-co/radar/web@sha256:63d77aa6fdf10f1b7f4e90f51648bb606fb5fd5cda807faee23b3aa99f065c25`.

No se añadieron recursos, permisos, secretos, programación ni cambios de IAP/OAuth.
Se actualizó únicamente la imagen web de la revisión privada. Los Jobs conservan
su imagen y configuración. Sin nuevas migraciones ni esquema de negocio.
La revisión sigue compartiendo datos y bloqueo con producción; no implica aislamiento.
Las visitas mantienen la persistencia web existente. Generación observada antes de
la comprobación: 1794563987624960; al cerrar: 1794565416224086. No se restauró ningún
snapshot ni se reemplazó una base con datos sintéticos. Las capturas existentes y
los tres IDs de búsquedas permanecen visibles en la consulta.

Para revertir esta presentación en la revisión privada, reasignar únicamente el
tag a `radar-ejecuciones-20261113-b`, sin cambiar porcentajes ni restaurar datos:

```powershell
& ../cloud.ps1 run services update-traffic radar --update-tags=ejecuciones-review=radar-ejecuciones-20261113-b --project=radar-inmobiliario-co --region=us-central1
```

## Git y archivos

Cambios locales, sin push, merge, tags ni conflictos. El original no fue destino
de escrituras del agente. El commit de evidencia posterior al runtime solo añade
este informe y su enlace; el árbol queda limpio.

- `AGENTS.md`
- `CHANGELOG.md`
- `RADAR_PROYECTO_RECTOR.md`
- `README.md`
- `catalogo/servicio.py`
- `consola/docs/EJECUCIONES.md`
- `consola/durable.py`
- `consola/ejecuciones.py`
- `consola/static/ejecuciones.css`
- `consola/templates/_gestion_busquedas.html`
- `consola/templates/v04/base.html`
- `consola/templates/v06/base06.html`
- `consola/templates/v06/ejecuciones06.html`
- `consola/templates/v06/fuentes06.html`
- `consola/templates/v06/inicio06.html`
- `consola/tests/test_browser.py`
- `consola/tests/test_ejecuciones.py`
- `consola/tests/test_fincaraiz.py`
- `consola/tests/test_fuentes_eliminar.py`
- `consola/tests/test_radar_central.py`
- `consola/tests/test_revision_local.py`
- `consola/tests/test_v06.py`
- `consola/tests/test_wasi.py`
- `consola/v06.py`
- `docs/README.md`
- `scraper/metro/__init__.py`
