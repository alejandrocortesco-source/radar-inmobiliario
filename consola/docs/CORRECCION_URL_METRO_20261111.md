# Corrección de URLs de Metrocuadrado — 11 de noviembre de 2026

Hallazgo posterior a la validación previa a Cloud. Base: `develop`, v0.11.0,
`fe29bb0cb071ca0bbb489b090495c7acdf88b19b`, con cambios locales preexistentes de
validación y presentación que se conservan. Sin commit, push ni despliegue.

## Problema y causa

La URL aportada por el usuario fue:

`https://www.metrocuadrado.com/apartamento-casa/arriendo/bogota/la-carolina?search=form`

El POST `/v0.6/fuentes` exigía literalmente `path.startswith('/inmuebles/')`.
La rechazaba antes de escribir o navegar, con el mensaje «Usa una URL de búsqueda
de Metrocuadrado, con ruta /inmuebles/». Las pruebas anteriores de registro de
Metrocuadrado solo usaban rutas `/inmuebles/`: faltaba esta familia de URLs.

El motor del scraper no exige ese prefijo: valida el dominio HTTP(S), navega a
la URL recibida y lee datos estructurados del listado y paginación. El defecto
confirmado está en la admisión de fuentes; no implica reconstruir el catálogo,
matching ni persistencia. Tampoco demuestra que la página real conserve los
selectores o el esquema esperado por el scraper.

## Corrección compatible

- `catalogo/fuentes/metrocuadrado.py` concentra la validación sintáctica para el
  formulario actual y el servicio usado por los formularios históricos.
- Admite las rutas históricas `/inmuebles/…` y las rutas por tipos con operación
  `venta` o `arriendo` y ubicación, incluyendo exactamente el ejemplo comunicado.
- Conserva dominio exacto, HTTP(S), puertos permitidos, ausencia de credenciales,
  límite de longitud y rechazo de espacios/controles y fichas `/inmueble/…`.
- No transforma la URL en `/inmuebles/arriendo/…`: perder `apartamento-casa`
  podría ampliar o cambiar la búsqueda. La identidad mantiene la ruta completa.
- La normalización existente conserva los filtros de query, ordena parámetros y
  elimina `search`, `src_url`, `utm_*` y fragmento. No se cambió ese contrato ni se
  fusionaron búsquedas históricas con las nuevas rutas.
- El formulario explica los dos formatos. Guardar sigue escribiendo únicamente
  configuración auxiliar y no inicia extracción ni llama a Gemini.

La validación es sintáctica, no una comprobación en vivo de que cada combinación
de slugs exista en el portal. No se añadió una consulta externa al guardar.

## Pruebas nuevas y regresión

Evidencia en `.tmp/metro-url-20261111/`, exclusivamente con bases sintéticas:

- Registro/duplicado: rutas histórica y por tipos, con conservación de un filtro
  `preciomax=3000000` y hash/bytes del catálogo inalterados.
- Paso desde fuentes registradas al comando CLI: recibe la ruta completa por
  tipos normalizada, sin convertirla en otra búsqueda. Ejecución CLI simulada.
- Chromium del formulario a 1440×900 y 768×1024: registra la URL exacta del usuario,
  muestra el mensaje de guardado sin extracción y detecta el duplicado al repetir.
- Chromium del descubrimiento del scraper: navega a esa URL con `search=form`,
  recibe HTML/React Flight sintético por interceptación de todas las peticiones,
  valida listado, DOM, fin de paginación, conteo y procedencia persistida. No se
  consultó el portal ni se capturó una ficha real.
- Rechazo de dominio parecido, credenciales, puertos inválidos, ficha individual,
  ruta incompleta, controles y esquema JavaScript.

Las 12 pruebas dirigidas pasaron. Las suites completas y sus resultados de cierre
se registran en `consola-cierre.xml`, `catalogo-cierre.xml` y `scraper-cierre.xml`
y sus respectivos logs. Consola: 392 aprobadas (235,41 s); catálogo: 249 aprobadas
(9,60 s); scraper: 122 aprobadas (50,66 s). Total sobre el estado actual, incluidos
los cambios preexistentes: **763 aprobadas**, sin fallos ni omisiones. Compilación
Python y `git diff --check` correctos; permanece la advertencia conocida de BlockingPortal.

El primer intento quedó sin avanzar dentro del sandbox de Windows. Se detuvieron
solo los procesos de pruebas de esta revisión y se repitieron fuera del sandbox,
con carpetas sintéticas nuevas. No se cuentan esos intentos como pruebas aprobadas.

## Instancia y límite de la comprobación

Se reinició exclusivamente la instancia sintética de revisión en
`http://127.0.0.1:8765/v0.6/`, conservando sus bases y cargando la corrección.
Se verificó HTTP 200, health y la ayuda nueva. Otras instancias preexistentes,
incluida cualquier instancia operativa en el puerto 8000, no se reiniciaron.

No hubo extracciones reales, uso real de Gemini ni escrituras en bases operativas.
La herramienta web no pudo abrir la página aportada. Por tanto, sigue pendiente
comprobar con autorización posterior la respuesta auténtica de esa búsqueda y
una extracción acotada en almacenamiento aislado. Aceptar/guardar su URL queda
comprobado; compatibilidad con el contenido actual del portal no se da por probada.

Archivos de esta corrección: `catalogo/fuentes/metrocuadrado.py`,
`catalogo/servicio.py`, `consola/v06.py`,
`consola/templates/v06/_fuente_form.html`, `consola/tests/test_v06.py`,
`catalogo/tests/test_urls_metrocuadrado.py`, `scraper/tests/test_metro_url.py`,
este informe y su enlace en `docs/README.md`. Los demás cambios pendientes eran
anteriores a esta corrección y se conservan.
