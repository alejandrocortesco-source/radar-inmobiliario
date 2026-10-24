# Consola v0.1 — Radar Inmobiliario

Interfaz de consulta para Mónica, disponible en `/consola/` dentro del mismo
FastAPI que ya sirve el scraper. La interfaz técnica permanece en `/`;
la API, reportes y exportaciones conservan sus rutas.

## Iniciar en Windows

Desde PowerShell, con el entorno existente de este equipo:

```powershell
Set-Location -LiteralPath 'C:\Users\Palex25\Documents\Boch-Lab\Radar Inmobiliario'
& '.\.venv\Scripts\python.exe' '.\scraper\run.py' serve
```

Mantener esa terminal abierta y visitar
[la Consola](http://127.0.0.1:8000/consola/).
Para detener el servicio, pulsar Ctrl+C en su terminal. Si ya estaba iniciado,
reiniciarlo para que cargue las rutas nuevas; no abrir una segunda instancia.

En una instalación cuyo entorno esté dentro de `scraper/`, usar
`& '.\scraper\.venv\Scripts\python.exe' '.\scraper\run.py' serve`.
No se necesitan dependencias adicionales a las del scraper.

La base predeterminada sigue siendo `scraper/data/metro.sqlite`. Para consultar
otra base existente, sin copiarla:

```powershell
& '.\.venv\Scripts\python.exe' '.\scraper\run.py' --db 'C:\ruta\catalogo.sqlite' serve
```

El lanzador persistente existente `.\scraper\start-interface.ps1` también inicia
este mismo servicio. Si ya detecta uno activo no lo reinicia automáticamente.

## Uso

- Catálogo con tarjetas y una entrada por identidad del anuncio.
- Texto, ciudad, barrio, zona, tipo, operación, moneda, precios, áreas,
  habitaciones, baños, parqueaderos y disponibilidad.
- Orden por precio, área, extracción de ficha, presencia en búsquedas o ID
  (el ID se utiliza para ordenar, no se muestra como dato).
- Páginas de 12, 24 o 48 resultados. Los enlaces a las fichas conservan
  filtros, orden y desplazamiento para volver al mismo listado.
- Fichas con galería, ofertas separadas de venta y arriendo, áreas y
  características, descripción, procedencia y búsquedas asociadas.
- Fotografías con carga diferida y alternativa cuando no existen o fallan.
- Estados vacíos, filtros inválidos y base no disponible con mensajes HTML.

Para comparar precios, seleccionar operación y moneda. No se convierte ninguna
divisa ni se infiere una moneda desconocida. Por defecto se comparan áreas
construidas y se ordena por última extracción. Una unidad no confirmada queda
sin dato; los ceros conocidos de habitaciones o parqueaderos se conservan.

Las fechas de extracción y presencia se muestran por separado, en hora de
Colombia (UTC−5). Una presencia reciente no implica que hayan cambiado las fotos
o características. La ausencia en una búsqueda nunca se presenta como venta.

La galería y el plegado móvil usan JavaScript sencillo. Sin JavaScript siguen
funcionando el formulario GET, la paginación y los enlaces de fichas; la galería
interactiva requiere JavaScript.

## Organización y reutilización

- `rutas.py`: router Jinja2 y composición de las páginas.
- `presentacion.py`: formato, estado de navegación y parámetros del formulario.
- `templates/`: base, catálogo, filtros, ficha y estados.
- `static/`: CSS adaptable y JavaScript.
- `tests/`: pruebas HTTP, navegación y pruebas reales en Chromium.

Las páginas llaman a `ServicioCatalogo.listar/consultar/obtener`.
Los filtros se validan contra el mismo `FiltrosCatalogo` que la API,
utilizando Pydantic ya incluido en FastAPI. Se usan los nombres reales de la API,
incluyendo `limit` y `offset`; no hay SQL, consultas HTTP internas ni otro servidor
de aplicación. El único cambio del scraper es montar el router y los estáticos
en `metro.web.app`.

## Pruebas

Desde la raíz:

```powershell
.\.venv\Scripts\python.exe -m pytest -c consola/pytest.ini consola/tests
.\.venv\Scripts\python.exe -m pytest -c catalogo/pytest.ini catalogo/tests
.\.venv\Scripts\python.exe -m pytest -c scraper/pytest.ini scraper/tests
```

Las pruebas de navegador utilizan Playwright y Chromium existentes, un proceso
temporal del mismo FastAPI y datos sintéticos. El proceso termina al cerrar cada
prueba. No se hace scraping ni se utiliza la base real en la suite automatizada.
La comprobación visual manual con la base real solo realiza lecturas.

## Limitaciones

El catálogo se filtra en memoria. La lista de ubicaciones también se obtiene
desde el servicio, sin caché. Si el scraper actualiza datos entre solicitudes,
las páginas pueden variar.

Las fotos dependen de las URLs públicas de la fuente y pueden caducar.
La interfaz no inventa atributos ni identifica propiedades físicas repetidas
entre anuncios diferentes. La ficha técnica conserva el historial de precios;
esta interfaz inicial presenta las ofertas actuales del catálogo.

No se incluyen autenticación de producción, Google Sheets, oportunidades,
Gemini, matching ni despliegue. La imagen Docker actual es de extracción;
una futura imagen web deberá incluir `catalogo/` y `consola/`.
