# Programación general de Radar Central — v0.13.0

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

El informe final de esta tarea se completa después de verificar los builds y recursos.
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
