# Radar Central: diagnóstico y reconciliación del 13 de noviembre de 2026

Clon independiente, rama `codex/ejecuciones-manuales`. v0.12.2.
Este informe complementa el cierre anterior; no sustituye sus hechos históricos.

## Evidencia anterior a cualquier reparación

Todas las horas siguientes son America/Bogota, el 13 de noviembre de 2026.

- Informe anterior: commit e2ef455 a las 05:25:12; reportaba cero ejecuciones.
- Reserva posterior: `da02fdb6-7055-47e8-8d8a-f0e941668284`, creada 05:26:01.
  Selección: una búsqueda Fincaraíz, La Carolina, Bogotá, casas y apartamentos
  en venta. El ID mostrado procede de `radar/executions/control.json`, no del lock.
- Trabajador: `radar-manual-review-9cl2d`, con RADAR_RUN_ID coincidente. Comienzo
  del trabajador registrado 05:27:31; último progreso 05:27:33, Preparando portal.
- Una consulta web escribió `reconciled` a las 05:27:48. El historial de objetos
  conserva las generaciones de reserva, reclamación y progreso. Generación de
  control observada antes de reparar: 1794565668388644.
- Cloud Run confirma finalización 05:28:10.004012, una tarea fallida, exit code 2,
  Completed=False/NonZeroExitCode. El contenedor anunció exit(2) a las 05:28:07.
  Los logs agregados no conservan la excepción original; no se atribuye un error
  específico del portal, persistencia o scraper como hecho histórico probado.
- El control aún decía running, sin fin ni confirmación de guardado final.
  El objeto `radar/state.tar.gz.lock` devuelve 404, comprobado explícitamente.
  No se encontraron ejecuciones vivas de los Jobs manual, Metrocuadrado, Wasi,
  Fincaraíz o state-check. No se canceló ningún proceso ni se usó la antigüedad
  como prueba de abandono. Se reconsultó el estado terminal antes de reparar.
- Respaldo inicial existente: `backups/initial-20261111.tar.gz`, generación
  1794431837444747, 6054342 bytes, MD5 SPrTxapcz2R1OC/tXLHREw==, coherente con
  la entrega operativa. No se requieren migraciones ni restauraciones de bases.

El aviso protegía una reserva real. A las 05:27:48 el Job todavía estaba activo;
el registro persistente posterior quedó sin cierre. No hay evidencia de una
consulta de reconciliación posterior al cierre antes de esta investigación.
El informe anterior no contradice una solicitud realizada después.

## Defecto reproducido y corrección

El SDK google-cloud-storage 3.17.1 conserva generation en el Blob: reload vuelve
sobre esa versión histórica. El adaptador anterior reutilizaba ese mismo handle.
Una escritura web durante captura dejaba al trabajador leyendo su versión anterior;
los reintentos CAS fallaban y tampoco podía persistir el cierre de error. Una prueba
con el SDK instalado reproduce esa secuencia y el agotamiento de reintentos.
La secuencia remota y el primer heartbeat coinciden con este modo de fallo, pero
la ausencia de excepción original impide demostrar que fue la causa exacta del exit 2.
Sí se confirma el defecto del adaptador y el estado residual del registro.

- Lectura y reintento CAS toman un Blob nuevo para la generación vigente.
  La comprobación y liberación del lock también usan el objeto vivo, con condición
  de generación, sin confundir una versión histórica con propiedad actual.
- La web observa el control activo sin escribir marcas de consulta, retención o
  acknowledgements de lanzamiento. El trabajador conserva sus propias escrituras.
  Retención/proyección solo escriben si sigue sin haber reserva activa dentro del CAS.
  Esto permite mantener la imagen actual del Job: no se cambia el recurso Job.
- Caché de observación de hasta 60 s por proceso, descartable y solo de lectura.
  La ejecución y su protección siguen siendo durables en GCS/Cloud Run.
- Un cierre terminal exige evidencia remota, CAS que revoca la reserva, limpieza
  solo de su generación/token y cierre interrumpido con la fecha real de Cloud Run.
  Un fallo de consulta o limpieza conserva la reserva. Un trabajador concurrente
  invalida la reparación. No se relanza una solicitud de resultado incierto.
- El aviso diferencia Actualización en curso de Verificando el estado de una
  actualización anterior. Incluye búsqueda, fuente, inicio/solicitud y seguimiento.
  UUID/Job/operación quedan en Detalle técnico. El sondeo actualiza también el aviso.

## Validación

Pruebas nuevas con SDK real y transporte simulado versionado: 11 aprobadas.
Flujos afectados y Chromium: 57 aprobadas antes de agregar la última reproducción;
no sumar estas ejecuciones repetidas como pruebas distintas.
Catálogo completo: 249 aprobadas. Scraper completo: 122 aprobadas.
Consola completa sobre el código final: 456 aprobadas (259,83 s), incluidas las
11 pruebas nuevas. Pasada previa: 454 aprobadas; después se cerró y probó la carrera
de mantenimiento y se agregó la reproducción completa del adaptador anterior.
La comprobación real por IAP cerró el registro y verificó el mismo informe al recargar.
El detalle técnico muestra UUID y trabajador correctos. No se seleccionó ni inició
ninguna búsqueda real. La cabecera fija de versión se alineó después, sin cambios
funcionales; suite específica final y Chromium: 58 aprobadas. Sin sesión, la
revisión devuelve 302 a accounts.google.com. No se comprobó otra cuenta.
Solo bases sintéticas, sin portales reales ni Gemini. Se revisaron capturas de
escritorio 1440×900, tablet 768×1024 y móvil 390×844: foco, ausencia de overflow,
selección, aviso activo/por verificar, vacíos, progreso, completado y fallo.
Pip check, compilación y git diff --check correctos. Persiste la advertencia
conocida de BlockingPortal en Starlette/AnyIO.

## Alcance operativo y reversión

Se compiló únicamente web y se desplegó la revisión privada
`radar-central-reconcile-20261113`, sin tráfico de producción.
Runtime inicial de la corrección: cee0ceb84c980daf3a55dd86a0ad484d3c7ca73e.
Build inicial SUCCESS: b700555d-b189-4043-a4e3-2d7a4b4275fb.
La etiqueta fija de cabecera se alinea en el build final, registrado al cierre.
Las imágenes y configuración de Jobs, IAP/OAuth, secretos, permisos y Scheduler se
conservan. No se inicia scraping. Los fixes del adaptador quedan también preparados
en código para futuros builds de Jobs; esta tarea no sustituye sus imágenes.
La compatibilidad de la web observadora con el trabajador anterior está probada.

La revisión comparte catálogo, snapshot, bloqueo, secretos e identidades con producción.
La visita de seguimiento puede reconciliar control; no autoriza una nueva captura.
No se borra control.json ni se reinicia historial. La reparación solo debe cerrar
el registro terminal indicado y preservar el catálogo y las tres búsquedas.

Revertir presentación: reasignar solo el tag ejecuciones-review a la revisión anterior,
sin porcentajes ni restauración de datos. El control sigue en versión 1, con campos
aditivos que el código previo tolera. Volver al código anterior reintroduce escrituras
web durante captura y el defecto de generación: conservar la protección y evitar
nuevas ejecuciones manuales hasta volver a aplicar esta corrección. No restaurar un
snapshot ni un control histórico para revertir código.

## Comprobación manual sin captura

1. Abrir por IAP Radar Central y el informe del ID indicado: resultado Interrumpida,
   fecha final 05:28 y guardado final no confirmado; búsqueda Fincaraíz identificada.
2. Expandir Detalle técnico: UUID y trabajador coinciden; el historial conserva el registro.
3. Recargar y abrir el mismo enlace en otra pestaña: mismo informe, sin nuevos Jobs.
4. Abrir Inicio y volver a Radar Central: tres búsquedas existentes; el botón Iniciar
   sigue deshabilitado sin selección. No iniciarlo durante esta comprobación.

## Modificación remota confirmada

La visita por IAP a las 06:01 usó el reconciliador, sin editar objetos manualmente:
control running → reconciling → interrupted, una sola ejecución conservada,
job_result=failed, fin real 05:28:10.004012. Generación final de control observada:
1794567662708366. No había lock que retirar: 404 antes y después. Las lecturas del
listado usan su adquisición/liberación normal del lock compartido; no retiran
bloqueos ajenos. El snapshot no se subió ni se restauró durante esta reparación:
generación 1794565546045367, tamaño 6048505 bytes y MD5 zzSUE3eQHfS7R6qDdmYJIw==
idénticos antes y después. Se conservan las tres búsquedas. Métricas desconocidas
siguen N/D; no se afirma guardado final de la captura fallida.

URL privada del informe:
https://ejecuciones-review---radar-dvhqhy5u3q-uc.a.run.app/v0.6/ejecuciones?run=da02fdb6-7055-47e8-8d8a-f0e941668284

Producción permanece al 100% en radar-verify-20261111. Se cambian solo la imagen
web de revisión y su tag privado; se generan los artefactos normales de Cloud Build.
No hay cambios de permisos, autenticación, tráfico porcentual, secretos ni Jobs.
No se canceló ni lanzó ningún Job.

## Archivos y Git

Cambios locales, sin push, merge, tags ni conflictos, en la rama conservada.
Archivos de ejecución: ejecuciones/control.py, cloud_run.py y servicio.py;
adaptador compartido scraper/wasi/durable.py; versión scraper/metro/__init__.py.
Presentación: consola/ejecuciones.py, consola/static/ejecuciones.js,
consola/templates/v06/base06.html, ejecuciones06.html, _ejecucion06.html,
_ejecucion_aviso06.html y _ejecuciones_historial06.html. Pruebas:
consola/tests/test_ejecuciones.py y test_ejecuciones_generaciones.py.
Documentación: CHANGELOG.md, README.md, docs/README.md,
consola/docs/EJECUCIONES.md y este informe. Sin migraciones de datos.
