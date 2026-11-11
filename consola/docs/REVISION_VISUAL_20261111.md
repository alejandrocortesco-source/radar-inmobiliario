# Revisión visual de Radar — 11 de noviembre de 2026

Referencia: **`/v0.6/`**, la entrada vigente indicada en `consola/README.md` y el documento rector. `/` es el explorador técnico conservado por compatibilidad. No se ha incrementado la versión, hecho commit, push ni despliegue.

La revisión conserva las cuatro secciones del inicio, su distribución adaptable, textos, navegación y reglas. No modifica consultas, matching, scraper, persistencia ni integración con proveedores. El catálogo conserva su densidad de tabla; los paneles siguen siendo paneles y las fichas independientes siguen siendo páginas.

## Identidad tomada del inicio

Fondo crema `#f3f0e9`, superficie `#fdfcf8`, texto `#302e28`, secundario `#6a665b`, borde `#d5d0c5`, marrón `#71503c` / hover `#503626` y oliva `#4f5a3d`. Arial/Helvetica, base 14 px / 1,5; títulos principales de 32 px (28 en móvil), secciones de 22 px (20 en móvil), peso normal. Ancho máximo 1536 px y márgenes adaptables de 40/24/16 px. Campos con fondo cálido y borde inferior; botones rectos de al menos 40 px. Las tablas mantienen sus contenedores de desplazamiento y los estados mantienen significado propio.

## Inventario de pantallas

Las 28 vistas de esta tabla se recorrieron **después de los cambios** en Chrome, a 1440 × 1000, 820 × 1180 y 390 × 844. Las rutas con identificadores usan exclusivamente fixtures sintéticos. Las variantes que comparten plantilla se agrupan en la tabla, sin excluir su revisión.

| Pantalla / ruta | Estados revisados y ajuste |
| --- | --- |
| Inicio `/v0.6/` | Referencia conservada; cuatro secciones, navegación, tablas y fuentes. Valores trasladados al tema compartido. |
| Clientes `/v0.6/clientes` | Lista activa; misma identidad del inicio, teclado y tabla. |
| Inactivos `/v0.6/clientes?vista=inactivos` | Estado vacío, switcher activo/inactivo. |
| Nuevo `/v0.6/nuevo` | Campos, validación nativa, foco en campo inválido, barrios, preferencias desplegables y guardado. |
| Editar necesidades `/v0.6/nuevo?oportunidad=…` | Valores guardados, formulario y cancelación. |
| Cliente `/v0.6/clientes/{id}` | Edición desplegable, necesidades, resultados, decisiones, orden y éxito al guardar. Nombre largo sin desbordamiento. |
| Cliente sin resultados, misma ruta | Estado vacío de candidatos, contadores y acciones. |
| Identificación `/v0.6/identificacion` | Antes y después de análisis determinista sintético; evidencia, comparación ancha, confirmación y vistas de revisión. Se añade `aria-current` al enlace principal. |
| Catálogo `/v0.4/` | Se sustituye la paleta fría y verde por la del inicio; Arial, anchos, encabezados, controles, tablas y enlaces coherentes. |
| Categoría vacía `/v0.4/?categoria=cambio_precio` | Mensaje vacío, categoría activa y regreso. También búsqueda sin resultados al combinar texto y ciudad. |
| Ficha `/v0.4/inmuebles/{id}` | Página y panel lateral; títulos, comentario largo, guardado, descripción, datos de fuente, historial vacío y procedencia desplegable. |
| Matching `/v0.4/oportunidades/{id}/coincidencias` | Resumen, tabla, confirmados/pendientes, orden, diagnóstico y comentarios. Se conservan los colores de estado con tonos compartidos. |
| Nueva oportunidad `/v0.4/?panel=nueva` | Modal, campos, foco, pie de acciones y confirmación del borrador; sin redondeos ni superficies ajenas. |
| Gestión `/v0.4/?panel=clientes` | Modal de clientes y oportunidades; títulos, formularios y navegación. |
| Matching vacío `/v0.4/?contexto=matching` | Mensaje de selección y acciones iniciales. |
| Editar cliente `/v0.4/clientes/{id}` | Editor independiente/modal, campos y botones. |
| Consola histórica `/consola/` | Captura, resumen sin ejecutar, resultados, gestión y catálogo integrado; colores, Arial, superficies, tipografía y controles. |
| Ficha histórica `/consola/inmuebles/{id}` | Página, metadatos, enlaces y desplegables con la identidad común. |
| Cliente histórico `/consola/clientes/{id}` | Formulario y mensajes con estilos compartidos. |
| Matching histórico `/consola/oportunidades/{id}/coincidencias` | Resumen, tabla, diagnóstico y estados con paleta común. |
| Anunciante `/consola/anunciante?inmueble=…` | Página y panel desde catálogo/ficha/matching; ausencia de contacto, otros inmuebles, paginación, carga, fallo, reintento y retorno del foco con Escape. |
| Explorador técnico `/` | Inventario, ejecución, filtros y tabla. Se elimina el estilo verde independiente, conservando todos los textos y rutas. |
| Catálogo técnico `/catalog` | Disponibilidad y tabla ancha dentro de su región. |
| Detalle técnico `/properties/004?run_id=1` | Ficha válida, tablas con URLs largas, datos normalizados, características, multimedia y procedencia. |
| Error de cliente `/v0.6/clientes/no-existe` | Error HTML, contraste y regreso al inicio. |
| Error de ficha `/v0.4/inmuebles/no-existe` | Estado inexistente con los mismos títulos, superficie y enlaces. |
| Edición Wasi `/v0.6/?editar_wasi=…` | Selectores dependientes y numerosos campos; misma composición del inicio, sin consultar opciones externas. |
| Edición Fincaraíz `/v0.6/?editar_fincaraiz=…` | URL filtrada y modo de criterios verificados; selectores, texto de ayuda y acciones. Sin verificar contra el portal. |

Las API, CSV, JSON, OpenAPI y sus visores de documentación no son pantallas de negocio; conservan sus contratos y respuestas. No se modificó el middleware de acceso ni se recorrió un login externo.

## Componentes y mantenimiento

- `consola/static/tema.css`: única paleta compartida, tipografía base, medidas comunes, foco, estados, sombras y encabezado reutilizable. Se carga directamente antes de las hojas de cada familia, sin importaciones CSS encadenadas.
- `consola/static/compatibilidad.css`: adaptación acotada de las distribuciones históricas, controles, modales y tablas; no afecta al dashboard actual.
- `consola/static/tecnica.css`: extrae el CSS inline del explorador técnico y utiliza el mismo tema.
- Las hojas existentes dejan de declarar paletas independientes. Anunciantes usa variables del tema y conserva su implementación y comportamiento.
- Las plantillas base conservan sus enlaces y contenido. Se identifica la sección activa de revisión y los paneles de gestión existentes.

## Comprobaciones y evidencia

Solo bases sintéticas en `.tmp/revision-visual/` y bases `tmp_path` de pytest. El servidor de revisión bloquea conexiones externas y subprocesos; no se ejecutaron scrapers, Google Cloud ni tareas del proveedor. Los estados de evaluación se sembraron mediante el repositorio auxiliar **sin ejecutar la tarea retornada**: cero solicitudes, incluidos cero llamados al transporte simulado.

Chrome: 84 recorridos finales (28 vistas × tres tamaños), sin desbordamiento horizontal de página. Se verificaron búsqueda por texto, combinación de filtros con estado vacío, paginación, guardar comentario, creación de cliente y oportunidad, selector de barrios con teclado, Escape y retorno de foco, panel sobre ficha y conservación/descarte de borradores. Se inspeccionaron estados sintéticos de evaluación en curso, correcta y fallida; el botón se deshabilita durante el procesamiento. El fallo y la carga de anunciantes se forzaron únicamente en el servidor fixture; Reintentar recupera el contenido.

Contraste calculado sobre la paleta aplicada: texto/fondo 11,93:1; texto secundario/fondo 5,04:1; enlace/superficie 7,02:1; blanco/botón 7,20:1; advertencia 5,75:1; éxito 8,93:1; error 6,60:1. Son comprobaciones de combinaciones principales, no una certificación completa de accesibilidad.

Evidencia local: [auditoría de rutas, tamaños y contraste](../../.tmp/revision-visual/auditoria-navegador.json). Las capturas incluyen el aviso amarillo del entorno sintético; ese aviso no pertenece a la aplicación operativa.

| Diferencia | Antes | Después |
| --- | --- | --- |
| Catálogo | [Captura](../../.tmp/revision-visual/capturas/catalogo-antes.jpg) | [Captura](../../.tmp/revision-visual/capturas/catalogo-despues.jpg) |
| Anunciante | [Captura](../../.tmp/revision-visual/capturas/anunciante-antes.jpg) | [Captura](../../.tmp/revision-visual/capturas/anunciante-despues.jpg) |
| Modal de oportunidad | [Captura](../../.tmp/revision-visual/capturas/formulario-antes.jpg) | [Captura](../../.tmp/revision-visual/capturas/nueva04-desktop.jpg) |
| Consola histórica | [Captura](../../.tmp/revision-visual/capturas/historica-antes.jpg) | [Captura](../../.tmp/revision-visual/capturas/historica-desktop.jpg) |
| Explorador técnico | [Captura](../../.tmp/revision-visual/capturas/tecnica-antes.jpg) | [Captura](../../.tmp/revision-visual/capturas/tecnica-desktop.jpg) |

Las capturas principales usan el mismo viewport de 1440 × 1000. El fixture recibió después comentarios y un cliente largo para comprobar contenido variable. Se conservan capturas adicionales por pantalla y tamaño en la misma carpeta.

## Pruebas

**757 pruebas aprobadas**: 389 de consola, 247 de catálogo y 121 de scraper. La ejecución final de consola incluye las tres regresiones técnicas nuevas. `git diff --check` terminó correctamente; Git informa únicamente la normalización futura LF/CRLF del archivo de pruebas editado. Pytest informa una deprecación existente de `anyio.abc.BlockingPortal` en Starlette.

| Suite | Resultado | Log local |
| --- | --- | --- |
| Consola, incluido Chromium | 389 aprobadas, 231,51 s | [Entrega](../../.tmp/revision-visual/pruebas-consola-entrega.txt) |
| Catálogo | 247 aprobadas, 9,47 s | [Log](../../.tmp/revision-visual/pruebas-catalogo.txt) |
| Scraper | 121 aprobadas, 49,47 s | [Log](../../.tmp/revision-visual/pruebas-scraper.txt) |
| Flujo v0.4 y regresiones técnicas, antes de la suite final | 8 aprobadas, 19,42 s; incluidas en las 389 | [Log](../../.tmp/revision-visual/pruebas-ui-final.txt) |

Comandos ejecutados desde la raíz:

```powershell
& .\.venv\Scripts\python.exe -m pytest -c consola/pytest.ini consola/tests --basetemp=.tmp/revision-visual/pytest-consola-entrega -q
& .\.venv\Scripts\python.exe -m pytest -c catalogo/pytest.ini catalogo/tests --basetemp=.tmp/revision-visual/pytest-catalogo -q
& .\.venv\Scripts\python.exe -m pytest -c scraper/pytest.ini scraper/tests --basetemp=.tmp/revision-visual/pytest-scraper -q
git diff --check
```

Los logs anteriores conservan los fallos de sincronización hallados durante la revisión: primera consola, 385 aprobadas y un fallo; segunda, 387 aprobadas y dos fallos. Tras esperar la carga completa, la última pasó sus 389 pruebas. No se presentan las pasadas anteriores como aprobadas ni se repiten resultados de commits históricos.

Se añadió una regresión de tres tamaños para las tablas técnicas y las URLs largas. La prueba de navegación v0.4 ahora espera `load` antes de medir la página y editar el modal: las primeras pasadas podían observar CSS o inicialización incompletos tras navegar. No se cambiaron manejadores de la aplicación para hacer pasar las pruebas.

## Límites y hallazgos ajenos a presentación

- Revisión en Chrome/Chromium de escritorio con viewports de tablet y móvil; no se probó Safari en un iPad físico ni un lector de pantalla.
- El explorador técnico mantiene un fallo previo al abrir un ID original compartido entre fuentes: `/properties/001` devuelve ambigüedad en JSON. La ficha válida `004` se verificó en los tres tamaños. No se alteró la resolución de identidades.
- La fixture de regresión con mapa publicado y sin el metadato `fields.map_url.raw` expone un error previo de la plantilla técnica. La prueba visual usa una ficha sin mapa. Este caso de datos incompletos queda pendiente; no se modificó la plantilla de detalle ni se ocultó como éxito.
- Los estados de proveedor son escenarios sintéticos de presentación; esta revisión no acredita servicio real, consumo, validación de portales ni despliegue.

## Instancia y Git

Instancia local: **http://127.0.0.1:8768/v0.6/**, abierta en Chrome. Datos de revisión separados de los operativos. Para iniciar de nuevo sin los fallos visuales temporales del fixture, desde la raíz:

```powershell
& .\.venv\Scripts\python.exe consola/tools/revision_local.py --datos .tmp/revision-visual --port 8768
```

El lanzador y esos datos se probaron durante esta sesión; la instancia actualmente activa añade únicamente un middleware de fixtures y `Cache-Control: no-store`, desde `.tmp/revision-visual/servidor_estados.py`. El archivo de fallo de anunciante queda vacío y no quedan evaluaciones en curso.

Rama `develop`, HEAD `fe29bb0`. Índice sin cambios preparados; ningún commit nuevo, push, tag ni cambio de versión. Sin conflictos de merge.

Archivos de esta tarea:

- `consola/static/{tema,compatibilidad,tecnica,consola,v06,anunciantes}.css`
- `consola/static/v04/v04.css`
- `consola/templates/base.html`, `consola/templates/v04/base.html`, `consola/templates/v06/base06.html`
- `scraper/metro/templates/base.html`
- `consola/tests/test_presentacion_tecnica.py`, `consola/tests/test_v04_browser.py`
- Este informe.

Cambios anteriores conservados: `docs/README.md` modificado; `consola/docs/VALIDACION_PRECLOUD_20261111.md`, `consola/tests/test_revision_local.py` y `consola/tools/revision_local.py` sin seguimiento. No se editó su contenido. Bases, logs, scripts auxiliares y capturas de esta revisión permanecen en `.tmp/`, fuera de Git.
