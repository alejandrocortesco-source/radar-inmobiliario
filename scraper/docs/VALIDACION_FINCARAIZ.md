# Validación Fincaraíz — v0.9 local

> Alcance temporal: los resultados y límites de este informe corresponden al hito descrito. El estado actual integra tres fuentes e [identificación supervisada](../../docs/IDENTIFICACION.md); no acredita despliegue, autenticación de personas, Scheduler activo ni consumo mensual verificado. Gemini sigue opcional y no participa en identidad física.


Fecha: **9 de noviembre de 2026, America/Bogota**. Base comprobada `66083ed` en `develop`; índice y árbol inicialmente limpios. La versión v0.9 identifica esta nueva función compatible; no se creó commit ni tag. No hubo push, merge, publicación o despliegue. Las referencias históricas no se modificaron.

## Implementación revisada

- Configuración por URL y criterios con IDs/etiquetas observados, verificación de una página antes de guardar, persistencia de URL original/efectiva/filtros, revisiones, edición y activación. Guardar no inicia captura.
- Motor incremental común, identidad por fuente e ID, deduplicación entre búsquedas y conservación de procedencias. Comparación de precios COP, historial, checkpoints y recuperación.
- Recorrido por enlaces del portal, validación de página/filtros/totales, detección de repetición y cobertura incompleta. Protección de ausencias y de documentos fiables ante fallos, pérdida de campos o galería.
- Catálogo integrado, ficha, administración, áreas, ubicación, anunciante/perfil, CSV, dashboard de cuatro secciones y matching/decisiones sin cambiar Gemini.
- Job y snapshot durable incluyen la fuente, sin desplegar ni configurar un horario.

## Pruebas automatizadas realmente ejecutadas

Todas las regresiones usan **SQLite sintético en `.tmp/` o `tmp_path`** y portales interceptados. Se ejecutaron procesos separados de pytest, con las rutas de imports descritas en [V06](../../consola/docs/V06.md). Chromium y TestClient se ejecutaron fuera del sandbox de Windows para disponer de subprocess y sockets locales. No se tocaron bases operativas.

| Ejecución final | Resultado |
| --- | --- |
| `catalogo/tests` | 228 aprobadas, 10,22 s |
| `scraper/tests` | 121 aprobadas, 81,88 s |
| `consola/tests` | 297 aprobadas, 223,50 s |
| Total de las suites completas | **646 aprobadas** |

Tras completar la protección de galería, `scraper/tests/test_fincaraiz.py` se repitió: **9 aprobadas, 11,41 s**. Tras comprobar las tres fuentes simultáneas con un mismo ID original y cerrar el encabezado v0.9, `consola/tests/test_fincaraiz.py` se repitió: **6 aprobadas, 13,82 s**. Esta última pasada añade **un caso nuevo** de tres fuentes a los cinco ya incluidos en la suite: **647 casos distintos verificados**, sin sumar las repeticiones como casos adicionales.

Las nuevas pruebas cubren parámetros de URL, rechazo de fichas/dominios ajenos, criterios no reproducibles, persistencia/revisiones/estado, desconocidos/ceros/errores, ubicación principal frente a asociadas, áreas y etiqueta de antigüedad, identidad, historial, duplicados entre búsquedas, conservación de la ficha previa, bajas falsas, paginación de dos páginas, checkpoints, repetición y cambio de filtros, límites incompletos, finalización exitosa y disparo de matching, snapshots, CSV, agrupación de anunciantes y conservación de decisiones al recalcular. La regresión adicional verifica el mismo código en Metrocuadrado, Wasi y Fincaraíz, acceso por UUID/fuente:ID y rechazo del código ambiguo.

Chromium recorrió el formulario a **1440×900, 768×1024 y 390×844**, comprobó controles, foco, errores y ausencia de desbordamiento de página. Las suites existentes comprobaron además estados vacíos, tablas con desplazamiento propio y flujos sin JavaScript de las fuentes anteriores. Se inspeccionaron capturas nuevas de escritorio y móvil en `.tmp/fincaraiz-v09/screenshots/`. El cambio de modo oculta los campos de la otra modalidad; se mantienen labels y funcionamiento de preparación de formulario sin JavaScript.

`compileall`, ayuda del CLI Fincaraíz, ayuda de Jobs y `git diff --check` pasaron. Persiste la advertencia conocida de deprecación de `BlockingPortal` en Starlette/AnyIO; no afecta el resultado. La primera prueba de UI usó un nombre de fixture incorrecto y se corrigió antes de las pasadas aprobadas; no se cuenta ese intento como validación.

## Inspección y validación real acotada

La solicitud de esta tarea autoriza consultas reales acotadas, como excepción explícita al uso exclusivo de fixtures para las regresiones. Toda la evidencia y almacenamiento de validación permanecen en **`.tmp/fincaraiz-v09/`**, aislados de los datos de Mónica. No se usó sesión manual, login, contactos enviados ni formularios para habilitar teléfonos.

Se comprobó mediante Chromium la [búsqueda de referencia](https://www.fincaraiz.com.co/venta/casas-y-apartamentos/la-carolina/zona-norte/bogota), un enlace real a su página 2 y una ficha publicada. Se verificaron también siete enlaces de filtros publicados por esa página para ofrecer opciones iniciales reales. No se fabricaron endpoints ni slugs. En ese momento el portal anunció **267 resultados**, con **21 en cada una de las primeras dos páginas**; no son constantes de implementación.

Se confirmó `pageProps.params.filters`, `fetchResult.searchFast`, sus metadatos de paginación y `pageProps.data/technicalSheet` en la ficha. La página 2 añade `filters.page`: se comprueba su número, manteniendo iguales los filtros de negocio. Los listados contienen ya ficha técnica, descripción, imágenes y anunciante en los casos inspeccionados.

Se verificó el registro por URL en la base auxiliar aislada y la resolución por criterios con una segunda comprobación real de filtros. Después se ejecutó el adaptador dos veces con **máximo dos páginas y tres trabajos nuevos de captura por ejecución**. Los resultados finales fueron:

| Ejecución aislada | Páginas | IDs únicos observados | Capturas nuevas fiables | Reutilizadas | Estado |
| --- | --- | --- | --- | --- | --- |
| 3 | 2 | 42 | 3 | 6 | incompleta por límites |
| 4 | 2 | 42 | 3 | 9 | incompleta por límites |

Las ejecuciones 1 y 2 de diagnóstico detectaron el campo adicional de navegación y se conservaron como evidencia incompleta. Tras el ajuste, las ejecuciones 3 y 4 recorrieron las dos páginas sin perder filtros. La repetición mantuvo **42 filas de anuncio**, sin duplicarlas. Incluyendo las capturas previas de diagnóstico, el almacén aislado terminó con **12 documentos fiables**, **10 nombres exactos de anunciante** y **5 discrepancias entre áreas**. No hubo contactos completos de teléfono/WhatsApp en esos documentos. Se preservaron los anunciantes, los enlaces de perfil y las publicaciones originales. Un indicador `has_whatsapp` o un teléfono enmascarado no se presentó como contacto.

El caso inspeccionado `194465607` entrega **78 m² publicados** y **72,12 m² construidos/privados**. Se conservaron los tres valores y su discrepancia. Su código de antigüedad `3` tiene etiqueta **«9 a 15 años»**; no se convirtió en tres años. La ubicación principal y las asociadas se conservaron separadas. El barrio de la URL nunca se copió a todas las fichas.

Ninguna de estas ejecuciones acotadas declaró cobertura completa ni confirmó ausencias. El cierre exitoso, recálculo automático y conservación de decisiones se comprobaron con datos sintéticos, no con clientes reales. Los 42 anuncios observados no equivalen a haber capturado todas las fichas de la búsqueda.

## Límites y pendientes

- La validación inicial no incluyó extracción completa. La captura operativa completa autorizada posteriormente se documenta en el apartado siguiente; Cloud Run sigue pendiente.
- El modo criterios inicia con correspondencias verificadas de La Carolina/Bogotá y se amplía mediante URLs verificadas. No hay un catálogo nacional de ubicaciones ni se inventan búsquedas para combinaciones no comprobadas.
- No se prometen teléfonos: contactos enmascarados o sujetos a formulario permanecen no disponibles. No se enviaron datos personales ni mensajes.
- Ubicación principal desconocida o sin equivalencia controlada permanece pendiente; ubicaciones asociadas no confirman matching. Antigüedad en intervalo conserva la limitación del motor existente.
- No se construyó ni ejecutó una imagen Docker en esta validación. La inclusión en Dockerfile/Jobs y la persistencia de snapshot se verificaron localmente; faltan validación real Cloud Run/Cloud Storage, recuperación remota, ejecución posterior desatendida y costes. No se desplegó, pagó ningún servicio ni programó ejecución nocturna.
- La app se entrega como código local listo para iniciar o reiniciar con `python scraper/run.py serve`; no se reinició un servicio sobre bases operativas.

## Captura operativa posterior y commit autorizado

El 9 de noviembre de 2026, después de cerrar la implementación, el usuario solicitó ejecutar Fincaraíz para completar el catálogo. Se registró la búsqueda de referencia en la base auxiliar operativa y se ejecutó sin límites de páginas ni anuncios, usando el bloqueo de escritor existente. Esta fue una operación solicitada sobre el catálogo real, distinta de las pruebas sintéticas y de las inspecciones acotadas anteriores.

La ejecución local **1** terminó `completed` el **9 de noviembre de 2026 a las 20:09:32 de Colombia**: **13 páginas, 267 anuncios nuevos, 267 capturas correctas, cero errores, cero duplicados y cero reintentos**. Duración medida del proceso: **37,04 s**. Se completó el flujo posterior de actualización de matching sin registrar errores. La API local respondió HTTP 200 y total 267 para `fuente=fincaraiz`. El catálogo integrado contenía entonces **774 anuncios**: Metrocuadrado 439, Wasi 68 y Fincaraíz 267. No se ejecutaron nuevamente las otras fuentes ni se cambiaron sus documentos.

Las bases, anuncios y métricas operativas permanecen en almacenamiento local ignorado por Git; este commit conserva código, pruebas, configuración pública de opciones y documentación, sin datos del catálogo ni información privada. No se afirma que esta ejecución local valide Docker o Cloud Run.

La siguiente instrucción del usuario autoriza **hacer commit de esta versión** en `develop`. Se prepara el commit local `feat(v0.9): integrar Fincaraíz como tercera fuente`, sin crear tag, push, merge, Release o despliegue. Los 647 casos documentados arriba se ejecutaron durante la implementación; no se presentan como pruebas nuevas de este paso de commit. Antes de registrar el commit se revisan diff, alcance, archivos ignorados, ausencia de datos privados y `git diff --check`. El hash resultante se informa al usuario, sin incorporarlo dentro de su propio contenido.

## Archivos y conservación

Cambios locales de esta tarea, sin conflictos, commits ni cambios previos ajenos. Los archivos privados de `.local/`, datos operativos, secretos y referencias Git se conservaron. Implementación nueva en `scraper/fincaraiz/`, normalización/resolución en `catalogo/fuentes/`, presentación en `consola/` y persistencia detrás del adaptador auxiliar existente.

Archivos modificados o añadidos:

- `AGENTS.md`
- `Dockerfile.jobs`
- `RADAR_PROYECTO_RECTOR.md`
- `README.md`
- `catalogo/README.md`
- `catalogo/fuentes/fincaraiz.py`
- `catalogo/fuentes/fincaraiz_opciones.json`
- `catalogo/modelos.py`
- `catalogo/persistencia/_metrocuadrado.py`
- `catalogo/persistencia/busquedas.py`
- `catalogo/persistencia/integrado.py`
- `catalogo/servicio.py`
- `consola/README.md`
- `consola/presentacion.py`
- `consola/rutas.py`
- `consola/static/wasi.js`
- `consola/templates/_dato_fuente.html`
- `consola/templates/_fincaraiz_datos.html`
- `consola/templates/_gestion_busquedas.html`
- `consola/templates/anunciante.html`
- `consola/templates/ficha.html`
- `consola/templates/v04/ficha.html`
- `consola/templates/v06/_fuente_form.html`
- `consola/templates/v06/base06.html`
- `consola/templates/v06/inicio06.html`
- `consola/tests/conftest.py`
- `consola/tests/test_fincaraiz.py`
- `consola/v06.py`
- `docs/ESTRUCTURA.md`
- `docs/README.md`
- `oportunidades/README.md`
- `oportunidades/automatizacion.py`
- `oportunidades/servicio.py`
- `scraper/README.md`
- `scraper/docs/FINCARAIZ.md`
- `scraper/docs/VALIDACION_FINCARAIZ.md`
- `scraper/fincaraiz/__init__.py`
- `scraper/fincaraiz/__main__.py`
- `scraper/fincaraiz/browser.py`
- `scraper/fincaraiz/extraction.py`
- `scraper/fincaraiz/scraper.py`
- `scraper/fincaraiz_run.py`
- `scraper/job.py`
- `scraper/tests/test_fincaraiz.py`
- `scraper/wasi/durable.py`
