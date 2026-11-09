# Wasi en Radar Inmobiliario — v0.8

Ampliación solicitada el 8 de noviembre de 2026, sobre `v0.6` / `9db935a` (anunciantes v0.7). No incluye push, merge ni despliegue. El catálogo real no se usa para pruebas.

## Contratos conservados

Un inmueble sigue siendo un anuncio. UUID5 conserva exactamente el contrato `[fuente,id_original]`; Wasi usa `wasi` y códigos de texto, incluidos ceros iniciales. El mismo código de Metrocuadrado produce otra identidad. No se buscan ni fusionan inmuebles físicos. Enlaces de fichas, comentarios, decisiones y matching utilizan UUID. La API también acepta `wasi:CODIGO` y `metrocuadrado:CODIGO`; un código simple compartido devuelve 422 y exige calificarlo.

`wasi.sqlite` reutiliza el esquema técnico y `Store` incremental de Metrocuadrado. No hay otro esquema de negocio. `CatalogoIntegrado` compone repositorios de solo lectura: las vistas, filtros, CSV, anunciantes, indicadores y matching reciben el mismo `Inmueble`. Los contratos `RepositorioCatalogo`, `RepositorioRevision` y los adaptadores de configuración permiten sustituir almacenamiento posteriormente; no se implementa Sheets. La interfaz técnica histórica del scraper en `/` continúa siendo la herramienta específica de Metrocuadrado; la consola de Mónica y `/api/catalog` son integradas.

Variables opcionales, rutas predeterminadas junto a `METRO_DB`:

| Variable | Uso |
| --- | --- |
| `METRO_DB` | Catálogo técnico Metrocuadrado, predeterminado `scraper/data/metro.sqlite` |
| `WASI_DB` | Catálogo técnico Wasi, predeterminado `wasi.sqlite` en el mismo directorio |
| `RADAR_CRM_DB` | Configuración auxiliar existente, predeterminado `<nombre-metro>-consola.sqlite` |

Las tres rutas deben ser distintas. La consola nunca escribe capturas. Puede iniciar con solo la base Wasi; si existe una base ilegible, no la omite silenciosamente.

## Configurar búsquedas sin capturar

En el inicio `/v0.6/`, «Agregar fuente» permite seleccionar Metrocuadrado (URL filtrada) o Wasi (controles). Permanecen exactamente cuatro secciones. Con JavaScript los controles geográficos dependen de los padres. Sin JavaScript, «Actualizar formulario» prepara las opciones tras elegir fuente o cambiar cada padre. Guardar y editar solo escriben la base auxiliar.

Wasi requiere ciudad y al menos localidad o zona/barrio. Los IDs y etiquetas corresponden a opciones observadas, no a barrios del catálogo ni equivalencias inventadas. Incluye un snapshot de opciones inspeccionadas el 8 de noviembre: departamentos colombianos, Bogotá, sus localidades y zonas de Usaquén, además de criterios compatibles. No es un directorio geográfico completo. Las opciones de otra ciudad o localidad deben sincronizarse con la cuenta del portal antes de configurarlas, mediante «Actualizar opciones de Wasi» en el formulario o el comando de opciones. Esa acción separada requiere acceso configurado y no guarda búsquedas ni capturas. El scraper vuelve a verificar opciones, valores, resumen activo y renovación del listado cada vez que aplica una búsqueda; un cambio del portal falla de forma conservadora.

Desde la raíz, después de configurar acceso:

```powershell
# Lee únicamente opciones de controles: no pulsa Buscar ni captura inmuebles.
.\.venv\Scripts\python.exe scraper/wasi_run.py options --parent id_pais=1 --parent id_dpto=15 --parent id_ciudad=794 --parent id_localidad=1

# Para explorar otro departamento: sincronizar primero sin incluir ciudad;
# revisar las opciones en el formulario y repetir con sus IDs reales.
.\.venv\Scripts\python.exe scraper/wasi_run.py options --parent id_pais=1 --parent id_dpto=2

# Alternativa a guardar desde el formulario: este JSON no contiene secretos.
.\.venv\Scripts\python.exe scraper/wasi_run.py register --name "Apartamentos en venta · Usaquén" --filters scraper/examples/wasi-usaquen.json
```

`--db` y `--crm` se colocan antes del subcomando. Las opciones sincronizadas se guardan en `radar_wasi_opciones` de la base auxiliar. Una localidad explícitamente vacía (`--parent id_localidad=`) permite consultar zonas de la ciudad cuando el portal las ofrece así. No hay búsqueda ni captura al sincronizar opciones.

La identidad de búsqueda es `wasi:SHA256(filtros canónicos)`, nunca la URL común. `radar_wasi_busquedas` conserva filtros con identidad estable; un guardado explícito puede actualizar sus etiquetas publicadas, y cada ejecución conserva su snapshot; `consola_busquedas` selecciona cuáles se ejecutarán. Editar filtros registra una nueva revisión y retira únicamente la selección anterior de futuras ejecuciones. Las procedencias y configuraciones anteriores siguen disponibles; las presencias históricas conservan su último estado y fecha, sin inventar ausencias de búsquedas que ya no se ejecutan; no se aplican ausencias de la nueva búsqueda a la anterior. Renombrar sin cambiar filtros conserva identidad. Las ejecuciones reanudadas usan la copia de configuración de su `run`, aunque se haya eliminado o editado el registro auxiliar.

## Credenciales locales

No compartir contraseñas por chat. El código no contiene credenciales ni las recibe por argumentos de CLI. No se cargan archivos `.env` automáticamente.

En una terminal PowerShell privada, suministrarlas al entorno del proceso:

```powershell
$env:WASI_USER = Read-Host 'Usuario de Wasi'
$radarClaveWasi = Read-Host 'Contraseña de Wasi' -AsSecureString
$env:WASI_PASSWORD = ([pscredential]::new('wasi', $radarClaveWasi)).GetNetworkCredential().Password
Remove-Variable radarClaveWasi
```

Los valores introducidos no aparecen en los comandos ni se guardan en el historial. Otra opción es `WASI_USER_FILE` y `WASI_PASSWORD_FILE`: rutas a archivos externos protegidos mediante los permisos del usuario, fuera del repositorio o dentro de `data/` ignorado por Git. No guardar valores en scripts, imágenes o archivos versionados. Si se usa un archivo externo, su protección y copia de seguridad corresponden al gestor de secretos del entorno local.

Cada ejecución crea un contexto aislado. Comprueba acceso efectivo a la red, reutiliza las cookies válidas de ese contexto y, si falta sesión, usa `#user`, `#password` y `#login` del formulario normal. Verifica de nuevo acceso a `#advanced_search`. Hace un solo envío de credenciales por ejecución. La sesión se reutiliza durante el trabajo y se destruye al cerrar Chromium; **no se persisten cookies, perfiles ni storage state**. Esto evita depender de una sesión manual o proteger otro secreto persistido.

Los errores de autenticación se registran con códigos fijos: `auth_configuration_missing`, `auth_rejected`, `auth_failed`, `auth_blocked`, `auth_session_expired`, `auth_interactive_verification` o `auth_unexpected_destination`. No se conservan excepciones detalladas, HTML, capturas de login, cabeceras o payloads con credenciales. Un rechazo/CAPTCHA/OTP/bloqueo detiene el trabajo y no aplica ausencias. No hay resolución de CAPTCHA ni evasión. Una sesión que caduca durante el recorrido bloquea esa ejecución; reanudar inicia sesión automáticamente y verifica los checkpoints.

## Primera captura y recuperación

```powershell
# Primero registrar una búsqueda desde la consola o mediante register.
.\.venv\Scripts\python.exe scraper/wasi_run.py scrape
.\.venv\Scripts\python.exe scraper/wasi_run.py status 1
.\.venv\Scripts\python.exe scraper/wasi_run.py scrape --resume 1

# Metrocuadrado conserva su entrada anterior.
.\.venv\Scripts\python.exe scraper/run.py scrape --fuentes-registradas

# Ambas fuentes registradas, sin iniciar FastAPI.
.\.venv\Scripts\python.exe scraper/job.py --source all

# Al terminar la terminal privada:
Remove-Item Env:WASI_PASSWORD -ErrorAction SilentlyContinue
Remove-Item Env:WASI_USER -ErrorAction SilentlyContinue
```

Wasi recorre todas las páginas. Verifica página activa, continuidad de intervalos, total estable, IDs únicos y final deshabilitado; exige cubrir exactamente el total anunciado. No admite máximos de páginas o detalles. Los errores no equivalen a cero resultados. Un cambio de IDs o precios desde el checkpoint exige iniciar otra ejecución, conservando lo anterior.

La primera pasada descubre y deduplica todas las búsquedas antes de planificar. Solo si hay detalles pendientes, una segunda pasada de los listados guardados abre esos modales y verifica que las páginas no cambiaron. Un anuncio presente en varias búsquedas tiene un solo trabajo global. La navegación de Wasi es secuencial, con pausa mínima y reintentos limitados, porque comparte contexto y modales; Metrocuadrado conserva su concurrencia existente. Esto evita nuevas pestañas/búsquedas por cada ficha. Se elige el mayor tamaño de página que el portal ofrezca, sin limitar el número de páginas. Se bloquean fuentes y multimedia; las imágenes se responden dentro del navegador con un SVG vacío local, sin descargar fotos. Abortar imágenes rompe Fotorama: elimina fotogramas. La galería se recorre mediante su control normal, esperando que la imagen activa cargada corresponda a su miniatura; solo se conservan URLs originales observadas. El SVG nunca se guarda en el catálogo.

El código del modal cambia antes que los demás campos. Se espera a que termine la petición normal de ficha y se confirma el título del listado, además del código. El panel de empresa espera su propia respuesta normal antes de leer contactos. Se observan las respuestas de la navegación, sin invocar endpoints directamente ni conservar sus cuerpos. Un contador tardío, un modal con datos anteriores o una galería sin inicializar no se interpretan como captura completa.

Se reutilizan documentos completos y fiables con el mismo precio; nuevo, cambio de precio, precio inválido, conflicto o ficha previa incompleta requieren detalle. Los importes son COP sin conversiones. No hay refresco por edad/fecha: cambios sin variación de precio pueden quedar sin detectar. Fallar o capturar parcialmente conserva la última ficha fiable y deja revisión pendiente. Las ausencias siguen requiriendo dos ejecuciones completas y exitosas, por búsqueda y fuente. Las bases separadas impiden que Wasi retire anuncios de Metrocuadrado.

Código de salida 0: completado. 2: incompleto, bloqueado, fallido o configuración inválida. Las transacciones de página y los intentos persisten. `status` muestra clasificaciones, páginas, únicos, reutilizados, fichas abiertas, errores y reintentos. `errors` cuenta trabajos actualmente fallidos/parciales/bloqueados y `error_events` conserva las incidencias históricas, incluso si un reintento termina bien. La medición de duración, CPU y RAM Python+Chromium se imprime y guarda en `metrics/wasi/`; son mediciones del proceso, no facturación de Google Cloud.

## Mapeo y calidad

Captura campos existentes: título, operación, tipo, ciudad, localidad como zona, zona/barrio publicado como barrio, precios de cada operación, áreas construida/privada, habitaciones, baños, parqueaderos, estrato, piso, año de construcción, administración, descripción, características, imágenes y contactos del anunciante. Área de terreno no se convierte en área publicada/construida/privada. Dirección del anunciante permanece separada de la del inmueble. Fechas, coordenadas y dirección desconocidas no se deducen de la búsqueda ni de la empresa. `None` no se transforma en cero.

El normalizador conserva `fields.present/absent/error` y calidad completa/parcial. La ficha muestra «Información no disponible en esta fuente» para ausencias conocidas y «Pendiente por error de captura» cuando falló el campo. Un precio ausente sigue exigiendo revisión conservadora. Las características sin columna específica se conservan en el documento técnico, sin añadir campos al modelo común.

Se inspeccionaron controles y DOM de listado, ficha y empresa, además del formulario público de login. Los selectores son específicos del portal y pueden cambiar; las pruebas sintéticas no demuestran que una cuenta real pueda iniciar sesión ni que todos los anuncios tengan igual estructura.

El nombre de empresa conserva igualdad literal. Se consultan los contactos publicados del panel de ese inmueble. El panel depende de empresa y anuncio: se deduplican consultas exactas dentro de la ejecución y sus reintentos, pero no se omite el panel de otro inmueble por compartir empresa, pues puede tener otro agente. Los contactos nunca se propagan por ese supuesto. Los enlaces de WhatsApp se reducen al destino publicado, eliminando el mensaje que contiene identidad de la cuenta conectada. La consola aplica las validaciones de enlaces existentes. No se contacta, solicita alianza ni publica.

La URL pública solo se conserva si fue publicada en la fila o en el enlace de WhatsApp del panel y termina en el código solicitado; no se construye a partir de un slug. Sin URL pública, el anuncio conserva código, fuente y búsquedas, pero la página general **no** aparece como «Publicación original». Los enlaces a búsquedas siguen identificados como tales.

## Cloud Run Jobs: preparación, sin despliegue

`Dockerfile.jobs` se construye desde la raíz e incluye scraper y módulos compartidos, sin servidor HTTP. El Dockerfile histórico de Metrocuadrado permanece disponible.

```powershell
docker build -f Dockerfile.jobs -t radar-jobs .
.\.venv\Scripts\python.exe -m pip install -r scraper/requirements-cloud.txt

# Solo imprime el horario: no crea tareas ni infraestructura.
$env:RADAR_DAYS = 'TUE,FRI'
.\.venv\Scripts\python.exe scraper/job.py --schedule
# {"schedule":"0 0 * * TUE,FRI","timeZone":"America/Bogota"}
```

Los dos días son configurables. `MON,THU` es únicamente el ejemplo predeterminado del generador de horario; no se activó ninguna programación. La futura tarea de Cloud Scheduler debe usar la expresión generada, `America/Bogota`, OAuth y la identidad invocadora del Job. Configurar **una tarea, paralelismo uno y sin reintentos automáticos de Job**; los reintentos de navegación ya están acotados. Ajustar timeout/memoria mediante medición real.

Credenciales: crear dos secretos privados en Secret Manager, dar `roles/secretmanager.secretAccessor` a la identidad del Job únicamente sobre ellos y exponerlos como `WASI_USER`/`WASI_PASSWORD` fijados a versiones concretas, o montarlos y configurar las variables `*_FILE`. No usar claves JSON de service account ni secretos en Docker build args. Ejemplo de flags **para la etapa autorizada de configuración futura**, no ejecutados en esta entrega: `--set-secrets=WASI_USER=wasi-user:1,WASI_PASSWORD=wasi-password:1`.

Persistencia: `EstadoGCS` utiliza ADC de la identidad del Job y un bucket privado. Las bases viven en disco local durante el trabajo; no se monta SQLite/WAL sobre almacenamiento de objetos. Un único objeto comprimido contiene backups consistentes de `metro.sqlite`, `wasi.sqlite`, `metro-consola.sqlite` y cachés geográficas opcionales. No contiene secretos ni sesión. El objeto se sustituye de forma atómica mediante precondición de generación. Un segundo objeto de lock, creado con generación cero, impide Jobs simultáneos. La identidad necesita permisos de objetos limitados al bucket/prefijo de estado; mantener acceso público deshabilitado y versionado/recuperación según la política elegida.

Variables: `RADAR_STATE_BUCKET`, `RADAR_STATE_OBJECT` (predeterminado `radar/state.tar.gz`) y `RADAR_DATA_DIR`. En Cloud Run, falta de bucket detiene el Job antes de capturar; no se acepta disco efímero como destino definitivo. El directorio local de restauración debe estar sin bases previas. El wrapper usa nombres de archivo estables, diferentes de las rutas personalizadas permitidas por la CLI local.

Inicializar en una etapa posterior desde una copia cerrada de las bases, con nombres estables y configuración auxiliar incluida:

```powershell
$env:RADAR_STATE_BUCKET = 'BUCKET_PRIVADO'
$env:RADAR_STATE_OBJECT = 'radar/state.tar.gz'
.\.venv\Scripts\python.exe scraper/job.py --data-dir .tmp/estado-preparado --initialize-state
```

Este comando solo crea un estado inexistente; no reemplaza uno existente. No se ha ejecutado aquí. El Job normal restaura, captura, guarda cada 60 segundos y al terminar, incluso al bloquearse. SIGTERM cancela conservando checkpoints; ante SIGKILL se conserva el último snapshot confirmado. Las métricas se imprimen en logs; los CSV de muestras permanecen locales y no se incluyen en el bundle.

Si un contenedor termina forzosamente, el lock remoto puede quedar activo. No expira automáticamente. Antes de retirarlo, comprobar que no existe ninguna ejecución activa y conservar la generación del objeto para eliminar exclusivamente ese lock. Después reanudar el ID conservado (`--resume-wasi`). No borrar bases, checkpoints ni el objeto de estado. Si se cambia un filtro o el listado cambió desde el checkpoint, iniciar otra ejecución en lugar de forzar la antigua. La prueba de adaptador con almacenamiento simulado no valida IAM, ADC, latencia o facturación reales.

Referencias oficiales comprobadas para esta preparación: [secretos en Jobs](https://docs.cloud.google.com/run/docs/configuring/jobs/secrets), [programación de Jobs](https://docs.cloud.google.com/run/docs/execute/jobs-on-schedule) y [cliente Cloud Storage / precondiciones](https://docs.cloud.google.com/python/docs/reference/storage/latest/google.cloud.storage.blob.Blob).

## Validación pendiente real

El 9 de noviembre se comprobó el login automático local con archivos privados externos y se ejecutó la captura operativa solicitada por el usuario; sus resultados y recuperación constan en [el informe de verificación](VALIDACION_WASI.md). Esa captura es distinta de las pruebas automatizadas, que usan únicamente datos sintéticos.

Antes de declarar operación desatendida validada se necesita construir la imagen; autorizar configuración y despliegue futuro; comprobar Secret Manager, IAM, bloqueo, restauración, checkpoints y una ejecución Cloud Run; ejecutar otra vez posteriormente **sin intervención manual**; medir duración, RAM, fichas reutilizadas y costes. No se promete el objetivo inferior a US$10/mes hasta medirlo. No se ha desplegado.

Las pruebas automatizadas usan SQLite sintético y páginas de portal simulado interceptadas en Chromium, sin contactar Wasi. Los resultados de la verificación de esta entrega se registran al cerrar el trabajo; no reutilizar los conteos históricos de v0.7 como pruebas nuevas.

## Búsqueda de La Carolina por título

En la inspección del 8 de noviembre, el selector de zonas de Usaquén no ofrecía La Carolina. Se verificó la búsqueda Bogotá D.C. / Usaquén, Apartamento, Vender, con el control real `Título` igual a `La Carolina`: el portal anunció 68 resultados. Esto es un filtro textual de título, no una equivalencia geográfica ni cobertura garantizada de todo el barrio. El valor `title` se conserva en la configuración y su identidad, se aplica antes de Buscar y se comprueba en el resumen activo. No se asigna ese texto como barrio a las fichas.

`wasi_run.py scrape --search ID_BUSQUEDA` permite ejecutar únicamente la búsqueda indicada, conservando las demás configuraciones sin capturarlas. Se puede repetir `--search`; no se combina con `--resume`, que usa el snapshot de la ejecución original. No hay límites de páginas ni anuncios.

Ejemplo reproducible de la búsqueda autorizada, con acceso ya configurado:

```powershell
# Registrar es idempotente por filtros y no captura.
$radarBusqueda = .\.venv\Scripts\python.exe scraper/wasi_run.py register --name 'Wasi · La Carolina (título), Bogotá · apartamentos en venta' --filters scraper/examples/wasi-la-carolina.json | ConvertFrom-Json
# Esta segunda orden sí inicia una nueva ejecución de esa búsqueda.
.\.venv\Scripts\python.exe scraper/wasi_run.py scrape --search $radarBusqueda.id
```

### Formato de archivos y sesión en uso

Los archivos externos de acceso admiten UTF-8 con o sin BOM, un valor literal o una línea etiquetada (`Usuario: …`, `Password: …`). Las etiquetas solo se interpretan en archivos; las variables de entorno conservan literalmente su valor. No se copian estos archivos al repositorio.

El portal puede mostrar «Tu usuario está siendo usado en otros dispositivos» y el enlace «Usar aquí». Sin autorización operativa, el scraper se detiene con `auth_session_in_use`. `WASI_USE_HERE=1` habilita pulsar ese enlace normal, únicamente cuando se ha autorizado trasladar la sesión y se han detenido los accesos simultáneos incompatibles. No se oculta el modal por JavaScript, no se extraen tokens y no se habilita por defecto. Puede desconectar otra sesión. No utilizarlo en un Job sin decidir previamente cómo se coordina con el acceso de Mónica.

La inspección real también encontró IDs duplicados en modales ocultos (por ejemplo, `bathrooms`). Los filtros se buscan exclusivamente dentro de `.advanced-search`; las opciones y sus comprobaciones siguen el mismo ámbito. Las esperas aceptan el reemplazo del nodo de control por el portal y el contacto móvil se toma del enlace de teléfono publicado, evitando incluir el texto del botón de WhatsApp.
