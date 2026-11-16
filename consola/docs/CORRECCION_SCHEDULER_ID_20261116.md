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
