# Scraper de Metrocuadrado — Radar Inmobiliario

Componente de [Radar Inmobiliario](../README.md) para descubrir anuncios, mantener un catálogo incremental por cambios de precio y revisar los resultados con FastAPI. Recorre todos los listados y abre las fichas nuevas, con precio modificado o que requieren revisión de integridad. Puede ejecutarse por consola sin iniciar la interfaz. No necesita Apify, Sheets, Gemini ni WhatsApp. No envía formularios ni contacta anunciantes.

## Instalación (Windows / PowerShell)

Requiere Python 3.12 o superior. Desde la raíz del repositorio, entrar primero al componente. Para una instalación nueva, el entorno se crea dentro de `scraper/`:

```powershell
cd scraper
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m playwright install chromium
```

En Linux/macOS: entrar igualmente a `scraper/`, ejecutar `python3 -m venv .venv`, usar `.venv/bin/python` e instalar Chromium con `python -m playwright install --with-deps chromium`. Los ejemplos siguientes se ejecutan desde `scraper/`; no es necesario activar el entorno.

Para reproducir también las dependencias transitivas verificadas en esta entrega, instalar `-r requirements.lock.txt` en lugar de `requirements.txt`.

En el equipo donde se desarrolló la primera versión se conserva el entorno existente en `../.venv/`, con sus dependencias y Chromium instalados. No se trasladó ese entorno porque sus ejecutables pueden guardar rutas absolutas. El lanzador de la interfaz busca primero `scraper/.venv/` y, si no existe, utiliza ese entorno de la raíz.

## Ejecutar

```powershell
# Búsqueda completa: URL de La Carolina incorporada como valor predeterminado.
.\.venv\Scripts\python.exe -m metro scrape

# Chromium visible
.\.venv\Scripts\python.exe -m metro scrape --headed

# Reanudar una ejecución; sustituir 1 por el ID que imprime la consola
.\.venv\Scripts\python.exe -m metro scrape --resume 1

# Consultar integridad y contadores
.\.venv\Scripts\python.exe -m metro status 1

# Interfaz independiente del scraper
.\.venv\Scripts\python.exe -m metro serve
```

La actualización incremental se activa por defecto. Se pueden repetir opciones `--url` para recorrer varias búsquedas. Los importes sin código monetario se comparan en COP por confirmación del usuario; `--listing-currency unknown` evita aplicar esa confirmación a otra búsqueda cuya moneda no se conozca. Consulta las [reglas de precios, conservación de datos y segunda confirmación de retirados](docs/INCREMENTAL.md).

También se puede ejecutar desde la raíz mediante `scraper/run.py`. Con el entorno existente de este equipo:

```powershell
.\.venv\Scripts\python.exe scraper\run.py scrape
.\.venv\Scripts\python.exe scraper\run.py status 1
.\.venv\Scripts\python.exe scraper\run.py serve
# Interfaz persistente; puede invocarse desde la raíz
.\scraper\start-interface.ps1
```

Con una instalación nueva dentro del componente, sustituir el intérprete por `.\scraper\.venv\Scripts\python.exe`. Los datos predeterminados siempre se guardan en `scraper/data/`, independientemente de la carpeta desde la que se invoque el punto de entrada. Una ruta personalizada en `--db` o `METRO_DB` se interpreta desde el directorio de trabajo si es relativa.

Abrir [la interfaz local](http://127.0.0.1:8000). La interfaz permite filtrar por búsqueda/ejecución, texto, tipo y estado, paginar, revisar fichas, valores originales, multimedia, procedencias, errores y exportar JSON con trazabilidad. No carga las fotografías automáticamente: muestra sus enlaces. Actualizar la página permite ver avances mientras corre el scraper en otra consola. `/docs` contiene la API de FastAPI. El servidor sólo escucha en localhost por defecto.

En Windows, desde `scraper/`, usar `.\start-interface.ps1` para dejar la interfaz ejecutándose en segundo plano. Este lanzador utiliza la carpeta del componente aunque se invoque desde otra ubicación, comprueba `/health` y escribe los registros en `scraper/data/interface.stdout.log` y `scraper/data/interface.stderr.log`. Puede invocarse de nuevo sin duplicar un servidor que ya responde. El comando `python -m metro serve` se ejecuta en primer plano y necesita mantener abierta su consola.

Opciones del scraper: `--url`, `--headed`, `--concurrency` (1–4, predeterminado 2), `--delay` (pausa mínima global entre inicios de navegación, predeterminada 1.5 s más variación), `--timeout` (milisegundos, 45000), `--retries` (2, es decir hasta 3 intentos). Para una prueba pequeña: `scrape --max-pages 2 --max-details 5`. Los límites de prueba **no** declaran una extracción completa. Cambiar la base con `python -m metro --db otra.sqlite scrape` o con `METRO_DB`.

Cada ejecución mide automáticamente duración en segundos/minutos, CPU y pico RAM observado de Python y todo el árbol de Playwright/Chromium. Imprime un resumen y añade una fila a `data/metrics/resource_usage.csv`, además de un CSV con las muestras temporales; la carpeta queda junto a la base utilizada. No modifica los documentos de resultados. Opciones: `--resource-interval 0.2` (segundos, predeterminado) y `--metrics-dir` para otra carpeta. Detalles, unidades, limitaciones y uso para dimensionar Cloud Run: [monitoreo de recursos](docs/RECURSOS.md).

Código de salida 0: todos los listados terminados y todos los trabajos correctos o conservados sin cambios de precio. Código 2: incompleto, bloqueado o fallido, incluyendo fichas parciales o precios contradictorios pendientes. `Ctrl+C` conserva los checkpoints. Un bloqueo, CAPTCHA visible o HTTP 401/403/429 detiene nuevas solicitudes y conserva el avance; no hay evasión, sesiones persistentes, proxies ni resolución automática de desafíos. Sólo ejecuciones completas y exitosas cuentan ausencias; se requieren dos para confirmar retirados de una búsqueda.

## Fuentes y selectores inspeccionados

Inspección real del 24 de octubre de 2026, mediante Chromium, en la [búsqueda solicitada](https://www.metrocuadrado.com/inmuebles/venta/bogota/la-carolina?search=form). La herramienta de navegación web no pudo abrirla; Playwright con acceso a red sí pudo. Se revisaron apartamentos, una oficina (`3220-M4843647`) y un consultorio (`3312-M7166280`), con distintas listas de características.

* **Listado inicial:** JSON que la propia página entrega en `self.__next_f.push(...)` (React Flight). Se lee con el decodificador JSON, sin ejecutar el script. `initialResults.results` contiene los resultados principales; `initialResults.highlights`, los destacados de esa búsqueda. `recommended` se excluye explícitamente. `totalHits` y `totalEntries` se registran como totales del portal, sin fijarlos en código.
* **Páginas siguientes:** respuestas JSON de `/rest-search/search`, capturadas pasivamente cuando el navegador pulsa el paginador. No se fabrica un endpoint alternativo ni se copian cabeceras/credenciales. La petición la hace la propia página.
* **DOM del listado:** `.property-list__results a[href*="/inmueble/"]` confirma que los enlaces renderizados corresponden al JSON; las tarjetas son virtualizadas. Se desplaza el documento para activar su carga. No se cuentan solamente las tarjetas visibles, ni se recolectan indiscriminadamente enlaces del pie o recomendaciones.
* **Paginador:** `.rc-pagination-item-active` y `.rc-pagination-next`, con `aria-disabled` para el último paso. Cada avance exige cambio de página activa **y** del conjunto de identificadores de la respuesta. Se espera una condición de datos/DOM, no `networkidle`. Una huella repetida o ausencia de un cambio confirmado termina con error e incompleto. Los números y totales son dinámicos.
* **Fichas:** objeto público Flight con `propertyId` coincidente y `businessType`, incluyendo campos `detail`, `images`, `featured`, `coordinates`, anunciante y contacto público. También se conservan JSON-LD y texto renderizado; etiquetas visibles de área/moneda complementan los campos normalizados. Fotos, videos y recorridos se guardan como URLs de los datos/DOM, sin construir rutas de fotos a partir de sus IDs. Los recursos de imagen, fuentes y multimedia se bloquean durante el scraping para evitar sus descargas.

Las inspecciones locales están en `data/inspection/`. Las muestras usadas por las pruebas están en `tests/fixtures/`. Los selectores dependen del portal y pueden cambiar: si dejan de coincidir, la ejecución falla de forma explícita y no inventa resultados.

## Datos y trazabilidad

`data/metro.sqlite` utiliza WAL para lectura desde la interfaz durante la extracción. Tablas:

| Tabla | Contenido |
|---|---|
| `runs` | URL, configuración inicial, fechas UTC, totales anunciados, fin del listado y estado |
| `pages` | Página activa, URL, huella, enlaces con objetos originales públicos, siguiente paso y fecha |
| `properties` | Identidad global, URL canónica y último documento normalizado |
| `appearances` | Relación anuncio/ejecución/página; conserva búsquedas y páginas de aparición |
| `jobs` | Estado, intentos, error y documento propio de cada ejecución |
| `events` | Navegaciones, cambios confirmados, errores, reanudaciones y restricciones |
| `run_searches` | Avance y confirmación de ausencias independiente por URL |
| `listing_observations` | Precios de listado y conflictos de cada anuncio/búsqueda |
| `search_memberships` | Estado y última verificación por búsqueda; contador de ausencias |
| `price_changes` | Precio anterior/nuevo, fecha de detección y verificación de la ficha |

Cada página se confirma junto a sus apariciones y cola en una transacción. Identidad: ID del portal que debe coincidir con la URL; se eliminan parámetros de seguimiento de la URL canónica. Los destacados repetidos se deduplican conservando su procedencia. La huella usa sólo resultados principales, para no confundir el destacado constante con una página repetida.

Los documentos tienen `normalized`, `fields` (estado `present`, `absent` o `error`, valor original y fuente), `features`, `photos`, `media`, `extra`, `sources`, `visible_text`, `errors` y `quality`. `extra` conserva todos los atributos públicos previstos y no previstos. Se preservan descripciones completas, características agrupadas y unidades publicadas. No se asigna cero a desconocidos, ni se infieren coordenadas, dirección, moneda, antigüedad o fechas. Los ceros entregados por el portal permanecen como valores originales. Dirección de la inmobiliaria y dirección del inmueble son campos distintos. Las coordenadas no se presentan como exactas: el indicador público de aproximación queda en `extra`.

Los campos `normalized.map_url` y `normalized.portal_map_url` permiten abrir la ubicación en OpenStreetMap y la sección original `#location-section` de la ficha. La inspección del mapa Leaflet confirmó que usa `coordinates.lat/lon` y que el botón de nueva búsqueda sólo abre `/mapa`, sin seleccionar el inmueble. Por eso los enlaces se construyen a partir de las coordenadas públicas y se marcan con `derived: true`, su fuente, valores originales y el indicador `ubicacionaproximada` en `fields`. No representan una dirección verificada ni mayor precisión que la publicada. Sin coordenadas válidas no se genera un enlace. La interfaz ofrece un botón «Ver ubicación en mapa» y la API/exportación incluyen ambos campos.

Para añadir estos campos a resultados ya guardados sin volver a visitar las fichas, desde la raíz con el entorno existente: `.\.venv\Scripts\python.exe scraper\tools\backfill_location.py`. El script actualiza únicamente los documentos JSON y conserva las fechas, estados y datos originales de extracción. Puede repetirse sin duplicar información; admite `--db` para otra base.

No se guardan cookies, cabeceras, almacenamiento del navegador, tokens, claves ni datos de sesión. La conservación de originales se limita a los objetos públicos utilizados, con filtrado de claves sensibles. Nunca se guarda el HTML completo del navegador. `data/scraper.log` y la tabla de eventos registran los incidentes.

## Recuperación y límites

Al reanudar no se repiten las fichas correctas ni las conservadas sin cambios; las fallidas y parciales se reintentan dentro del límite persistente. Para permitir más intentos tras un fallo persistente se puede aumentar `--retries` (hasta 5). Si se terminó el descubrimiento, se va directamente a las fichas pendientes. Si se interrumpió un listado, se recorre el paginador hasta el checkpoint, verificando IDs y precios; las páginas guardadas no se vuelven a insertar. Esto es necesario porque el paginador observado mantiene la misma URL para distintas páginas. Si cambió el listado desde el checkpoint, se registra el cambio y hay que iniciar una nueva ejecución para garantizar que no se pierdan anuncios.

SQLite dispone de instantáneas por ejecución; la tabla global muestra la información más reciente. Un bloqueo de archivo del SO impide que dos scrapers escriban simultáneamente en la misma base. La interfaz sí puede leerla a la vez. Un apagado abrupto puede dejar el estado de la ejecución como `running`: se reanuda mediante su ID y los checkpoints transaccionales.

La extracción conserva lo que el portal publica normalmente sin autenticación. No promete datos que el anunciante no publicó, ni información detrás de un muro de acceso. Un error en paginación permite procesar las fichas ya descubiertas, pero mantiene el listado incompleto. El total anunciado y los únicos pueden diferir por destacados o duplicados: ambos se muestran por separado.

## Pruebas

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Desde la raíz, con el entorno existente: `.\.venv\Scripts\python.exe -m pytest -c scraper/pytest.ini -q`. La configuración de pytest está dentro del componente y resuelve sus importaciones sin depender de la carpeta desde la que se invoque. Las herramientas `tools/` también resuelven sus archivos de entrada y salida respecto de `scraper/`.

Pruebas de muestras públicas de tres tipos, referencias Flight y descripciones multilínea, recomendaciones excluidas, deduplicación, valores ausentes/fallidos/cero, filtrado de sesión, persistencia transaccional, reintentos, API y escape HTML. La navegación real, el paginador y la recuperación también se probaron contra el sitio; ver [el informe de validación](docs/VALIDACION.md) para resultados finales y límites.

## Organización y Cloud Run Jobs

`metro/extraction.py`: adaptador y normalización; `metro/scraper.py`: Playwright y recorrido; `metro/storage.py`: SQLite; `metro/web.py` y `metro/templates/`: consulta; `metro/__main__.py`: consola; `metro/paths.py`: rutas del componente; `run.py`: punto de entrada desde la raíz; `pytest.ini`: importaciones y descubrimiento de pruebas. La documentación adicional está en `docs/`; la configuración de contenedor es específica de este componente.

Incluye `Dockerfile` preparado para un proceso Job, con Chromium y dependencias del navegador en una imagen Playwright que coincide con la versión instalada. No se necesita iniciar FastAPI en el Job. Ejemplo local, con Docker instalado:

```powershell
docker build -t metro-local .
docker run --rm -v "${PWD}/data:/data" metro-local scrape
```

Estos comandos se ejecutan dentro de `scraper/`. Si se construye desde la raíz, usar `docker build -f scraper/Dockerfile -t metro-local scraper`: el contexto es el componente y utiliza su `.dockerignore`.

El filesystem de Cloud Run es efímero: esta primera versión necesita planificar un volumen compatible con los bloqueos de SQLite o copiar la base cerrada a almacenamiento durable entre ejecuciones. No usar SQLite WAL directamente sobre un montaje de objetos/FUSE sin verificar sus garantías. Una alternativa posterior es un adaptador de base durable. Ejecutar una sola tarea por base; dimensionar timeout y memoria para Chromium. No se desplegó ni se configuró infraestructura de Google Cloud en esta entrega.
