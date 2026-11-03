# Fecha del catálogo y búsquedas de origen

Entrega del 3 de noviembre de 2026, en las rutas existentes `/v0.4/` y `/consola/`.

## Lo que verá Mónica

Junto a las categorías aparece **Última actualización del catálogo**, con fecha y
hora de Colombia. Se toma la finalización más reciente de una ejecución
`completed`, sin depender de filtros, página, ni extracción individual de fichas.
Una ejecución fallida/en curso no cambia esa fecha. Si no hay una finalización
exitosa registrada, se muestra el estado vacío correspondiente. La fecha indica
la última ejecución exitosa que actualizó el catálogo, no que todas las búsquedas
se hayan ejecutado simultáneamente. Las lecturas de fecha y catálogo son consultas
consecutivas; si una ejecución termina entre ellas, la siguiente consulta vuelve
a sincronizar la vista. No hay sondeo automático en segundo plano.

La tabla añade **Búsqueda de origen**, junto a Zona. Muestra el nombre elegido y
la fuente, con un enlace a la URL. Un inmueble que pertenece a varias búsquedas
muestra todas; no se duplica su fila. La ficha y el CSV también incluyen los nombres.
Estos nombres describen la intención de búsqueda, no el barrio verificado de la
publicación. El barrio y la zona siguen usando las reglas geográficas existentes.

**Nombrar búsquedas de origen**, junto a la fecha, permite editar los nombres y
registrar otra URL con nombre, por ejemplo **Zona Country Club**. La búsqueda real
actual se registra como **En la Carolina** por indicación del usuario; ese nombre
es un dato persistido, nunca un valor fijo en las plantillas.

Registrar una URL **no ejecuta el scraper**. Para capturar sus inmuebles hay que
usar el comando/mecanismo de actualización actual con esa URL. Cuando el adaptador
entregue la misma fuente e identidad de búsqueda, se mostrará el nombre registrado.
La integración de otro portal y la ejecución de scraping desde la consola quedan
fuera de esta entrega.

## Responsabilidades y almacenamiento

- `CatalogoSQLite.ultima_actualizacion()` lee `runs.finished` únicamente de
  ejecuciones completadas. Ignora fechas ausentes, inválidas o sin zona horaria;
  no presume una fecha basándose en una extracción o en la hora del archivo.
- `BusquedasSQLite` conserva solo metadatos en `consola_busquedas`, una tabla
  auxiliar en la base de la Consola (`metro-consola.sqlite` por defecto).
  Se crea al guardar por primera vez. Leer no crea archivos ni migra bases.
  La tabla es necesaria porque antes no había almacenamiento de nombres.
  No toca tablas del scraper, clientes, oportunidades, geografía ni comentarios.
- `ServicioCatalogo` valida los nombres/URLs y añade los nombres a
  `PresenciaBusqueda.nombre`, reutilizando el campo común existente. Se identifica
  cada nombre por `(fuente, id_busqueda)`. En Metrocuadrado se reutiliza
  `search_identity`; parámetros de seguimiento no crean otra búsqueda. En futuras
  fuentes se conserva la URL como identidad al registrarla; cualquier normalización
  específica deberá integrarse con el adaptador de esa fuente.
- El servicio recibe el repositorio de nombres por inyección. El filtrado sigue
  usando los identificadores originales; renombrar no cambia pertenencias,
  clasificaciones, disponibilidad ni historial. La misma URL en dos fuentes admite
  nombres separados. El almacenamiento podría sustituirse por Google Sheets sin
  que las plantillas conozcan SQL. No se implementa Sheets ahora.
- `consola/rutas.py` adapta el formulario GET/POST existente (sin dependencias
  nuevas), y las plantillas compartidas presentan la fecha y la procedencia.
  La exportación añade al final la columna **Búsquedas de origen**, conservando
  las columnas anteriores y la protección contra fórmulas.

Si no se ha guardado un nombre, se conserva el nombre legible derivado de la URL
que ya utilizaba la ficha. El formulario permite reemplazarlo por uno explícito.
Los respaldos de la base auxiliar de la Consola incluyen los nuevos nombres.

## Validación

`consola/tests/test_origen_busquedas.py`: fecha global en Colombia, ejecuciones
fallidas y nuevas completadas, filtros y páginas, guardar/renombrar y persistir,
varias búsquedas por inmueble, fuentes independientes, URL normalizada, ficha,
CSV, entradas inválidas, lectura sin creación de archivos y catálogo sin escrituras.
Chromium cubre editar y registrar desde escritorio, móvil y sin JavaScript.
Las pruebas existentes de áreas se actualizan para localizar su celda por clase,
sin depender de un índice de columna que cambia con esta nueva funcionalidad.

Resultado final: **513 pruebas aprobadas** (193 Consola, 230 catálogo, 90 scraper).
Se verificaron capturas de escritorio/móvil y `git diff --check`. Se conserva la
advertencia conocida de deprecación de `anyio.abc.BlockingPortal` en Starlette.
El servidor activo de `http://127.0.0.1:8000/v0.4/` se reinició y se verificaron
la fecha real y **En la Carolina**. El catálogo del scraper mantuvo su huella
antes/después de guardar el nombre en la base auxiliar.

Comandos desde la raíz:

```powershell
.\.venv\Scripts\python.exe -m pytest -c consola/pytest.ini consola/tests --basetemp=.tmp/pruebas-origen-entrega -q
.\.venv\Scripts\python.exe -m pytest -c catalogo/pytest.ini catalogo/tests --basetemp=.tmp/pruebas-origen-catalogo-final -q
.\.venv\Scripts\python.exe -m pytest -c scraper/pytest.ini scraper/tests --basetemp=.tmp/pruebas-origen-scraper -q
```
