# Validación realizada — 24 de octubre de 2026

Este informe describe la ejecución original del componente. Tras su reorganización, las rutas de datos, código, herramientas y pruebas indicadas aquí son relativas a `scraper/`. Los datos originales se conservaron en `scraper/data/`, excluidos de Git. Para comandos desde la raíz con el entorno existente, usar `.venv\Scripts\python.exe scraper\run.py`; las instrucciones actuales están en [el README del scraper](../README.md).

## Resultado real

Búsqueda: https://www.metrocuadrado.com/inmuebles/venta/bogota/la-carolina?search=form

Ejecución **1** en `data/metro.sqlite`, del 24/10/2026 a las **07:11:06–07:20:54 (Bogotá)**. La base guarda las fechas correspondientes en UTC.

| Medida | Resultado |
|---|---:|
| Total anunciado en el JSON público | 427 |
| Páginas detectadas y guardadas | 9 |
| Resultados principales por página | 50 en las primeras 8; 27 en la última |
| Anuncios únicos | 427 |
| Apariciones duplicadas entre páginas | 8 |
| Fichas correctas | 427 |
| Fichas parciales / fallidas / pendientes | 0 / 0 / 0 |
| Reintentos necesarios | 0 |
| URLs de fotografías | 7.381 |
| Fichas sin descripción / sin fotos | 0 / 0 |
| Errores de normalización registrados | 0 |
| `PRAGMA integrity_check` | `ok` |

Las URLs de fotos incluyen variantes publicadas de una misma imagen; la cifra no representa necesariamente 7.381 imágenes distintas. No se descargaron los archivos de imagen durante el scraper.

Tipos encontrados: 384 apartamentos, 25 oficinas, 9 casas, 3 casas lote, 3 consultorios, 1 finca, 1 edificio de apartamentos y 1 apartaestudio. Los tipos proceden del portal; no se infirieron del título.

Primero se hizo una prueba limitada a dos páginas y cinco fichas. Después se reanudó el mismo ID, se verificaron las huellas de ambas páginas y se completaron las restantes y las fichas pendientes. Los cinco éxitos originales no se repitieron. Por eso `runs.config_json` conserva los límites de la configuración inicial, aunque la ejecución completa posterior ya no los usó; los eventos distinguen ambas invocaciones. Las invocaciones futuras también guardan su configuración efectiva en `run_started`.

## Pruebas locales

* **14 pruebas automatizadas aprobadas**: muestras reales de apartamento/oficina/consultorio, referencias Flight, texto multilínea, deduplicación, exclusión de recomendaciones, ausencias frente a errores y ceros, filtrado de sesión, transacciones y recuperación, API, HTML escapado, límites y restricciones de acceso.
* **Interfaz comprobada con Chromium headless** en escritorio 1440 px y móvil 390 px: listado, apertura de una ficha y renderizado sin errores JavaScript. La vista móvil conservó un ancho de documento de 390 px. Capturas en `data/verification/`.
* FastAPI iniciado en `http://127.0.0.1:8000`. Exportación y consulta de trazabilidad comprobadas.
* Entorno `.venv`, dependencias y Chromium instalados. Versiones directas en `requirements.txt` y todas las versiones instaladas en `requirements.lock.txt`.
* Un aviso de deprecación de Starlette/AnyIO aparece al ejecutar pytest; no produjo fallos.

## Límites comprobados del entorno

El aislamiento inicial bloqueaba DNS y temporales. Las instalaciones, la navegación real y las pruebas que necesitaban esos permisos se ejecutaron con la aprobación correspondiente fuera del aislamiento. No se eludieron restricciones del portal.

**Modo visible:** `--headed` está implementado, pero su prueba no pudo iniciar el ejecutable completo de Chromium. Playwright informó `BrowserType.launch: spawn UNKNOWN`; al ejecutar ese mismo `chrome.exe` directamente, Windows informó que «la configuración en paralelo no es correcta» (error de carga Side-by-Side). El Chromium headless separado sí funcionó durante todo el recorrido. El fallo visible quedó registrado en `data/headed-test.sqlite`, separado de los 427 resultados. No se modificaron componentes de Windows para corregirlo. Se necesita resolver esa dependencia/configuración del navegador en el equipo para validar el modo visible.

**Docker/Cloud Run:** se entregó el Dockerfile y separación por procesos, pero Docker no está instalado en este entorno. No se construyó la imagen ni se desplegó un Job; la persistencia durable de SQLite en Cloud Run necesita configurar almacenamiento adecuado, como explica el README.

Los campos no publicados permanecen ausentes. «Ficha correcta» significa que el objeto público del inmueble se leyó y normalizó sin errores; no garantiza que el anunciante haya publicado todos los campos posibles ni que los datos del anuncio sean exactos.

## Evidencia reproducible

* Base: `data/metro.sqlite`.
* Auditoría: `data/verification/integrity.json`, regenerable con `.venv\Scripts\python.exe tools\verify_output.py 1`.
* Exportación completa: `data/metro-run-1.json` y botón de exportar en la interfaz.
* Navegación y errores: tablas `pages` y `events`, y `data/scraper.log`.
* Inspecciones: `data/inspection/`; muestras mínimas: `tests/fixtures/`.
* Capturas de interfaz: `data/verification/dashboard.png`, `detail.png`, `mobile.png`.

## Comprobación tras reorganizar Radar Inmobiliario

El 24/10/2026 se movió el componente a `scraper/`, conservando `.git` en la raíz, el commit `646bf7be11addc9a852b90b7eff8631c742f38c9` y la etiqueta `v0.1.0`. No se modificó la configuración de remotos ni se hizo commit o push de la reorganización.

* **17 pruebas aprobadas** desde la raíz (`.venv\Scripts\python.exe -m pytest -c scraper/pytest.ini -q`) y desde `scraper/` (`..\.venv\Scripts\python.exe -m pytest -q`). Incluyen la ejecución del punto de entrada desde una carpeta ajena y la resolución de rutas de datos.
* `scraper/run.py status 1` y `python -m metro status 1` desde el componente acceden a los **427 anuncios originales**. La base trasladada conserva `integrity_check = ok`, 427 fichas correctas y ninguna fallida.
* Una nueva prueba real limitada a una página y una ficha guardó **51 enlaces** y **1 ficha correcta**, en `scraper/data/reorganization-check.sqlite`. Su estado `incomplete` y salida 2 son los esperados por los límites de prueba; no alteró la ejecución original.
* El lanzador `scraper/start-interface.ps1` inició FastAPI desde su nueva ubicación con el entorno existente de la raíz. Chromium verificó listado y detalle, vistas de escritorio y móvil, sin errores JavaScript; el documento móvil mantuvo 390 px de ancho.
* Se comprobaron las exclusiones Git de datos, bases de prueba, `.venv`, `.env` y cachés. Los 30 archivos de la versión anterior se conservaron en sus ubicaciones correspondientes. No hay repositorios Git anidados.

No se volvió a recorrer toda la búsqueda durante esta comprobación ni se repitieron las pruebas de Docker o Chromium visible; permanecen los límites documentados anteriormente. El entorno virtual existente se mantiene en la raíz, ignorado por Git, para evitar romper las rutas de Windows. Las instalaciones nuevas pueden crear su entorno dentro de `scraper/`.

## Campo de ubicación en mapa

Se inspeccionó `#location-section` en el consultorio `3312-M7166280`, activando la carga diferida de la sección como hace el botón «Ver lugares cercanos». El mapa Leaflet usa las coordenadas públicas de la ficha; sus enlaces de atribución no son enlaces al inmueble y el botón de nueva búsqueda abre el mapa general. Por ello `map_url` es un enlace derivado a OpenStreetMap y `portal_map_url` apunta a la sección original. Ambos conservan evidencia y `derived: true` en `fields`.

El enriquecimiento local dejó **425 anuncios con mapa y 2 ausentes por falta de coordenadas**, sin modificar fechas ni estados originales. SQLite mantuvo `integrity_check = ok`. La exportación local también se regeneró con los campos nuevos. Una extracción real limitada a una página y una ficha, en `data/location-check.sqlite`, confirmó que las nuevas capturas los guardan automáticamente.

**28 pruebas aprobadas**, incluidos datos reales, coordenadas ausentes e inválidas, indicación de ubicación aproximada, persistencia, API y exportación. Chromium comprobó el botón de mapa en la interfaz del consultorio señalado; captura en `data/verification/location.png`. No se hizo commit ni push.

## Monitor de recursos

Se añadió un envoltorio de `Scraper.run()` y un muestreador independiente con psutil, sin modificar el cuerpo de la ejecución ni la lógica de extracción. La igualdad del cuerpo previo y el actual se verificó comparando sus árboles de sintaxis (AST). Las mediciones se guardan en CSV independientes; no se agregaron campos a los documentos ni tablas de resultados.

Una prueba real limitada a una página y dos fichas en `data/resource-check.sqlite`, el 24/10/2026, registró **23,08 s (0,38 min)**, **11,94 s de CPU**, **51,72 % de uso medio relativo a un núcleo**, **567,10 MiB de pico RSS observado** y **7 procesos simultáneos**, en 194 muestras con espera configurada de 0,1 s. Sus 2 fichas fueron correctas; el estado final incompleto se debe a los límites explícitos de prueba. Esta medición pequeña no estima por sí sola una búsqueda completa.

Los archivos son `data/metrics/resource_usage.csv` y `data/metrics/samples-20261024T181435407670Z-4e044f86.csv`. La suite completa terminó con **41 pruebas aprobadas**, y `pip check` no encontró dependencias incompatibles. Las nuevas pruebas cubren consumo real de un proceso hijo, CPU de procesos que terminan, reutilización de PID, memoria del árbol completo, append de varias invocaciones, accesos denegados, interrupción y fallo de la ejecución, y fallos de escritura que no alteran el resultado del scraper. Se prueban los contadores opcionales de cgroup v2 con archivos simulados; no se ejecutó un contenedor Linux/Cloud Run en este equipo Windows. La base original se verificó en modo de sólo lectura: conserva sus 427 anuncios y `integrity_check = ok`.

Consulta [las unidades, el alcance del muestreo y su uso para dimensionar Cloud Run](RECURSOS.md). No se hace una estimación monetaria ni se modifica el despliegue.

## Scraping incremental por precio

Se mantuvo el scraper existente y se añadió planificación de fichas por comparación monetaria, disponibilidad por búsqueda e historial de precios. El usuario confirmó COP para las URLs configuradas; el listado real muestra `$` sin un código de moneda explícito. El modo `--listing-currency unknown` conserva la revisión por ficha cuando no hay confirmación.

La suite terminó con **90 pruebas aprobadas**: formatos y monedas, operación de venta/arriendo/oferta dual, nuevos/modificados/sin cambios, conservación exacta de la ficha reutilizada, discrepancias de precios, reintentos de fichas parciales, búsquedas vacías, múltiples URLs con una sola cola de detalle, migración con respaldo, dos ausencias completas, reapariciones e idempotencia. Los cambios de precio y retirados se verificaron con escenarios controlados; no se provocaron modificaciones o retirados de anuncios reales en el portal.

La migración real de los 427 anuncios conservó las instantáneas originales y creó `data/metro.pre-incremental.sqlite`. Las pruebas completas iniciales se ejecutaron sobre `data/incremental-validation.sqlite`, una copia SQLite consistente del catálogo. Se identificaron tres ofertas de «Venta y Arriendo» con precio normalizado ausente en la versión anterior; se inspeccionó el componente público del listado y se corrigió su normalización sin confundir venta y arriendo.

En la ejecución **5 de la copia de validación**, el scraper recorrió las **9 páginas**, volvió a encontrar **427 IDs únicos** y los clasificó **todos como `unchanged`, sin abrir ninguna ficha**. El monitor registró **19,10 s**, **19,47 s de CPU**, **779,12 MiB de pico RSS observado** y 6 procesos simultáneos. Es una medición de una ejecución concreta, no una garantía de tiempo o costo diario.

Después se ejecutó el flujo nuevo en la base principal: ejecución **2**, las 9 páginas y 427 anuncios, con **424 fichas reutilizadas y 3 revisadas una vez para reparar su normalización antigua**. Terminó `completed`, sin conflictos ni retirados. Las 427 fichas de la ejecución original 1 se conservaron.

Chromium verificó el resumen incremental, el filtro `unchanged`, el catálogo de disponibilidad y la ficha; sin errores JavaScript, con ancho móvil de 390 px. Capturas: `data/verification/incremental-dashboard.png` y `incremental-mobile.png`. La aplicación quedó disponible en `http://127.0.0.1:8000/`; la nueva vista es `/catalog`. No se instaló un cron ni se hizo commit o push.
