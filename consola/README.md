# Consola v0.2 — Radar Inmobiliario

Interfaz minimalista de consulta en `/consola/`, dentro del FastAPI existente.
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

## Uso

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

- `rutas.py`: páginas Jinja2 y exportación CSV de solo lectura.
- `presentacion.py`: formatos, enlaces públicos, mapa, historial y navegación.
- `templates/`: catálogo, filtros, enlaces, ficha y estados.
- `static/`: CSS adaptable y JavaScript sin librerías ni recursos remotos.
- `tests/`: HTTP, navegación, SQLite sin escrituras y Chromium.

Se conservan FastAPI, `ServicioCatalogo`, `FiltrosCatalogo`, las consultas comunes
y `CatalogoSQLite`, que abre SQLite con `mode=ro` y `query_only`.
El catálogo hace una sola lectura por solicitud para obtener filtros y resultados.
La exportación usa esa misma selección y transmite el CSV por filas.
No hay SQL en la Consola, solicitudes HTTP internas, caché persistente ni
un segundo servidor. Los formularios GET, paneles, enlaces y paginación funcionan
sin JavaScript; la restauración de posición y cambio automático de tamaño lo usan.

El filtrado sigue siendo en memoria y requiere leer el catálogo completo.
La exportación conserva la selección en memoria, aunque no construye un CSV
completo antes de transmitirlo. Si el scraper cambia datos entre solicitudes,
los resultados pueden variar. Los enlaces externos pueden caducar.

No se implementan Google Sheets, Gemini, matching ni cambios al scraper o al
esquema de SQLite.

## Pruebas

Desde la raíz, con carpetas temporales dedicadas que pytest puede recrear:

```powershell
.\.venv\Scripts\python.exe -m pytest -c consola/pytest.ini consola/tests --basetemp=.pytest_cache/consola-v02
.\.venv\Scripts\python.exe -m pytest -c catalogo/pytest.ini catalogo/tests --basetemp=.pytest_cache/catalogo-v02
.\.venv\Scripts\python.exe -m pytest -c scraper/pytest.ini scraper/tests --basetemp=.pytest_cache/scraper-v02
```

Las pruebas usan datos sintéticos y SQLite temporal. Chromium arranca un servicio
local de prueba y lo cierra al terminar. No ejecutan scraping ni usan la base real.
Las pruebas v0.1 de tarjetas/galería se adaptaron al comportamiento aprobado de
v0.2, conservando la cobertura de filtros, errores, seguridad, navegación y lectura.
