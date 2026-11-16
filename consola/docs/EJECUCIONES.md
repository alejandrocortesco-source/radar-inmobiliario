# Radar Central — ejecución manual v0.12.3

Implementación en el clon independiente `Radar-CloudRun-20261111/repo`, rama
`codex/ejecuciones-manuales`, por autorización del 13 de noviembre de 2026.
Esta solicitud prevalece sobre la regla general de desarrollar en develop.
No cambia el dashboard de cuatro secciones, los identificadores ni las rutas anteriores.

## Ubicación actual

El dashboard sustituye Agregar fuente por Radar Central y conserva cuatro secciones.
Muestra hasta tres búsquedas, priorizando las de una ejecución activa, las que aún
no tienen captura y las últimas por fecha real. Sin fechas de creación disponibles
no se inventa una cronología de altas; una búsqueda nueva se identifica Sin ejecutar.
Un control activo sin actualización reciente aparece Por verificar hasta abrir su
seguimiento. Inicio solo lee el control, nunca restaura un segundo snapshot bajo el
lock web ni lanza Jobs. En modo local usa las capturas técnicas sintéticas disponibles.

Radar Central conserva la ruta `/v0.6/ejecuciones`. Su botón Agregar búsquedas abre
`/v0.6/ejecuciones/busquedas`: formulario y gestión anteriores, con los mismos POST.
Alta/edición, errores, duplicados, filtros dependientes, eliminación y activación
regresan a esa subpágina. Los enlaces de edición antiguos del inicio se redirigen.
Esta subpágina atraviesa WebDurable; solo las dos rutas de control exactas evitan
el snapshot. El registro auxiliar y el control durable no cambian de esquema.

## Uso y arquitectura

`/v0.6/ejecuciones` lista las búsquedas auxiliares existentes de las tres fuentes.
Guardar o editar sigue sin capturar. La selección usa el par fuente/id_busqueda.
Inactivas visibles y no ejecutables. POST valida forma, límites, existencia y
activación contra el snapshot actual bajo el bloqueo compartido. Se permite
hasta 100 búsquedas por solicitud, con rechazo explícito si se excede.
El Job vuelve a validar todas antes de comenzar; una selección inválida no captura.

La web reserva un UUID en `radar/executions/control.json` mediante CAS de generación,
libera el snapshot y solicita un Job con ese UUID. HTTP JSON devuelve 202 y el ID;
no espera la extracción. El único Job invocable está configurado por el operador
y limitado en código a radar-manual o radar-manual-review, en radar-inmobiliario-co,
us-central1. No acepta comandos, URLs nuevas ni nombres de Jobs del navegador.

`scraper/job.py --execution UUID` reutiliza las tres clases y configuradores
actuales. Cada scraper recibe exactamente una búsqueda y concurrencia 1.
Cada búsqueda conserva su run técnico, deduplicación, actualizaciones, ausencias,
historial y matching determinista. Gemini nunca forma parte de este mecanismo.
Un resultado parcial/fallido del portal permite continuar; errores SQLite/I/O,
pérdida del bloqueo, control o persistencia detienen el lote.

No hay threads, procesos ni BackgroundTasks de scraping en HTTP. La única tarea
async de captura vive dentro del contenedor del Job. Cerrar páginas o reemplazar
la revisión web no cancela el Job. El Job manual tiene una tarea, paralelismo 1,
cero reintentos y timeout total explícito de 10800 s. El timeout no recorta páginas:
puede interrumpir un lote demasiado largo y quedará registrado como tal.

## Concurrencia, incertidumbre y recuperación

El UUID es también la clave de idempotencia. Reenvíos de la misma selección
recuperan la reserva y nunca vuelven a llamar jobs.run. Otra selección con esa
clave, o una ejecución incompatible, devuelve 409. CAS impide dos reservas activas.
Un lanzamiento que pierde respuesta queda incierto, sin reintento automático.
Solo un CLOUD_RUN_EXECUTION puede reclamar el UUID; duplicados, reintentos y Jobs
tardíos tras el cierre de la reserva salen antes de tocar SQLite o el portal.

Mientras hay una reserva activa, una consulta como máximo cada 60 s por proceso web contrasta
Cloud Run (referencia exacta del trabajador o lista paginada filtrada por RADAR_RUN_ID).
Se consulta el Job guardado en el registro, aunque una revisión posterior configure
otro Job. Una reclamación concurrente invalida el cierre; primero se revoca la
reserva por CAS y luego se limpia el lock. Un fallo de limpieza conserva la reserva. Un heartbeat viejo no prueba
un fallo: si el Job sigue activo se mantiene la reserva y se avisa. Un Job terminal
sin cierre confirmado queda interrumpido. Si no aparece ningún Job después de
10 min y la consulta remota fue exitosa, se cierra y revoca la reserva: un lanzamiento
tardío no podrá capturar. Una caída de la API conserva la reserva y muestra el
problema; no autoriza otro lanzamiento. No se reutiliza la solicitud incierta.
La web no escribe acknowledgements del lanzamiento, marcas de consulta ni retención
sobre un registro activo. La reserva durable queda Solicitando Job hasta la reclamación
del trabajador; una respuesta incierta conserva esa reserva y se verifica por UUID,
sin volver a lanzar. La referencia del Job/trabajador permite consultar el resultado;
la operación HTTP puede quedar sin referencia si su respuesta no se conserva.
La observación remota se almacena solo en una caché de lectura de hasta 60 s, nunca
como autorización para repetir el lanzamiento. Retención y proyección de búsquedas
exigen ausencia de reservas activas dentro del mismo CAS, incluso después de una
carrera. Así se conserva compatibilidad con la imagen de Job anterior, que mantiene
un handle de Blob fijado a su última generación. El adaptador corregido usa un handle
nuevo para leer la generación vigente en cada lectura/reintento y validar el lock vivo.

Actualización en curso requiere confirmación de Cloud Run. Si falta, el aviso dice
Verificando el estado de una actualización anterior, con nombre, fuente, hora y
seguimiento; el UUID y referencias quedan en Detalle técnico. El sondeo actualiza
ambos mensajes. Una lectura incierta nunca convierte antigüedad en permiso para
liberar el bloqueo. Un cierre terminal conserva la fecha real de Cloud Run y distingue
interrupción de guardado durable confirmado.

La reconciliación es oportunista al consultar/iniciar; sin visitas no consume
recursos ni crea Scheduler. La siguiente visita recupera el estado real.

El token del lock se registra antes de adquirirlo y su generación al adquirirlo.
Una respuesta perdida de creación se comprueba leyendo el token. Tras muerte del
Job se retira únicamente el lock con esa generación o token, y solo después de
reconciliar que no existe un Job activo. Nunca se borra un bloqueo posterior ni
state.tar.gz. Los Jobs históricos/web usan el mismo lock; los locks históricos
huérfanos sin registro de control siguen requiriendo revisión operativa manual.

## Progreso y guardado

El registro de control es un JSON durable independiente del tar de SQLite.
La página y `/v0.6/ejecuciones/estado` atraviesan AccesoRadar pero no WebDurable:
leen control, sin cargar una copia local SQLite durante el Job. El listado es una
proyección identificada por su fecha de comprobación, no una copia operativa del
catálogo. Sin ejecución activa se refresca leyendo el snapshot bajo su lock.
Un alta recién guardada aparece en la siguiente visita y POST siempre revalida.

Heartbeat agregado cada 30 s, más transiciones por búsqueda; sin eventos por anuncio.
La página consulta cada 15 s y se pausa oculta o sin ejecución activa. Muestra
búsqueda/fuente, fase observable (listados/revisión), contadores fiables, transcurrido
y última actualización. Nunca estima un porcentaje de anuncios sin total fiable.
La falta de red del navegador no altera el estado del Job.

Snapshot consistente aproximadamente cada 60 s durante captura, al terminar cada
búsqueda y al cerrar el lote. Se comprueban integridad y propiedad del lock antes
de guardar, con precondición de generación. Extracción terminada no equivale a
éxito: el estado completado exige subida remota confirmada y liberación del lock.
Si se pierde la confirmación se informa guardado final no confirmado, aunque
pueda existir un snapshot remoto más reciente. Se conserva la última generación
confirmada. RPO durante un corte abrupto: último checkpoint; no hay reanudación
automática de búsquedas interrumpidas desde esta primera página.

## Métricas y estimación

Procesados: anuncios distintos por búsqueda con resultado técnico success,
unchanged, partial, failed o blocked. Incluye reutilización de ficha e incidencias;
excluye anuncios aún pendientes. No cuenta visitas HTTP ni inmuebles físicos únicos.
Nuevas/actualizadas/sin cambios: filas fiables success/unchanged, clasificadas como
new/modified/unchanged por el motor actual. Modified corresponde a cambio de precio;
no pretende contabilizar toda diferencia posible de atributos. Otras revisiones
pueden no entrar en esas tres categorías. Las sumas generales pueden repetir una
publicación presente en varias búsquedas. Una métrica no disponible aparece N/D,
nunca cero inventado. Se omiten los textos crudos de excepciones del proveedor.

Se leen en modo SQLite ro las últimas ejecuciones técnicas compatibles. Las capturas
históricas de varias búsquedas se identifican como compartidas y no se usan para
estimar duración individual. Se deduplican por run técnico las mediciones importadas
y las nuevas. Hasta cinco muestras completas y guardadas de la misma identidad:

| Carga | Criterio conservador sobre las muestras |
| --- | --- |
| Por estimar | Ninguna muestra comparable |
| Liviana | Todas <180 s y <100 procesados |
| Moderada | Alguna >=180 s o >=100 procesados, sin alcanzar pesada |
| Pesada | Alguna >=900 s o >=500 procesados |

El rango requiere al menos tres ejecuciones comparables: 0,75 × mínima duración
hasta 1,5 × máxima. Para el restante se resta solo el transcurrido de la búsqueda
actual y se agregan las pendientes con muestras suficientes. Superado el rango se
explica la demora sin tiempos negativos. Son constantes sencillas ajustables en
`ejecuciones/control.py`, orientación relativa; no CPU, memoria ni facturación.

## Retención y seguridad

Retención oportunista de 30 días, máximo 100 registros terminados y 2 MB del JSON
vivo; si se alcanza el límite de bytes salen primero los terminales más antiguos.
Nunca limpia ejecuciones activas, catálogo ni historial técnico previo.
Generaciones no actuales/soft delete siguen la política existente del bucket:
no son registros consultables en la UI y pueden conservar bytes adicionales.
No se cambió la política global del bucket para esta función.

El registro contiene IDs, nombres de búsqueda, fuentes, tiempos, contadores,
referencia de Job/operación y errores fijos saneados. No incluye configuración de
sesión, cookies, HTML, credenciales, clientes, teléfonos ni prompts.
El Job manual silencia logs técnicos por anuncio; conserva salida agregada.
IAP firmado y Origin estricto se mantienen para páginas, consultas y POST. No se
crean sesiones, cuentas ni autenticación paralela. Los límites y checks del servidor
no dependen de casillas HTML. Fechas y horas: America/Bogota.

## Revisión privada, alcance y reversión

`deployment/deploy-review.ps1` usa digests exactos del build existente, crea solo
radar-manual-review y asigna al servicio radar-web un rol personalizado sobre ese
Job: run.jobs.run, run.jobs.runWithOverrides, run.executions.get/list. Storage
radar/ y Secret Manager usan los permisos e identidades actuales. No amplía IAP,
OAuth, acceso público ni permisos de personas. Los tres Jobs previos se conservan.

La revisión etiquetada ejecuciones-review se despliega con --no-traffic. Producción
continúa en su revisión anterior. **Comparte servicio, identidades, secretos,
bloqueo, snapshot y catálogo con producción**: no es un entorno de datos aislado.
Consultar no captura. Iniciar desde la revisión puede actualizar esos mismos datos
y bloquear temporalmente las operaciones de catálogo/CRM de producción. No probar
scraping real sin explicar ese alcance y obtener la selección concreta del usuario.

Para retirar la revisión de prueba: comprobar primero ausencia de ejecución activa,
retirar solo su tag con `gcloud run services update-traffic radar
--remove-tags=ejecuciones-review --project=radar-inmobiliario-co --region=us-central1`.
No redistribuir porcentajes. Conservar el Job/control hasta cerrar lo activo;
después puede retirarse su binding específico y, bajo autorización operativa,
el Job de prueba. No eliminar snapshots ni borrar el registro para revertir código.
Si en una etapa futura se promueve, volver a la revisión anterior conserva las bases:
el control es aditivo, separado y la estructura SQLite de negocio no cambia.
No restaurar un backup para revertir UI; esa acción sí puede perder datos.

## Cuatro casos manuales

1. Abrir Ejecuciones por IAP: comprobar las tres fuentes, nombres/criterios,
   estados, historial previo disponible y selección deshabilitada sin casillas.
2. Guardar una búsqueda desde Radar Central y volver: debe aparecer sin captura previa.
   Seleccionar individualmente o todas las activas; una inactiva no debe habilitarse.
3. Con selección concreta autorizada, iniciar una vez y recargar el enlace del ID:
   mismo Job, avance por búsqueda y seguimiento disponible con catálogo ocupado.
4. Abrir el informe final y comparar resultado por búsqueda, N/D, tiempos,
   generación confirmada e historial. Los estados parcial/fallo se ejercitan con
   simulaciones locales; no provocar errores deliberados en el catálogo real.

Pruebas automatizadas y capturas nuevas: `consola/tests/test_ejecuciones.py`;
regresión durable: `test_cloud_durable.py`; suites consola, catálogo y scraper en
procesos separados, sin portales reales ni Gemini. Resultados de la entrega se
registran aparte una vez ejecutados; este documento no atribuye pruebas históricas.

Entrega comprobada, builds, permisos, resultados y manifiesto de archivos:
[informe del 13 de noviembre](ENTREGA_EJECUCIONES_20261113.md).

## Wasi: superposición al buscar (v0.12.3)

El Job y la web deben usar las imágenes de esta corrección: actualizar solo la web
no modifica el scraper. El cierre exige interceptor dentro de ProductFruits y un
único botón visible con nombre accesible Close/Cerrar (opcionalmente dialog/window/
ventana/diálogo). Un botón ambiguo, ausente o inaccesible conserva incompleto.
Se permite un único cierre y una comprobación posterior, con esperas acotadas;
Buscar solo se pulsa después de verificar su accesibilidad. No hay force=True,
remoción del DOM, aceptación de avisos ni toma automática de sesión.

La renovación del tbody, valores de filtros, resumen y paginador siguen siendo
obligatorios. Un total cero con respuesta renovada y cobertura verificada es válido;
sin listado verificado no se confirman ausencias. Los nuevos informes agregan
listing_error_count, listing_code, listing_pages y listing_complete, independientes
de error_count por anuncio. Son campos aditivos, sin migración. Las ejecuciones
históricas conservan sus mensajes originales, sin reescribir control ni catálogos.


## Metrocuadrado: respuestas de paginación (15/11/2026)

El listener acepta exclusivamente el hostname `www.metrocuadrado.com` y los paths
`/rest-search/search` o `/api/rest-search/search`; los parámetros de consulta no
cambian el reconocimiento. No acepta `/api/rest-search/search/seoelements` ni
hosts parecidos. Sigue validando el JSON y exige cambio de página activa y de
identificadores principales; HTTP 200 por sí solo no verifica el avance.
Se conservan coincidencia con el DOM, checkpoint, fin del paginador y comparación
de principales únicos con el total anunciado de esa captura. Los destacados no
cuentan para dicho total y pueden repetirse. Una discrepancia conserva incompleto
y no aplica ausencias/retiros. No se fijan 406 o 408 como total permanente.

La corrección requiere actualizar la imagen del Job `radar-manual-review`, sin
cambiar la web. No modifica datos ni el esquema de control. Preparación, pruebas,
digest, comprobación manual y reversión: [informe de revisión](METRO_RESPUESTAS_20261115.md).
