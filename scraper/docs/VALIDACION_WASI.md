# Verificación de v0.8 — Wasi y preparación de Cloud Run Jobs

## Verificación histórica de implementación — 8 y 9 de noviembre de 2026

Este apartado conserva el informe recibido con los cambios locales. Sus resultados y la captura operativa descrita más abajo corresponden a ejecuciones anteriores; no son pruebas nuevas de la revisión para el commit v0.8. El cierre de esa revisión se registra al final.

| Suite | Resultado |
| --- | --- |
| Consola, con Chromium | 292 aprobadas |
| Catálogo | 228 aprobadas |
| Scraper, con portal Wasi simulado en Chromium | 112 aprobadas |
| Total de casos de las tres suites | **632 aprobadas** |

Las tres suites se ejecutaron de nuevo el 9 de noviembre: consola 259,41 s, catálogo 14,92 s y scraper final 88,28 s. Las regresiones de país preseleccionado y reaplicación tras «Usar aquí» también se ejecutaron por separado: dos aprobadas, sin sumarlas de nuevo al total. Se verificaron `compileall`, CLI `wasi_run.py --help`, generación de horario `job.py --schedule` y `git diff --check`. Persiste la advertencia de deprecación `BlockingPortal` de Starlette/AnyIO. El sandbox bloquea sockets locales; las ejecuciones con HTTP/Chromium se realizaron fuera del sandbox, con bases sintéticas bajo `.tmp/`.

Comando utilizado desde la raíz, en procesos separados:

```powershell
foreach ($radarSuite in @('consola', 'catalogo', 'scraper')) {
    .\.venv\Scripts\python.exe -c "import sys,pathlib; r=pathlib.Path.cwd(); sys.path[:0]=[str(r),str(r/'scraper'),str(r/'consola/tests')]; import pytest; raise SystemExit(pytest.main(['--rootdir=.','-o','pythonpath=',sys.argv[1]+'/tests','-q','--basetemp=.tmp/pytest-wasi-verificacion-'+sys.argv[1]]))" $radarSuite
    if ($LASTEXITCODE -ne 0) { throw "Falló la suite $radarSuite" }
}
```

La suite de Wasi intercepta todas las solicitudes del navegador con páginas sintéticas. Verifica login automático, sesión reutilizada/caducada, rechazo, CAPTCHA, secreto ausente y ausencia de secretos en evidencias. Comprueba paginación, mayor tamaño de página ofrecido, galería sin descargas, recuperación tras paginación incompleta, reuse sin abrir fichas y contactos específicos por inmueble. Las pruebas de persistencia cubren nuevos, cambios de precio, revisión, conflictos entre búsquedas, deduplicación, conservación de ficha fiable y ausencias por búsqueda. El adaptador durable se prueba con SQLite sintético y un cliente GCS simulado que exige generaciones y exclusión mutua.

Las regresiones de consola cubren códigos iguales entre fuentes con UUID distintos, API inequívoca, filtros, CSV por oferta, ficha con desconocidos/errores, anunciantes, indicadores, matching y decisiones independientes. Guardar/editar no crea una base de captura. Actualizar opciones es una acción separada y sustituida por un adaptador simulado en pruebas. El formulario se recorrió a 1440, 768 y 390 px, también a 390 px sin JavaScript: labels, foco, dependencias, guardado, edición y ausencia de desbordamiento. Se inspeccionaron capturas desktop y móvil de SQLite sintético, conservadas solo en `.tmp/`.

## Captura operativa autorizada el 9 de noviembre

El usuario solicitó poblar el catálogo real con apartamentos en venta de La Carolina, Bogotá. Proporcionó la ubicación de archivos privados externos y autorizó pulsar el enlace normal «Usar aquí». Se comprobó login automático real sin introducir secretos en el repositorio, evidencias o configuración de búsquedas. No se persiste sesión. Esto es una operación autorizada sobre el catálogo, separada de las pruebas sintéticas.

La configuración real usa Colombia / Cundinamarca / Bogotá D.C. / Usaquén, Apartamento, Vender y el control textual `Título = La Carolina`. El selector inspeccionado de zonas no ofrece La Carolina; no se inventó una equivalencia ni se promete cobertura geográfica de todo el barrio. El portal entregó 68 anuncios en dos páginas (50 y 18), sin límites artificiales. Se guardó una copia local de la base auxiliar antes de registrar esta búsqueda.

La primera ejecución conservó checkpoints e incidencias. La inspección real reveló que el código del modal cambia antes que el contenido y que Fotorama cambia la miniatura antes de cargar la imagen activa. Se corrigieron esas esperas y la carga del panel de contactos. Las imágenes se responden con un SVG local para mantener la galería sin descargar multimedia. Las 13 capturas previas con galerías incompletas quedaron marcadas mediante los estados técnicos existentes para revisión conservadora, conservando documentos e historial; la ejecución 1 quedó incompleta y no confirmó ausencias. La ejecución 2 vuelve a capturarlas y recorre la búsqueda íntegra. Dos fichas verificadas con el extractor corregido recuperaron 20 y 28 fotografías respectivamente, con código, título, precio y empresa coincidentes.

**Resultado final:** ejecución 2 completada el 9 de noviembre a las 11:40, hora de Colombia. Dos páginas, 68 anuncios únicos, 68 fichas abiertas y fiables, cero reutilizadas en esta primera captura completa, cero trabajos pendientes/fallidos/parciales y cero conflictos de listado. Se conservó una incidencia histórica de opciones dependientes, recuperada al reanudar; no se borraron evidencias para presentar un historial limpio. Los 68 anuncios permanecen activos y sin `needs_refresh`. Se conservaron 1.470 URLs originales de fotos, con hasta 51 por anuncio.

La lectura HTTP final del catálogo devuelve 507 anuncios: 439 Metrocuadrado y 68 Wasi. Inicio, catálogo completo y catálogo filtrado por Wasi responden HTTP 200. La exportación de Wasi devuelve 73 filas por oferta, incluyendo anuncios con más de una operación; no representa duplicación de fichas. Estos son controles operativos de solo lectura, separados de las pruebas sintéticas.

Medición local de la pasada completada: 1.198,90 segundos (19,98 minutos), 1.360,84 segundos de CPU del árbol y pico de RAM de 2.124,04 MiB, incluyendo Chromium. Son mediciones Windows de una captura inicial completa con galerías, no mediciones de Cloud Run ni una estimación de facturación. El siguiente dimensionamiento en Google Cloud debe tomar ese pico como referencia inicial y volver a medirse. Se conservan CSV técnicos en `scraper/data/metrics/wasi/`.

Al cerrar Chromium aparecieron avisos de tareas pendientes de `Response.finished()` en Playwright 1.55; el código de salida fue 0 y los 68 documentos ya estaban confirmados. Se sustituyó esa espera por el evento normal `requestfinished`, manteniendo la confirmación de respuesta y sin leer cuerpos privados. La regresión sintética comprueba también el cierre sin esos avisos. No se repitió toda la extracción real para probar ese cambio final.

Las pruebas automatizadas utilizan exclusivamente bases y páginas sintéticas. No se contactaron anunciantes ni se solicitaron alianzas. No se desplegó ni se creó Scheduler. Docker no está disponible en el ejecutor, por lo que la imagen no se construyó.

Quedan pendientes: construcción de imagen, validación real de Secret Manager/ADC/IAM y snapshots, primera ejecución Cloud Run y una ejecución posterior sin intervención. El login local no acredita funcionamiento desatendido en Google Cloud. Rendimiento facturable y presupuesto mensual inferior a US$10 pendientes de medición. Sheets conserva contratos sustituibles, sin migración implementada. Ver [configuración, comandos y recuperación](WASI.md).

## Git y conservación

Al cerrar la implementación previa, la rama era `v0.6` y HEAD conservaba `9db935a` (`feat(v0.7): incorporar anunciantes, contactos e inmuebles relacionados`). En esa etapa no se creó commit ni hubo conflictos Git, merge, push o despliegue. La carpeta raíz `docs/` ya estaba sin seguimiento y no se modificó. La revisión posterior autorizada para el commit v0.8 conserva ese diagnóstico fuera del commit por contener referencias de cuenta y operaciones reales ajenas al código de esta entrega.

## Archivos de esta entrega

- `.dockerignore`
- `AGENTS.md`
- `Dockerfile.jobs`
- `RADAR_PROYECTO_RECTOR.md`
- `README.md`
- `catalogo/README.md`
- `catalogo/fuentes/__init__.py`
- `catalogo/fuentes/wasi.py`
- `catalogo/fuentes/wasi_opciones.json`
- `catalogo/persistencia/_metrocuadrado.py`
- `catalogo/persistencia/busquedas.py`
- `catalogo/persistencia/contrato.py`
- `catalogo/persistencia/integrado.py`
- `catalogo/persistencia/sqlite.py`
- `catalogo/servicio.py`
- `catalogo/tests/test_api.py`
- `consola/README.md`
- `consola/rutas.py`
- `consola/static/v06.css`
- `consola/static/wasi.js`
- `consola/templates/_dato_fuente.html`
- `consola/templates/_gestion_busquedas.html`
- `consola/templates/ficha.html`
- `consola/templates/v04/ficha.html`
- `consola/templates/v06/_fuente_form.html`
- `consola/templates/v06/base06.html`
- `consola/templates/v06/inicio06.html`
- `consola/tests/conftest.py`
- `consola/tests/test_browser.py`
- `consola/tests/test_fuentes_eliminar.py`
- `consola/tests/test_wasi.py`
- `consola/v06.py`
- `oportunidades/automatizacion.py`
- `oportunidades/servicio.py`
- `scraper/README.md`
- `scraper/docs/INCREMENTAL.md`
- `scraper/docs/VALIDACION_WASI.md`
- `scraper/docs/WASI.md`
- `scraper/examples/wasi-usaquen.json`
- `scraper/examples/wasi-la-carolina.json`
- `scraper/job.py`
- `scraper/metro/scraper.py`
- `scraper/metro/storage.py`
- `scraper/metro/web.py`
- `scraper/requirements-cloud.txt`
- `scraper/tests/fixtures/wasi_network.html`
- `scraper/tests/test_wasi.py`
- `scraper/wasi/__init__.py`
- `scraper/wasi/__main__.py`
- `scraper/wasi/auth.py`
- `scraper/wasi/browser.py`
- `scraper/wasi/durable.py`
- `scraper/wasi/extraction.py`
- `scraper/wasi/locking.py`
- `scraper/wasi/options.py`
- `scraper/wasi/scraper.py`
- `scraper/wasi_run.py`

## Revisión para el commit v0.8 — 9 de noviembre de 2026

Se comprobó la base esperada `9db935ae398c93203cfaa3f7ebf7817d1904d17a` en la rama `v0.6`, se revisaron el diff completo y los archivos nuevos y se conservó el trabajo existente. Se actualizó la versión funcional a v0.8 en documentación y encabezado de la consola, manteniendo las rutas; el formulario Wasi usa una columna dentro de la tarjeta estrecha de tablet y el botón de opciones ocupa una fila propia.

Pruebas nuevas de esta revisión, en procesos separados y con bases sintéticas en `.tmp/pytest-v08-release-*`:

| Suite | Resultado nuevo |
| --- | --- |
| Consola, con Chromium | 292 aprobadas en 183,82 s |
| Catálogo | 228 aprobadas en 8,92 s |
| Scraper, con Wasi simulado en Chromium | 112 aprobadas en 64,84 s |
| Total | **632 aprobadas** |

Después de ajustar únicamente el encabezado de versión y la distribución del formulario en tablet se repitieron `consola/tests/test_wasi.py` y `consola/tests/test_v06.py`: **39 aprobadas en 52,68 s**, con Chromium y bases sintéticas en `.tmp/pytest-v08-final-ui`. No se suman como casos distintos al total anterior. Se inspeccionaron las capturas finales de escritorio y tablet; móvil y móvil sin JavaScript también pasaron de nuevo.

El primer intento dentro del sandbox quedó detenido y se interrumpió: no se cuenta como aprobado. La ejecución completa anterior terminó fuera del sandbox con los mismos contratos de datos sintéticos. Persiste únicamente la advertencia conocida de deprecación de `BlockingPortal` en Starlette/AnyIO. Se verificaron además `compileall`, `wasi_run.py --help`, `job.py --schedule` y `git diff --check`. No se ejecutaron extracciones reales ni se modificaron bases reales durante esta revisión.

La inspección visual usa capturas nuevas de las pruebas sintéticas a 1440, 768 y 390 px, incluidas comprobaciones de foco, labels, dependencias, errores, vacíos, cuatro secciones y ausencia de desbordamiento de página. Las capturas permanecen en `.tmp/` y no forman parte del commit.

Se seleccionaron explícitamente 57 archivos de código, pruebas, documentación y preparación de contenedor. La revisión de rutas y contenido no encontró credenciales, tokens, sesiones, claves privadas, bases, logs, capturas ni temporales en esa selección. `docs/wasi/diagnostico-red-2026-11-08.md` permanece sin seguimiento y fuera del commit; no se borró ni modificó.

La consulta de solo lectura `git ls-remote origin refs/heads/v0.6` devolvió `9db935ae398c93203cfaa3f7ebf7817d1904d17a`, igual a la base local y a `origin/v0.6`. La consulta inicial falló por la red del sandbox y se repitió correctamente fuera de él. No se hizo merge, rebase, push, tag ni cambio en otras ramas. El commit local autorizado deja un commit por delante de esa referencia consultada; su hash se informa al terminar, sin incorporarlo dentro de su propio contenido.

Docker no está disponible: no se construyó la imagen. Siguen pendientes despliegue, configuración real de Secret Manager/ADC/IAM, validación de snapshots y recuperación en Google Cloud, primera ejecución Cloud Run y otra posterior sin intervención, y medición de costos. Estas limitaciones de preparación se conservan explícitas; no se declara operación desatendida validada.
