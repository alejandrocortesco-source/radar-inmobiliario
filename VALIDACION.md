# Validación realizada — 24 de octubre de 2026

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
