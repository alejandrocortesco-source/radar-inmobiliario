# Corrección del contrato Scheduler — 16/11/2026

Solo clon y rama autorizados, base limpia 63f804f. Scheduler PAUSED y Radar
schedule.enabled=false comprobados por lectura antes de modificar. Sin activación,
llamada real a /trigger, scraping, jobs.run, IAM, IAP ni cambio de horario.

Reproducción previa: POST /trigger real vía TestClient, body JSON revision,
X-CloudScheduler-JobName corto y fecha consciente de zona: 422 en vez de 202.
La comparación exacta inicial de Programacion.deliver rechazaba el ID corto antes
de leer control, deduplicar, reservar o lanzar. La ruta solo declara Request:
no tiene parámetros/header aliases requeridos por FastAPI; headers.get de Starlette
es insensible a capitalización. El cuerpo revision lo configura Radar en Scheduler.

La incompatibilidad con el contrato documentado está reproducida. Sin el header
real de las solicitudes anteriores no queda demostrada definitivamente su causa.
Fuente: https://docs.cloud.google.com/scheduler/docs/configuring/deduplicate-job-requests

scheduler_identity deriva el ID corto de scheduler.name confiable y compara el valor
completo recibido exactamente con ambas representaciones. No valida por sufijos,
no cambia mayúsculas ni obtiene proyecto/región del solicitante. Ambas se convierten
al nombre completo antes del UUID5. Programacion.deliver también aplica la función:
no hay una vía alternativa sin normalización. Tiempo ausente/inválido se rechaza;
calendario, revisiones, pausas, CAS, recibos, exclusión y recuperación no cambian.

El receptor añade logs JSON de esta ruta con request_id generado, código fijo,
formato short/full e identidad canónica solo válida, fecha UTC validada y run_id
si existe. No imprime contenido rechazado, headers, body, tokens o excepciones.
Códigos: authentication_failed, missing_job_header, unrecognized_job,
missing_schedule_header, invalid_schedule_time, invalid_json, missing_revision,
invalid_revision, body_too_large, occurrence_validation_failed y
 durable_reservation_unconfirmed; aceptación durable registra su estado.
No se cambia la autenticación ni validación global de FastAPI.

Solo el disparador requiere actualización: web y worker no llaman deliver ni al
endpoint receptor. Se construye la imagen web como contenedor del disparador, pero
no se despliega en el servicio Radar ni en el Job de extracción.

Reversión: con Scheduler PAUSED, actualizar únicamente radar-schedule-review a
us-central1-docker.pkg.dev/radar-inmobiliario-co/radar/web@sha256:7bf127ad9fb10cb34d8f10bfc9f8321976538326600b48119d3bc3b01f15960b
mediante ../cloud.ps1 run services update, proyecto radar-inmobiliario-co y región
us-central1. No cambiar entorno, IAM, snapshots ni tráfico del servicio Radar.

La corrección aislada no acredita automatización operativa. La próxima prueba
programada autorizada deberá verificar formato recibido, canonical_job,
scheduled_at, request_id, reserva y un solo Job; después cobertura, resultados,
guardado y pausa. No se repite esa prueba en esta tarea.


## Resultados comprobados

Reproducción previa del endpoint: una prueba fallida, 422 en vez de 202, con el
receptor real y dependencias inertes. Tras corregir: 121 pruebas aprobadas de
cabeceras/programación/ejecuciones/generaciones (27,78 s). Archivo final de cabeceras,
incluidos payload generado por Scheduler y concurrencia entre representaciones:
26 aprobadas (1,71 s). 24 de esas 26 ya pertenecían a las 121; no sumar conjuntos.
Se corrigió durante regresión el orden de validación del cuerpo para no construir
clientes Cloud ante un body incompleto. Única advertencia: deprecación conocida
BlockingPortal Starlette/AnyIO. compileall y git diff --check correctos.

Casos HTTP: ID corto/completo, nombres de headers con distinta capitalización,
Job/proyecto/región ajenos, valores ausentes/vacíos, mayúsculas diferentes,
prefijos/sufijos/segmentos extra, tiempo ausente/inválido/sin zona, cuerpo inválido,
pausa, autenticación denegada y logs acotados. Equivalencias secuenciales y concurrentes
reservan un único UUID y lanzan un solo Job simulado. Recuperación, CAS, bloqueo
físico y coexistencia Manual se verifican en regresiones existentes, sin portales.
No se cambió presentación: no corresponde repetir pruebas visuales ajenas.

Commit fuente: 3402c3c62350e3132295e665c6d5e4b34df1a5d5.
Build bb816914-2d60-4321-abaa-2cf4e9273d0f, SUCCESS.
Solo radar-schedule-review actualizado, revisión radar-schedule-review-idfix-3402c3c,
Ready=True. Imagen efectiva (spec, status y Artifact Registry coincidentes):
us-central1-docker.pkg.dev/radar-inmobiliario-co/radar/web@sha256:ccacf8c39047f0fdd815f54c59be5f7c78e39a02388960f1eac9e2e9303c6715.
Entorno, identidad, recursos e ingress internal conservados frente al antes.

Web privada sigue radar-programacion-20261116-61b65b8 con digest 7bf127ad…;
radar-manual-review conserva d46281a6… y executionCount=8. Producción sigue al 100%
en radar-verify-20261111. No se alteraron código o imágenes de scrapers/worker/web,
IAM o IAP, ni se hizo una llamada real a /trigger. El contenedor web construido
se usa únicamente para alojar el disparador corregido.

Al cierre: Scheduler JSON idéntico al previo y PAUSED, incluyendo horario lunes
08:15 America/Bogota. Control GCS idéntico byte por byte, enabled=false y sin nuevos
registros. Metadatos de snapshot idénticos: generación 1794792532218538, 54.278.100
bytes. No hubo scraping, Gemini ni actualización del catálogo compartido.
Evidencia local excluida en .tmp/scheduler-id-fix.

Archivos modificados: ejecuciones/programacion.py, ejecuciones/disparador.py,
consola/tests/test_scheduler_headers.py, este informe, consola/docs/PROGRAMACION.md
y RADAR_PROYECTO_RECTOR.md. Rama conservada, sin conflictos, push, merge o tags.
El commit documental posterior registra los resultados sin cambiar runtime.

Reversión concreta (documentada, no ejecutada), dejando Scheduler PAUSED:

```powershell
../cloud.ps1 run services update radar-schedule-review --project=radar-inmobiliario-co --region=us-central1 --image=us-central1-docker.pkg.dev/radar-inmobiliario-co/radar/web@sha256:7bf127ad9fb10cb34d8f10bfc9f8321976538326600b48119d3bc3b01f15960b --quiet
```

La reversión restaura también el defecto del ID corto. No requiere restaurar datos.
La evidencia aún pendiente es el formato efectivamente recibido en una nueva
ocurrencia real autorizada y la cadena completa hasta guardado de las tres fuentes.
Los registros de noviembre anteriores no permiten reconstruir ese header ausente.
