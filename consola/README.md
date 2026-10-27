# Consola v0.3 — Radar Inmobiliario

Interfaz de consulta, captura manual y matching en `/consola/`, dentro del FastAPI existente.
La versión v0.1 se conserva en el commit `fb49534` y la etiqueta `consola-v0.1`.
La interfaz técnica sigue en `/`; la API, reportes y exportaciones anteriores conservan sus rutas.

## Abrir en Windows

Desde PowerShell, en este equipo:

```powershell
Set-Location -LiteralPath 'C:\Users\Palex25\Documents\Boch-Lab\Radar Inmobiliario'
& '.\.venv\Scripts\python.exe' '.\scraper\run.py' serve
```

Mantener la terminal abierta y visitar [la Consola](http://127.0.0.1:8000/consola/).
Para detenerla, pulsar Ctrl+C en esa terminal. Si el servidor ya estaba abierto
antes de cambiar el código, detenerlo y volver a ejecutar el comando. Recargar
el navegador con Ctrl+F5 para actualizar CSS y JavaScript.

Si se inició en segundo plano con `scraper/start-interface.ps1`, comprobar el PID
antes de detenerlo:

```powershell
$radarPid = [int](Get-Content -LiteralPath '.\scraper\data\interface.pid')
Get-CimInstance Win32_Process -Filter "ProcessId = $radarPid" |
    Select-Object ProcessId, ExecutablePath, CommandLine
```

Solo si corresponde al servicio de Radar de este proyecto, detener ese proceso
con `Stop-Process -Id $radarPid` y ejecutar el comando de inicio anterior.
El lanzador no reinicia un servidor que ya está activo.

No se requieren nuevas dependencias. La base predeterminada continúa siendo
`scraper/data/metro.sqlite`. Para consultar otra base existente, sin copiarla:

```powershell
& '.\.venv\Scripts\python.exe' '.\scraper\run.py' --db 'C:\ruta\catalogo.sqlite' serve
```

## Captura y matching v0.3

La corrección de v0.3 organiza el trabajo en tres áreas numeradas: **Cliente y
oportunidad**, **Resumen del matching** y **Resultados**. «Guardar y buscar
coincidencias» guarda y lleva directamente al resumen y la tabla en la misma
página. «Guardar oportunidad / Guardar cambios» y la consulta independiente de
coincidencias siguen disponibles. La navegación superior permite saltar al
catálogo completo, con todos sus filtros y fichas.

Los indicadores muestran el catálogo global, los compatibles con requisitos
confirmados y los candidatos pendientes de verificar, como grupos separados.
Antes de ejecutar una oportunidad se muestra «—», sin simular resultados.
El diagnóstico expandible cuenta cuántos anuncios se descartan y cuántos quedan
después de cada requisito. Un caso sin resultados explica los criterios que
lo limitaron. El [informe de corrección](docs/CORRECCION_V03.md) documenta la
causa raíz, el caso real y la validación.

1. Arriba del catálogo, escribe el nombre del cliente y opcionalmente su teléfono.
   Si ya existe, selecciónalo en «Usar un cliente existente» y pulsa «Preparar
   nueva oportunidad». Esto permite conservar varias oportunidades por cliente.
2. Elige compra/arriendo, tipo y presupuesto máximo COP. Ciudad es un selector
   real alimentado por el catálogo; con una única ciudad aparece fija y
   seleccionada automáticamente. No se usa `datalist` ni historial del navegador.
   Abre «Seleccionar barrios o zonas», escribe parte del nombre y marca varias
   opciones. La búsqueda ignora tildes, mayúsculas y espacios adicionales.
   Cada selección aparece como etiqueta con una × para retirarla. «Listo» cierra
   la selección; marcar opciones no la cierra. Al cambiar de ciudad se conservan
   solo ubicaciones que también existen allí y se informa cuáles se retiraron.
   Las opciones provienen exclusivamente del catálogo. Las ubicaciones guardadas
   que ya no figuran se conservan como etiquetas históricas, sin ofrecerlas como
   opciones nuevas. La captura manual adicional anterior sigue disponible.
   Sin JavaScript se utiliza la selección nativa múltiple y «Actualizar barrios»
   después de cambiar de ciudad, conservando el borrador sin guardarlo.
3. Ingresa habitaciones mínimas o área mínima (o ambas). Es obligatorio al menos
   uno. Usa números sin separadores de miles; decimales con punto. Presupuesto y
   áreas deben ser positivos; habitaciones, baños, parqueaderos y antigüedad
   admiten cero y requieren enteros. El mínimo de área no puede superar el máximo.
   Los errores se muestran en el formulario conservando lo diligenciado.
4. «Características adicionales y preferencias» incluye baños, parqueaderos,
   área máxima, antigüedad, tipo de área, estado y observaciones. Por defecto,
   cada criterio diligenciado es indispensable. Marca como preferencia aquellos
   que deban ordenar sin excluir. Una preferencia marcada requiere un valor.
   Ciudad, ubicación, tipo, operación y presupuesto siempre son indispensables.
5. Pulsa «Guardar y buscar coincidencias». Se consulta el
   catálogo global completo, independientemente de la URL o filtros del scraper
   y de los filtros activos de la tabla.
6. La tabla compacta muestra coincidencia, ubicación, tipo, precio, área,
   habitaciones, baños, parqueaderos, fuente y publicación. Pulsa el estado de
   una fila para desplegar requisitos y preferencias cumplidas, pendientes o no
   cumplidas. La ubicación abre la ficha y conserva orden y página al regresar.
   Cada encabezado alterna orden ascendente/descendente sobre todos los resultados;
   datos desconocidos siempre al final. Se muestran 24 filas por defecto, con
   12/24/48 y navegación por páginas. El resumen cuenta todo el catálogo evaluado,
   independientemente de la página. «Modificar oportunidad» permite buscar de nuevo.
7. «Clientes y oportunidades» permite consultar registros guardados, editar
   clientes y oportunidades, crear otra oportunidad para un cliente o marcarla
   cerrada desde la sección adicional. Editar nombre/teléfono actualiza el cliente
   compartido por todas sus oportunidades. No se elimina ningún registro.

El orden por coincidencia coloca primero los requisitos confirmados por datos,
luego menos requisitos pendientes y más preferencias cumplidas. Los empates usan
el identificador. También se permite ordenar por precio COP, con precios
desconocidos al final. No hay porcentajes ni puntuaciones de IA.

Un incumplimiento indispensable conocido excluye el anuncio. Un requisito sin
datos deja el resultado **pendiente de verificar**, nunca confirmado. Compra
se compara con las ofertas de venta; en ofertas duales se usa solo la operación
solicitada. No se convierten divisas ni se presume COP si la moneda falta.
La ciudad se compara junto con cualquiera de los barrios o zonas indicados
(alternativas, no condiciones acumulativas); se normalizan tildes, mayúsculas
y espacios. En ciudades se normaliza puntuación y se reconocen explícitamente
Bogotá, Bogotá D.C. y Bogotá, D.C. como la misma ciudad. No se usan coincidencias
parciales, geocodificación ni equivalencias entre barrios de nombres parecidos.

Las áreas se comparan solo con el tipo elegido (construida por defecto), sin
sustituir áreas privadas/publicadas. La superficie mostrada conserva la
prioridad visual de v0.2 y las explicaciones identifican el tipo comparado.
La antigüedad no existe como dato estructurado en el modelo del catálogo: al
exigirla queda pendiente; al preferirla se indica sin datos y no excluye.
Las observaciones se guardan sin interpretación automática. Confirmación de
requisitos significa cumplimiento según los datos, no verificación comercial:
siempre se debe confirmar disponibilidad actual con la fuente. Se muestra su
presencia en búsquedas y si el anuncio requiere revisión.

Clientes y oportunidades se guardan en `scraper/data/metro-consola.sqlite` por
defecto, separado de `metro.sqlite`. Se crea al guardar por primera vez; abrir
el catálogo no crea bases ni escribe. Con `--db`, la base de la Consola se ubica
junto al catálogo con sufijo `-consola.sqlite`. Para fijar otro archivo:

```powershell
$env:RADAR_CRM_DB = 'C:\ruta\consola.sqlite'
.\.venv\Scripts\python.exe .\scraper\run.py serve
```

La ruta debe ser distinta del catálogo. Las migraciones aditivas versionadas
se ejecutan dentro de la transacción de escritura, conservan registros y no
modifican tablas del scraper. Para respaldar los datos, detén el servicio y
copia ambos SQLite. No hay Google Sheets, WhatsApp, webhooks, Gemini, otros
LLM, servicios externos ni envíos automáticos. La API y los contratos de
captura están documentados en [oportunidades](../oportunidades/README.md).

## Catálogo (funciones conservadas)

- Encabezado sencillo, contador, herramientas y una fila con Zona, Precio y Tipo.
- Tabla de seis columnas: Zona, Tipo, Precio, Área, Habitaciones y Links.
  Zona presenta el barrio, o la zona/ciudad si no hay barrio; abre la ficha.
- 24 inmuebles inicialmente; selector de 12, 24 o 48 por página.
- Un precio por fila en formato local `$1.250.000`, con operación. La presentación
  usa la convención COP sin convertir importes ni modificar la moneda guardada.
  Sin filtro de operación se prioriza
  venta entre las ofertas compatibles; al filtrar arriendo se muestra arriendo.
  La ficha y la exportación conservan todas las ofertas correspondientes.
- Buscar despliega texto sobre título, descripción o ID original.
- Filtros despliega ciudad, barrio, tipo de área, rangos, características,
  disponibilidad, fuente, búsqueda de origen y revisión pendiente.
- Precio despliega operación, moneda y rango. Comparar u ordenar precios
  requiere operación y moneda; no se convierten divisas ni se infieren monedas.
- Ordenar permite precio, área, extracción, presencia en búsquedas e ID.
  Los encabezados Precio y Área también permiten alternar el orden.
- Exportar descarga CSV UTF-8, compatible con Excel, con todos los resultados
  de los filtros **ya aplicados** y el mismo orden, sin limitarse a la página.
  Una fila por oferta, con operación y moneda separadas. Antes de exportar,
  aplicar cualquier cambio pendiente en el formulario.
- Los iconos de enlace externo, imagen y ubicación abren la publicación,
  los enlaces individuales a fotos y el mapa directo de OpenStreetMap.
  Se utiliza el `map_url` almacenado si su marcador y centro corresponden a las
  coordenadas válidas del anuncio. `portal_map_url` solo apunta a una sección de
  la publicación y no garantiza que se cargue su mapa; no se usa como sustituto.
  Si faltan coordenadas o un enlace directo válido, el acceso queda deshabilitado.
  Las ubicaciones aproximadas identifican el punto como centro de una zona
  aproximada, nunca como dirección exacta. La precisión desconocida se indica.
  Los destinos externos abren otra pestaña. No se cargan imágenes automáticamente.
- La ficha muestra descripción, ofertas y características principales;
  datos adicionales y trazabilidad se consultan en secciones desplegables.
  El historial indica precios anterior, observado y de ficha,
  operación y estado de verificación, con importes en el mismo formato local.
  No se inventa un precio inicial ni una fecha.
- Volver al catálogo conserva filtros, orden, tamaño y página en la URL.
  JavaScript restaura además la posición vertical y horizontal mediante
  sessionStorage. Si no está disponible, la consulta y el regreso siguen funcionando.
- En tablet, los controles se redistribuyen y solo la tabla se desplaza
  horizontalmente si no cabe. No se ocultan columnas ni se crean tarjetas.

Por convención del mercado local, los números de área positivos y finitos se
presentan en m² aunque la captura no incluya unidad, sin modificar SQLite.
La tabla y la ficha priorizan construida, luego privada y luego publicada;
identifican el tipo como (construida), (privada) o (no especifica). Si no existe
ningún valor válido muestran «No especifica». La exportación conserva el mismo
valor prioritario y su tipo real. Los filtros y el orden de área comparan
únicamente el tipo seleccionado, sin sustituirlo por otras superficies; se indica
en la leyenda y en la ayuda de cada celda. Ceros, negativos, booleanos y valores
no finitos no se usan como áreas.
Las fechas se muestran en hora de Colombia (UTC−5); extracción, presencia y
actualización de la fuente se identifican por separado. La ausencia en búsquedas
no confirma venta ni disponibilidad comercial.

## Arquitectura y rendimiento

- `rutas.py`: páginas del catálogo y exportación CSV de solo lectura.
- `oportunidades.py`: adaptador de formularios y resultados; reutiliza los
  modelos, servicio, repositorio y motor de `oportunidades/`.
- `presentacion.py`: formatos, enlaces públicos, mapa, historial y navegación.
- `ubicaciones.py`: opciones reales por ciudad y conservación de históricos.
- `resultados.py`: orden y presentación de páginas, reutilizando `paginar` del
  catálogo, formatos y ficha. La tabla comparte estilos e iconos de publicación.
- `templates/`: catálogo, filtros, enlaces, ficha y estados.
- `static/`: CSS adaptable y JavaScript sin librerías ni recursos remotos.
- `tests/`: HTTP, navegación, persistencia, matching y Chromium.

Se conservan FastAPI, `ServicioCatalogo`, `FiltrosCatalogo`, las consultas comunes
y `CatalogoSQLite`, que abre SQLite con `mode=ro` y `query_only`.
El catálogo hace una sola lectura por solicitud para obtener filtros y resultados.
La exportación usa esa misma selección y transmite el CSV por filas.
No hay SQL en los adaptadores de la Consola, solicitudes HTTP internas, caché persistente ni
un segundo servidor. Los formularios GET, paneles, enlaces y paginación funcionan
sin JavaScript; la restauración de posición y cambio automático de tamaño lo usan.

El filtrado sigue siendo en memoria y requiere leer el catálogo completo.
La exportación conserva la selección en memoria, aunque no construye un CSV
completo antes de transmitirlo. Si el scraper cambia datos entre solicitudes,
los resultados pueden variar. Los enlaces externos pueden caducar.

La captura vive en un almacenamiento independiente. No se modificaron el
scraper ni su esquema. El matching se evalúa en memoria y su tabla tiene
paginación; la lista de clientes/oportunidades aún no está paginada. No hay historial de ediciones
ni control de edición concurrente: la última escritura prevalece. Esta versión
mantiene el alcance local de la aplicación existente.

## Pruebas

Desde la raíz, con carpetas temporales dedicadas que pytest puede recrear:

```powershell
.\.venv\Scripts\python.exe -m pytest -c consola/pytest.ini consola/tests --basetemp=.pytest_cache/consola-v03
.\.venv\Scripts\python.exe -m pytest -c catalogo/pytest.ini catalogo/tests --basetemp=.pytest_cache/catalogo-v03
.\.venv\Scripts\python.exe -m pytest -c scraper/pytest.ini scraper/tests --basetemp=.pytest_cache/scraper-v03
```

Las pruebas usan datos sintéticos y SQLite temporal. Chromium arranca un servicio
local de prueba y lo cierra al terminar. No ejecutan scraping ni usan la base real.
Las pruebas v0.1 de tarjetas/galería se adaptaron al comportamiento aprobado de
v0.2, conservando la cobertura de filtros, errores, seguridad, navegación y lectura.
Las pruebas v0.3 añaden el ciclo completo con y sin JavaScript, escritorio y móvil,
la regla habitaciones/área, criterios indispensables/preferencias, desconocidos,
edición, relaciones cliente/oportunidades, rollback atómico, reinicio del
repositorio, migraciones aditivas y huellas de la base del catálogo sin cambios.

Validación de entrega (26 de octubre de 2026): **418 pruebas aprobadas**:
118 de Consola (incluido Chromium), 210 de catálogo y 90 de scraper.
Se verificó también `git diff --check` y se revisaron capturas de escritorio y
móvil. El entorno reporta una advertencia de deprecación de
`anyio.abc.BlockingPortal` en Starlette; no afecta el resultado de las pruebas.

Validación posterior de la corrección v0.3: **432 pruebas aprobadas** (132 de
Consola, 210 de catálogo y 90 de scraper). Incluye la acción principal en
escritorio, móvil y sin JavaScript, diagnóstico acumulativo, regresión de ciudad
y explicación de búsquedas sin resultados. La comprobación adicional con los
427 inmuebles reales se reproduce sin escribir en las bases existentes:

```powershell
.\.venv\Scripts\python.exe consola/tools/validar_matching_real.py
```

La herramienta genera un CRM nuevo y `evidencia.json` en un directorio UUID
dentro de `.tmp/`, y verifica las huellas del catálogo y del CRM existentes.

Correcciones de usabilidad posteriores: **455 pruebas aprobadas** (155 Consola,
210 catálogo y 90 scraper). Incluyen ciudad única/múltiple, búsqueda y etiquetas,
eliminación de selecciones al cambiar ciudad, persistencia normalizada, orden
por las diez columnas, nulos al final y paginación con regreso desde la ficha.
Consulta el [informe de usabilidad](docs/USABILIDAD_V03.md).

Normalización geográfica posterior: consulta el
[diagnóstico, reglas, inventario y validación real](docs/GEOGRAFIA_V03.md).
El selector y el matching usan barrios controlados; los textos originales y
los casos ambiguos quedan disponibles en la ficha. El catálogo del scraper se
mantiene de solo lectura y la proyección se persiste en `metro-geografia.sqlite`.
