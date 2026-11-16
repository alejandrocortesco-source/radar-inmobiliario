# Programación general de Radar Central — v0.13.0

> Evolución local posterior, sin desplegar: [programación múltiple](PROGRAMACION_MULTIPLE.md). Esta guía conserva la arquitectura y evidencia del calendario compartido desplegado.

16/11/2026, America/Bogota. Clon y rama autorizados: Radar-CloudRun-20261111/repo,
codex/ejecuciones-manuales. Base 28c2b22 limpia. No se reconstruye ningún scraper.

## Uso

Un calendario para todas las búsquedas seleccionadas, identificadas por fuente/ID.
Días lunes a domingo y hora estricta HH:MM (00:00–23:59), America/Bogota explícito.
Guardar no inicia captura. Si ya está activa, Guardar reemplaza el calendario y
solo acepta fechas posteriores a la edición. Activar habilita próximas fechas,
sin disparo inmediato ni recuperación de fechas pasadas. Pausar cierra el gate
antes de modificar Cloud y no cancela trabajadores que ya reclamaron la ejecución.
Manual sigue independiente, con la misma exclusión durable. Búsquedas nuevas no
se añaden; inactivas/eliminadas se omiten al revalidar el snapshot en el Job y
se registra advertencia. Si no queda ninguna, se omite todo sin tocar portales.

La UI muestra estado verificado, resumen, próximas cinco fechas de Bogotá, lotes
semanales y máximo de capturas de búsquedas. El estado incierto dice Desactivada ·
Por verificar y explica la corrección. No hay consumo/duración inventados; las
mediciones existentes continúan en la tabla manual. Formulario normal con labels,
fieldset/legend, foco, validación de servidor y errores accesibles. No requiere JS
para programar. Las tablas anchas conservan su contenedor de desplazamiento.

## Arquitectura y autenticación

Cloud Scheduler -> OIDC -> radar-schedule-review (Cloud Run, ingress internal,
IAM privado, min=0) -> control GCS por CAS -> radar-manual-review. La web Radar
conserva IAP, Origin estricto, identidad y tráfico de producción. No se añade una
excepción de autenticación a la web. El disparador también valida firma, issuer,
audiencia, expiración e identidad exacta de radar-scheduler; ningún header de
Scheduler por sí solo autentica. JobName exacto y ScheduleTime RFC3339 son obligatorios.
El cuerpo solo contiene revisión de configuración, nunca credenciales o URLs.

Destino fijo por operador: projects/radar-inmobiliario-co/locations/us-central1/
jobs/radar-weekly-review. La cuenta radar-scheduler solo invoca ese servicio.
radar-schedule-dispatch solo modifica control y consulta/recupera el lock exactos
mediante condiciones de bucket, y usa el rol de ejecución limitado al Job de revisión.
No puede leer/escribir snapshot ni leer secretos. La web recibe un rol personalizado
con get/fullView/create/update/pause/enable de Scheduler y actAs sobre la cuenta
Scheduler exacta; no run/delete, IAM administrativo ni claves de servicio.
Scheduler solo permite estos roles al nivel proyecto; código restringe el recurso.

Fuentes oficiales verificadas el 16/11/2026:
- [Scheduler y OIDC](https://docs.cloud.google.com/scheduler/docs/http-target-auth).
- [Destino Cloud Run](https://docs.cloud.google.com/run/docs/triggering/using-scheduler).
- [Ingress interno desde Scheduler](https://docs.cloud.google.com/scheduler/docs/creating).
- [Identidad de ocurrencias y deduplicación](https://docs.cloud.google.com/scheduler/docs/configuring/deduplicate-job-requests).
- [API Job: state es output-only](https://docs.cloud.google.com/scheduler/docs/reference/rest/v1/projects.locations.jobs).
- [Permisos mínimos](https://docs.cloud.google.com/scheduler/docs/access-control).

CreateJob no permite crear directamente PAUSED. Para respetar la condición de esta
entrega no se crea ahora ningún Scheduler operativo. Guardar desactivada sin recurso
solo persiste GCS. La primera activación explícita posterior crea el nombre fijo;
el gate está bloqueado durante la operación. No se crea una ventana activa seguida
de pausa durante este despliegue. Pausas posteriores usan PauseJob y confirman PAUSED.
La cuenta/agente administrado de Scheduler deberá conservar roles/cloudscheduler.serviceAgent.

## Persistencia, duplicados y recuperación

Campos aditivos schedule, schedule_audit y schedule_receipts en control.json;
ninguna tabla SQLite ni snapshot se usa para guardar horarios. Auditoría 30 cambios,
recibos dos días (el margen de aceptación es solo 15 minutos), historial existente
30 días/100 terminales/2 MB. Los recibos impiden relanzamiento aunque un informe
salga de retención durante el margen aceptable. Una entrega más vieja siempre
se omite aunque ya no exista su recibo. No se altera un snapshot histórico.

Una operación de configuración reserva token CAS y conserva configuración anterior
más desired durable. Mientras hay pending se bloquea todo nuevo inicio automático.
Pause/Patch/Resume de Cloud se verifican por GET: cron, zona, destino, OIDC, cuerpo y
estado. Solo entonces se confirma schedule. Un fallo, timeout o corte conserva
pending y la configuración anterior; nunca se presenta Activa sin confirmación.
Guardar/Pausar explícitamente recupera tras 90 segundos desde el comienzo de una
operación incierta (una operación normal termina antes). Otra ventana con revisión
vieja recibe 409. No hay sondeo frecuente ni reconciliador que active por su cuenta.
Si Cloud está inaccesible se informa Por verificar. Un GET solo verifica, no activa.

Ocurrencia UUID5 = nombre completo de Scheduler + revisión + hora prevista UTC.
ScheduleTime permanece igual en reintentos de Scheduler. Se valida configuración,
hora exacta semanal, fecha posterior a activación/edición y recepción entre 0 y
15 minutos después. Pausadas/sustituidas/tardías/futuras se registran omitidas.
La reserva y la comprobación de ejecución manual/automática son una sola mutación
CAS. La existencia del lock compartido también omite. No se acumula una cola.
Duplicados reciben la reserva/omisión existente y nunca vuelven a jobs.run.

El disparador no descarga ni adquiere el lock del snapshot: no puede dejarlo
huérfano al morir. Solo el propietario de una nueva reserva solicita el Job una vez.
Si muere entre reserva y solicitud, o la respuesta del API se pierde, se conserva
launching. La reconciliación preexistente consulta por UUID; tras 10 min sin Job
y con lectura remota exitosa revoca la reserva como interrumpida. No relanza ni
repite fuentes completas. Un trabajador tardío/duplicado no puede reclamarla.
Si la API falla no se libera por antigüedad. Siguiente visita/ocurrencia reconcilia.

El worker comprueba pausa/revisión en el CAS de reclamación. Después de started,
una pausa no lo cancela. Revalida búsquedas contra snapshot, omite las no elegibles
y usa el mismo bucle secuencial, métricas finales, cobertura, checkpoints, confirmación
de guardado y recuperación de locks. Un lock que aparezca entre disparador y Job
hace omitir el automático sin esperar ni capturar. Manual conserva su comportamiento.
Fallos/parciales de fuente conservan la política actual; errores de persistencia
interrumpen el lote. Gemini no forma parte de este flujo.

## Costos

[Cloud Scheduler](https://cloud.google.com/scheduler/pricing): US$0,10 por Job/31 días,
contando también pausados; tres Jobs gratuitos por cuenta de facturación, compartidos
entre proyectos. No se conoce el uso agregado de esa cuenta, por tanto no se promete
que aplique. Sin recurso creado, esta entrega no añade una cuota Scheduler mensual;
al activarlo, presupuestar US$0,10/mes antes del beneficio gratuito.

[Cloud Run](https://cloud.google.com/run/pricing): disparador con CPU bajo demanda,
min=0, 1 vCPU/512 MiB; se pagan peticiones/tiempo activo por encima del nivel gratuito
compartido. GCS, versiones/soft delete, logs, builds y Artifact Registry son aparte.
Como ejemplo de planificación, 31 entregas al mes de 10–60 s cada una,
1 vCPU y 0,5 GiB, suponen aproximadamente US$0,008–0,047 de disparador antes de
beneficios gratuitos (CPU US$0,000024/s, memoria US$0,0000025/GiB-s y peticiones
US$0,40/millón). Es un supuesto, no una medición; se añade US$0,10 de Scheduler y
operaciones GCS/logs/artefactos no cuantificados: alrededor de US$0,11–0,15/mes
para programación bajo ese ejemplo, excluyendo scraping y costos puntuales de build.
El nivel gratuito de servicios por peticiones incluye 180.000 vCPU-s, 360.000 GiB-s
y 2 millones de solicitudes al mes por cuenta; disponibilidad agregada no verificada.
El costo del scraping depende de duración y búsquedas: no es el costo de Scheduler.
No hay prueba operativa nueva ni medición suficiente para prometer el objetivo
US$10/mes. Las estimaciones de carga existentes no son mediciones de facturación.

## Verificación y despliegue

La evidencia efectiva de esta entrega consta al final de esta guía.
Pruebas nuevas en consola/tests/test_programacion.py, datos sintéticos en .tmp y
transportes de Cloud simulados. Ninguna prueba accede a portales o a catálogo real.
Script reproducible: deployment/deploy-schedule-review.ps1, invoca ../cloud.ps1.
Actualiza únicamente Job/revisión privados y añade el disparador y permisos mínimos.
No crea el calendario, no ejecuta Jobs ni distribuye tráfico de producción.

## Reversión

1. Si fue activada posteriormente, Pausar desde Radar y confirmar gate desactivado
   y Scheduler PAUSED antes de retirar código; no cancelar un Job ya iniciado.
2. Comprobar ausencia de ejecuciones activas. Reasignar solo el tag ejecuciones-review
   a radar-resultados-20261116-680ef8b, sin cambiar porcentajes. Producción debe seguir
   radar-verify-20261111 al 100%.
3. Volver la imagen de radar-manual-review a
   us-central1-docker.pkg.dev/radar-inmobiliario-co/radar/jobs@sha256:cba1da6dc8eab2e4dde7af9b4ec0d303cebf7fff7bfa58df00f0f54e0b3ea7e3.
   Conserva Metrocuadrado, Wasi y resultados finales anteriores.
4. Sin reservas activas, se puede retirar el servicio disparador y sus bindings
   específicos bajo autorización operativa. No eliminar snapshots/control, restaurar
   backups ni retirar locks como mecanismo de reversión. Configuración es aditiva.

## Cuatro casos de revisión

1. Configuración: elegir búsquedas/fuentes, martes y viernes, 00:30; Guardar con
   estado Desactivada. Recargar: selección y resumen persisten. No inicia scraping.
2. Edición: cambiar días/hora o selección y Guardar mientras desactivada. Recargar
   y revisar la estimación semanal; nuevas búsquedas quedan sin seleccionar. No captura.
3. Pausa: con configuración desactivada, Pausar confirma el gate cerrado sin captura.
   En prueba operativa futura, pausar Activa debe confirmar PAUSED; no cancela lo iniciado.
4. Coexistencia: marcar selección manual y comprobar que Iniciar ejecución sigue
   disponible con calendario activo. No pulsarlo en esta revisión: marcar casillas
   no captura. Activar solo para prueba operativa posterior: programa la siguiente
   fecha, sin inicio inmediato. Un horario durante Manual quedará omitido, sin cola.


## Entrega verificada el 16/11/2026

Runtime construido desde el commit limpio
61b65b85865998343d29151e23557e9d2d4559df. La ampliación posterior de pruebas visuales
y este informe no cambian código de runtime y no requieren reconstruir imágenes.
Rama conservada, sin conflictos, push, merge o tags.

### Pruebas realmente ejecutadas

| Conjunto | Resultado | Duración |
| --- | --- | --- |
| Consola: programación, ejecuciones, generaciones GCS, durable, resultados finales, acceso y navegación | 193 aprobadas | 47,28 s |
| Archivo final test_programacion.py, con ampliación de API/CAS y estados de UI | 43 aprobadas | 7,05 s |
| Catálogo: adaptador SQLite e identidades | 38 aprobadas | 0,62 s |
| Scraper: Metro responses, Wasi announcements, incremental y runner guards | 69 aprobadas | 68,08 s |
| pip check, compileall, parser PowerShell y git diff --check | Correctos | — |

El archivo final de programación comparte 38 casos con la regresión de 193; los
conjuntos no se suman. Los cinco posteriores amplían API/CAS y Chromium, sin cambios
de runtime. Advertencia única: deprecación conocida de BlockingPortal Starlette/AnyIO.
No se ejecutaron suites ajenas de CRM, Gemini o extracción real. Adaptadores/identidades
y guardas/incremental se verificaron porque la selección automática reutiliza esas
fronteras. No se atribuyen pruebas de entregas anteriores a esta ejecución.

Las pruebas cubren medianoche, cambio de semana, zona IANA, validación estricta,
guardar/activar sin captura inmediata, pausa/edición, reconstrucción del servicio,
sincronización incierta, formularios viejos y CAS concurrente. Cuatro entregas
simultáneas producen un solo lanzamiento. Se comprueban recibos fuera de retención,
respuesta de lanzamiento perdida, revocación/reconciliación, trabajador tardío,
conflictos manual/auto y lock físico antes/después de reservar, pausa antes y después
de started, eliminación/inactivación, selección nueva no incorporada, persistencia,
parcial de fuente, historial y reportes. Firma RSA OIDC real con certificados
sintéticos: audiencia, expiración, identidad y firma incorrectas rechazadas.

Chromium intercepta todas las solicitudes hacia TestClient y fakes de Cloud/Storage.
Escritorio 1440x900, tablet 768x1024 y móvil 390x844: formulario desactivado/guardado,
activo con cinco fechas, botón Manual disponible al seleccionar, error Cloud sin
filtrar secretos, búsquedas vacías y advertencia. Foco y labels, hora HH:MM y ausencia
de overflow de página. Capturas inspeccionadas visualmente en .tmp/programacion-20261116,
con nombres programacion/activa/error/vacia-{ancho}.png; son datos sintéticos.

### Recursos e imágenes efectivos

Builds SUCCESS en radar-inmobiliario-co/us-central1:

| Imagen | Build | Horario Bogotá |
| --- | --- | --- |
| Web y disparador | 46519361-1e67-4e67-97a4-965b67c5f8f8 | 07:25:21–07:26:49 |
| Job | ca0b6f4b-98e3-4e0e-aaa1-5c10c24f818a | 07:25:21–07:27:09 |

- Web de revisión: radar-programacion-20261116-61b65b8, Ready=True, 0%.
- Disparador nuevo: radar-schedule-review-00001-p94, Ready=True, ingress internal,
  identidad radar-schedule-dispatch, min=0, max=1, 1 vCPU/512 MiB, sin secretos.
- Ambas usan el digest efectivo (spec y status.imageDigest):
  us-central1-docker.pkg.dev/radar-inmobiliario-co/radar/web@sha256:7bf127ad9fb10cb34d8f10bfc9f8321976538326600b48119d3bc3b01f15960b.
- radar-manual-review usa:
  us-central1-docker.pkg.dev/radar-inmobiliario-co/radar/jobs@sha256:d46281a68d306745e897c561f5b07ef198a9b4ace4257d6ca8eee5f16a7f6043.
  Su spec es idéntica a la anterior salvo imagen y nonce generado. Conserva una
  tarea, paralelismo 1, cero reintentos, 10800 s, identidad, secretos y entorno.
- Los digests coinciden con Cloud Build y Artifact Registry.
- Producción conserva radar-verify-20261111 al 100%; tag ejecuciones-review apunta
  únicamente a la revisión nueva. IAP=true e invoker de radar limitado al agente IAP.
- API cloudscheduler.googleapis.com habilitada. Su agente administrado conserva
  roles/cloudscheduler.serviceAgent. Scheduler jobs list devuelve []: ningún calendario
  creado ni activo, por la condición de no crear recursos inicialmente habilitados.

Cuentas nuevas: radar-scheduler y radar-schedule-dispatch. Roles personalizados
radarScheduleManager y radarScheduleStorage con las listas exactas versionadas en
los JSON de deployment. Bindings nuevos: manager a radar-web en proyecto; actAs de
radar-web sobre radar-scheduler; Storage de dispatcher condicionado a control.json
(o lock exacto); ejecución de dispatcher sobre radar-manual-review; invoker de
radar-scheduler exclusivamente sobre radar-schedule-review. No hay allUsers,
allAuthenticatedUsers, claves JSON, permisos de personas nuevos ni lectura de secretos.
No se modifica la autenticación del servicio Radar existente. La cuenta Scheduler
no puede ejecutar directamente el Job, editar horarios ni leer el catálogo.

### Revisión privada y conservación

URL verificada con la sesión IAP existente, usando computer-use en modo lectura:
https://ejecuciones-review---radar-dvhqhy5u3q-uc.a.run.app/v0.6/ejecuciones#programacion

La pantalla real muestra v0.13.0, Desactivada, las tres fuentes, siete días, HH:MM
00:30, Bogotá visible y los tres botones. Ninguna selección se guardó o activó en
datos operativos. El informe histórico sigue 69 procesados / 1 nuevo / 0 cambios /
68 sin cambios de precio, con 55 reutilizados y 13 releídos, sin reescribirlo.

Después de esa consulta, snapshot conserva generación 1794792532218538 y tamaño
54.278.100 bytes; control conserva generación 1794792546779732 y 16.733 bytes.
Igualdad con metadatos anteriores comprobada. Job conserva executionCount=8; ningún
scraping real, Job de extracción nuevo o Gemini. La petición externa sin credencial
a /trigger devuelve 404 por ingress interno, antes de alcanzar la aplicación.
La validación OIDC dentro del contenedor se comprueba localmente con firma real y
material sintético; no se afirma una entrega Scheduler operativa de extremo a extremo.
Tampoco se hizo una captura real: esa prueba sigue pendiente de activación autorizada.

Artefactos locales excluidos: metadatos before/after, JSON de builds/Registry/revisiones,
IAM del disparador y capturas de .tmp/programacion-20261116. No se añaden snapshots,
logs privados ni datos de catálogo al repositorio. No cambia política global del bucket.

### Manifiesto de archivos

| Área | Archivos |
| --- | --- |
| Control y coordinación | ejecuciones/control.py, ejecuciones/worker.py, ejecuciones/programacion.py, ejecuciones/scheduler.py, ejecuciones/disparador.py |
| Consola y frontera durable | consola/ejecuciones.py, consola/durable.py, consola/static/ejecuciones.css |
| Plantillas | consola/templates/v06/ejecuciones06.html, _programacion06.html, _ejecuciones_historial06.html, _ejecucion06.html, base06.html |
| Pruebas | consola/tests/test_programacion.py |
| Despliegue e IAM | deployment/deploy-schedule-review.ps1, schedule-manager-role.json, schedule-storage-role.json |
| Versión y zona IANA | scraper/metro/__init__.py (solo versión), scraper/requirements.lock.txt (tzdata==2026.6) |
| Documentación | RADAR_PROYECTO_RECTOR.md, README.md, CHANGELOG.md, docs/README.md, consola/docs/EJECUCIONES.md y esta guía |

25 archivos. Scrapers Metrocuadrado, Wasi y Fincaraíz sin cambios de código; catálogo,
matching, resultados finales e informes históricos conservan sus implementaciones.

Comandos de reversión documentados, no ejecutados, después de pausar si se activó
posteriormente y verificar ausencia de reservas/trabajadores activos:

```powershell
../cloud.ps1 run services update-traffic radar --project=radar-inmobiliario-co --region=us-central1 --update-tags=ejecuciones-review=radar-resultados-20261116-680ef8b --quiet
../cloud.ps1 run jobs update radar-manual-review --project=radar-inmobiliario-co --region=us-central1 --image=us-central1-docker.pkg.dev/radar-inmobiliario-co/radar/jobs@sha256:cba1da6dc8eab2e4dde7af9b4ec0d303cebf7fff7bfa58df00f0f54e0b3ea7e3 --quiet
```

Comprobar de nuevo digest del Job, tag privado y producción al 100% en su revisión
conservada. Ninguna restauración de datos forma parte de revertir la presentación.


## Prueba operativa posterior: arranque rechazado y pausa confirmada

La solicitud del 16/11/2026 autorizó crear Scheduler activo y una sola captura
real de las tres búsquedas La Carolina. Guardar/Activar desde UI funcionaron sin
inicio inmediato y Scheduler disparó a las 08:15 Bogotá, pero el endpoint devolvió
422 antes de reservar. No comenzaron scrapers ni un Job y no hay guardado nuevo.
Radar quedó Desactivada y radar-weekly-review PAUSED desde la interfaz. Se conserva
lunes 08:15 con esas tres búsquedas. No reactivar hasta corregir y validar el contrato
del header JobName (ID corto documentado frente a ruta completa esperada).
No se repitió la prueba ni se aplicó una corrección de runtime en esta tarea.
Diagnóstico, propuesta mínima, límites y evidencia: [prueba operativa](PRUEBA_PROGRAMACION_20261116.md).


Corrección posterior autorizada del contrato JobName: [normalización exacta y diagnóstico](CORRECCION_SCHEDULER_ID_20261116.md). La validación operativa sigue pendiente; Scheduler permanece pausado.
