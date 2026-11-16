# Selector de búsquedas de Programación — corrección local

16 de noviembre de 2026. Clon Radar-CloudRun-20261111/repo, rama
codex/ejecuciones-manuales, HEAD 7283bc4. Versión registrada verificada en
scraper/metro/__init__.py: 0.13.1. Se preservó el trabajo local anterior de
programación múltiple, sin cambiar rama, hacer commit, push ni despliegue.

## Causa

La URL 127.0.0.1:8770 sirve la demostración aislada, cuyo fixture inicial solo
registraba Carolina y Norte de Metrocuadrado. No consultaba el bucket operativo.
El formulario obtenía opciones dinámicas de la proyección de búsquedas, pero
usaba groupby y omitía los portales sin filas, dando apariencia de soporte de una
sola fuente. La selección ya usaba checkboxes y parejas fuente/ID.

La fuente de verdad sigue siendo BusquedasSQLite.listar(): consola_busquedas con
clave compuesta (fuente,id_busqueda), estado en radar_busquedas_estado y
configuraciones específicas de Wasi/Fincaraíz en la misma base auxiliar. El
servicio proyecta ese registro desde el snapshot durable hacia control.searches;
el formulario no inventa búsquedas ni utiliza anuncios como opciones.

## Corrección

- Tres grupos estables, con nombres legibles y mensaje Sin búsquedas configuradas.
- Checkboxes individuales, Seleccionar todas (solo elegibles), Limpiar selección y contador accesible. Ningún radiobutton.
- La selección vacía es válida como borrador; guardar o activar requiere al menos una búsqueda activa. El error queda junto al selector, también con frecuencia semanal.
- Una búsqueda inactiva no seleccionada se deshabilita. Una selección histórica inactiva/eliminada se mantiene visible y marcada para retirarla explícitamente; no se descarta silenciosamente al editar otro campo. Guardar o activar la rechaza mientras siga no disponible.
- Valores serializados por fuente/ID, sin colisiones entre portales. Se verifica almacenamiento/recuperación y procesamiento exclusivo de las seleccionadas mediante trabajador simulado.
- La demo incorpora tres portales desde fixtures sintéticos separados. No se añaden búsquedas de ejemplo al selector de producto ni a datos reales.

Durante una captura se conserva la proyección disponible para no competir por el
snapshot; guardar/activar y el trabajador revalidan contra el registro autoritativo.
No se cambia la arquitectura de reservas, bloqueo, recibos, Scheduler ni ejecución.

## Archivos de esta corrección

- consola/ejecuciones.py: preparación de grupos y selecciones históricas.
- consola/templates/v06/programaciones06.html: selector únicamente.
- consola/static/programaciones.js: selección global, limpieza y contador.
- consola/static/ejecuciones.css: estilos acotados al selector.
- ejecuciones/calendarios.py: validación de vacíos y revalidación al activar.
- consola/tests/selector_fixtures.py y test_selector_programaciones.py: datos y pruebas nuevas.
- consola/tools/revisar_programaciones.py: carga de los fixtures en el snapshot sintético respetando generaciones.
- Este informe. Copias previas de los seis archivos existentes en .tmp/selector-20261116/antes/.

## Validación nueva

| Suite | Aprobadas | Tiempo XML | Evidencia |
| --- | ---: | ---: | --- |
| Programación, selector y ejecuciones | 176 | 69.687 s | entrega-consola.xml |
| Catálogo completo | 249 | 19.913 s | final-catalogo.xml |
| Scraper completo | 183 | 283.993 s | final-scraper.xml |

Logs y XML en .tmp/selector-20261116/. No sumar las repeticiones de pruebas. La
primera preparación del nuevo fixture intentó guardar sin restaurar su generación
actual y produjo PreconditionFailed; se corrigió usando cargar/guardar del adaptador
y se repitieron las pruebas. Los resultados finales no tienen fallos ni errores.
Única advertencia: deprecación conocida de BlockingPortal en Starlette/AnyIO.

Chromium comprobó 1440×900, 768×1024 y 390×844, grupos, múltiples búsquedas por
portal, selección combinada/global/vacía, contador, guardado y recuperación al
editar. Capturas selector-1440.png, selector-768.png y selector-390.png. Se inspeccionó
visualmente la captura móvil. También se cubren portales vacíos, IDs compartidos,
inactivas/eliminadas, bloqueo del guardado/activación y persistencia del resultado
simulado de las tres fuentes. Compileall y git diff --check correctos.

## Revisión local y límites

La demo se reinició y sirve el selector actualizado en:
http://127.0.0.1:8770/v0.6/ejecuciones/programaciones?nuevo=1

Recargar con Ctrl+F5. Si se detiene, desde el clon:

```powershell
.\.venv\Scripts\python.exe consola/tools/revisar_programaciones.py --port 8770
```

La demostración crea datos sintéticos nuevos en cada arranque y bloquea la red
externa. No muestra ni importa búsquedas de producción. En el entorno operativo,
las opciones proceden de sus búsquedas configuradas mediante el adaptador existente.
La corrección no está desplegada en Google Cloud. Sin cambios de datos productivos,
Jobs reales, Scheduler, scrapers, matching, credenciales ni infraestructura.
