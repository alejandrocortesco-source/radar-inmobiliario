# Filtros rápidos de actualización — entrega v0.5

Implementación del 3 de noviembre de 2026 sobre el checkout `v0.4` existente.
No había una implementación ni ruta v0.5 en este checkout: se conserva `/v0.4/`
como acceso principal y `/consola/` como interfaz anterior. No se renombraron
rutas, ramas ni etiquetas como parte de esta mejora.

## Uso

Bajo el título **Categorías de actualización**, encima de los controles de búsqueda
y filtros generales, aparecen **Todos**, **Nuevos**, **Cambio de precio** y
**Revisión conservadora**, cada uno con su contador real. Los contadores
respetan los filtros generales ya aplicados (texto, ciudad, precio, fuente,
búsqueda, etc.), independientemente de la categoría seleccionada y la página.
Cambiar de categoría vuelve a la primera página; conserva orden y tamaño.
La categoría viaja en `categoria=todos|nuevos|cambio_precio|revision_conservadora`
y se conserva en formularios, paginación, exportación CSV y regreso de la ficha.
La API existente `/api/catalog` también acepta ese parámetro.

En `/v0.4/`, JavaScript consulta la misma página y reemplaza únicamente la
sección del catálogo. Actualiza URL, contadores y selección, anuncia el resultado
y permite volver/avanzar en el navegador. Cancela consultas anteriores ante
selecciones rápidas. Si falla la consulta parcial, sigue el enlace GET normal.
Sin JavaScript (y en `/consola/`) los enlaces GET mantienen la funcionalidad.
Los ceros siguen siendo seleccionables y muestran un estado vacío explicativo.
No hay actualización automática en segundo plano: la siguiente consulta al
servidor incorpora las nuevas ejecuciones, igual que los demás filtros actuales.

## Semántica y separación de responsabilidades

- **Persistencia** (`catalogo/persistencia/sqlite.py`): lee la última ejecución
  `runs.status = completed` por cada `run_searches.search_url`, usando el ID
  creciente de ejecución. Una ejecución en curso, incompleta, fallida,
  interrumpida o bloqueada no reemplaza la evidencia exitosa. Una ejecución
  completada vacía sí reinicia las categorías de esa búsqueda. El catálogo y
  las categorías se leen en una misma transacción SQLite de solo lectura.
- **Traducción de evidencia**: `jobs.classification = new` aporta Nuevos;
  `modified` aporta Cambio de precio; `review` aporta Revisión conservadora.
  Un registro en `price_changes` de esa misma ejecución también aporta Cambio
  de precio, incluso cuando la clasificación es `review`. Se usa la pertenencia
  registrada en `listing_observations`, sin inferir condiciones nuevas. La bandera
  general `needs_refresh`/`requiere_revision` continúa siendo un filtro distinto;
  no sustituye la clasificación conservadora de una ejecución.
- **Modelo y consultas** (`catalogo/modelos.py`, `filtros.py`, `consultas.py`):
  cada presencia en una búsqueda lleva categorías comunes independientes del
  portal. `seleccionar` y `contar_categorias` funcionan con cualquier repositorio,
  usan el UUID existente y no conocen HTTP, SQL, HTML ni JavaScript. Sin búsqueda
  seleccionada se unen las categorías de las últimas ejecuciones por búsqueda;
  con búsqueda seleccionada solo se consideran las de esa búsqueda. Cada inmueble
  cuenta una vez por categoría, aunque figure en varias búsquedas. Las categorías
  pueden superponerse y sus contadores no tienen que sumar Todos.
- **Servicio/API y consola**: `ServicioCatalogo` mantiene su contrato y usa las
  consultas comunes; `catalogo/api.py` valida el nuevo parámetro. `consola/rutas.py`
  entrega conteos, etiquetas y enlaces a la plantilla compartida `_categorias.html`.
  El frontend solo presenta esos datos y navega: no clasifica inmuebles.

Se mantienen SQLite, las tablas y el historial existentes. No se modifican las
reglas, capturas ni planificación del scraper. Catálogos antiguos sin tablas de
evidencia incremental tienen contadores de categoría en cero; no se infieren
clasificaciones. Una futura fuente o un repositorio de Google Sheets podrá
aportar las mismas categorías comunes, sin cambios en las reglas del UX.
Google Sheets no se implementa en esta entrega. No se agregan dependencias.

## Validación

`consola/tests/test_categorias.py` cubre conteos, filtros generales, paginación,
exportación, API, UUID y fuentes distintas, categorías superpuestas, última
actualización exitosa por búsqueda, ejecuciones fallidas y vacías, conservación
del historial y lectura sin escrituras. Chromium verifica escritorio, móvil,
sin JavaScript, selección sin recarga, controles después del reemplazo y Atrás.

Resultados: **502 pruebas aprobadas** (182 Consola, 230 catálogo, 90 scraper),
más la repetición focalizada final de las 6 pruebas de categorías. `git diff --check`
sin errores. El entorno mantiene la advertencia conocida de deprecación de
`anyio.abc.BlockingPortal` en Starlette.

Consulta real de solo lectura al entregar: **439 Todos, 12 Nuevos, 5 Cambio de
precio, 0 Revisión conservadora**. Estos valores son evidencia de validación;
ninguno está fijo en el código de producción.

Comandos desde la raíz (usar directorios temporales dedicados):

```powershell
.\.venv\Scripts\python.exe -m pytest -c consola/pytest.ini consola/tests --basetemp=.tmp/pruebas-categorias-consola-completa -q
.\.venv\Scripts\python.exe -m pytest -c catalogo/pytest.ini catalogo/tests --basetemp=.tmp/pruebas-categorias-catalogo-02 -q
.\.venv\Scripts\python.exe -m pytest -c scraper/pytest.ini scraper/tests --basetemp=.tmp/pruebas-categorias-scraper -q
```

Corrección de visibilidad: la barra se sitúa antes de los filtros generales y el
panel móvil se despliega debajo de su control, evitando tapar las categorías.
