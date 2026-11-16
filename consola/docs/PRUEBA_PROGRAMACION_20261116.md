# Prueba operativa de programación v0.13.0 — 16/11/2026

## Resultado y alcance

**Validación operativa incompleta.** El horario real de Cloud Scheduler sí envió
solicitudes al disparador privado, pero este devolvió HTTP 422 antes de crear una
reserva durable. No comenzó ningún Job ni ninguna captura de Metrocuadrado, Wasi o
Fincaraíz. No existe un informe de ejecución nuevo. No se invocó Gemini.

**Estado final seguro: Radar Desactivada y Cloud Scheduler PAUSED.** La pausa se
hizo con el botón Pausar de Radar Central; no fue necesario el mecanismo administrativo.
No se repitió la prueba, reprogramó otro horario, forzó Scheduler ni llamó jobs.run
como sustituto. Los reintentos HTTP configurados en Scheduler no iniciaron capturas.

La solicitud del usuario de esta fecha autorizó excepcionalmente crear Scheduler
activo y una única ejecución automática real con las tres búsquedas existentes.
Sustituye para esta prueba la restricción previa de no crear un recurso inicialmente
activo. No autoriza otro intento real después del defecto encontrado.

Clon exclusivo Radar-CloudRun-20261111/repo, rama codex/ejecuciones-manuales,
HEAD inicial 736bdc4, limpio. Runtime permanece en 61b65b85865998343d29151e23557e9d2d4559df.
No se cambió código de runtime, imágenes, autenticación, IAM o tráfico. Solo se
creó/configuró/pausó el calendario y se registró esta evidencia documental.

## Preparación comprobada

Sin reservas activas en control, sin ejecuciones Cloud Run activas entre los Jobs
consultados y lock compartido ausente (404). La búsqueda activa es inequívoca en
cada fuente. Se leyó una copia inmutable del snapshot y de su SQLite auxiliar;
no se abrió ningún portal para verificar filtros ni se crearon búsquedas.

Configuración previa: no existía campo schedule en el control y Scheduler jobs
list estaba vacío. La UI mostraba Desactivada, sin búsquedas/días seleccionados,
hora predeterminada 00:30. Se guardaron copias locales excluidas antes de operar.

### Búsquedas seleccionadas, sin ampliar alcance

| Fuente | ID y filtros conservados |
| --- | --- |
| Metrocuadrado | https://www.metrocuadrado.com/inmuebles/venta/bogota/la-carolina — En la Carolina; venta, Bogotá, La Carolina, tipos de la URL existente sin añadir filtros |
| Wasi | wasi:f531c03d6fc9771c29865577fd3b7746517a49fcf893268398a77eb64d7c05f1 — país 1 (Colombia), departamento 15 (Cundinamarca), ciudad 794 (Bogotá D.C.), localidad 1 (Usaquén), tipo 2 (Apartamento), operación 1 (Vender), title=La Carolina |
| Fincaraíz | https://www.fincaraiz.com.co/venta/casas-y-apartamentos/la-carolina/zona-norte/bogota — Venta (1), Casas (1) y Apartamentos (2), Bogotá 65d441f3-a239-4111-bc5b-01c5a268869f, barrio La Carolina 0f82b8b1-fc61-46a4-a4f8-ec7ab7032280 |

Wasi usa el título La Carolina y la localidad Usaquén; no se presentó como un filtro
geográfico de barrio ni se sustituyó por una búsqueda distinta. Fincaraíz conserva
los demás campos históricos del portal en su configuración, sin usarlos como nueva
condición del matching. Orden serial del formulario guardado: Fincaraíz, Metrocuadrado,
Wasi. No se llegó a procesar ese lote.

### Componentes y permisos efectivos

- Web privada radar-programacion-20261116-61b65b8, Ready=True, tag ejecuciones-review,
  0% de tráfico; producción radar-verify-20261111 al 100% antes y después.
- Disparador radar-schedule-review-00001-p94, Ready=True, ingress internal.
- Web y disparador: us-central1-docker.pkg.dev/radar-inmobiliario-co/radar/web@sha256:7bf127ad9fb10cb34d8f10bfc9f8321976538326600b48119d3bc3b01f15960b.
- radar-manual-review: us-central1-docker.pkg.dev/radar-inmobiliario-co/radar/jobs@sha256:d46281a68d306745e897c561f5b07ef198a9b4ace4257d6ca8eee5f16a7f6043.
- Los commits de correcciones Metrocuadrado aa260cc, Wasi 48b22a0 y resultados
  680ef8b siguen siendo antecesores del código construido; los digests coinciden
  con la entrega v0.13.0 anterior. No se reconstruyeron imágenes para esta prueba.
- radar-web conserva get/fullView/create/update/pause/enable de Scheduler y actAs
  exclusivamente sobre radar-scheduler. El agente administrado conserva su rol
  cloudscheduler.serviceAgent. El disparador conserva acceso condicionado a control
  y lock y ejecución del Job de revisión. La cuenta radar-scheduler solo tiene
  invoker sobre el disparador; ninguna concesión nueva ni acceso público.
- OIDC usa radar-scheduler@radar-inmobiliario-co.iam.gserviceaccount.com y audiencia
  https://radar-schedule-review-56106530298.us-central1.run.app.
- IAP de Radar sigue habilitado; no se modificaron identidades, secretos o policies.

## Cronología real (Bogotá, UTC−05:00)

| Evento | Hora del 16/11/2026 |
| --- | --- |
| Guardar desde la UI, confirmado en auditoría | 08:02:07.992753 |
| Activar: inicio de sincronización | 08:02:52.680149 |
| Activar: confirmado en auditoría | 08:03:00.312350 |
| Ocurrencia elegida y confirmada por Scheduler | 08:15:00 |
| Primera solicitud observada en Cloud Run | 08:15:01.077554 |
| Primera respuesta del disparador | HTTP 422, latencia 8,346143914 s, incluido arranque en frío |
| Scheduler registra el primer fallo | 08:15:19.641654, FAILED_PRECONDITION / HTTP 422 |
| Reintento HTTP interno observado en Cloud Run | 08:15:40.467468, HTTP 422, latencia 0,143880607 s |
| Scheduler registra ese fallo | 08:15:45.867573, FAILED_PRECONDITION / HTTP 422 |
| Pausar desde Radar: inicio del gate de configuración | 08:16:12.644928 |
| Pausar: confirmado por Radar | 08:16:17.286545 |
| Registro posterior de Scheduler, sin petición correlacionada al contenedor | 08:16:42.472256, estado HTTP 200 en su log; no acredita captura ni reserva |

Entre la activación confirmada y la ocurrencia hubo aproximadamente doce minutos.
La UI mostró como primera fecha 16/11/2026 08:15; Scheduler confirmó
scheduleTime=2026-11-16T13:15:00Z, cron `15 8 * * 1` y timeZone America/Bogota.
Guardar y Activar no cambiaron la lista de ejecuciones. A las 08:09:03 todavía
había cero registros nuevos y executionCount=8, descartando un inicio inmediato.

No hay horas de inicio/cierre de scraping porque no empezó. La hora de cierre de
la prueba no debe confundirse con la confirmación de una captura: solo quedó pausada.
El último status administrativo de Scheduler es code=-1; no se usa como prueba de
éxito o de captura. El estado efectivo comprobado es PAUSED. El 200 posterior de su log no
se presenta como éxito: no tiene una solicitud equivalente en Cloud Run ni evidencia
posterior en control, Job o snapshot.

## Evidencia de cadena y límites

Recurso creado:
projects/radar-inmobiliario-co/locations/us-central1/jobs/radar-weekly-review.
Destino /trigger del servicio interno de revisión. Los logs de solicitudes de Cloud
Run muestran POST y User-Agent Google-Cloud-Scheduler con dos respuestas 422.
El endpoint devuelve 401 si authenticate falla; 422 pertenece a la validación de
ocurrencia posterior. Esto permite afirmar que ambas capas de autenticación llegaron
a permitir el procesamiento hasta esa validación; no se conservaron ni expusieron
los tokens o headers de autorización.

No se creó una reserva automática ni un recibo de ocurrencia en GCS. La lista runs
es idéntica a la copia previa; por eso **no existe ID Radar ni ejecución Cloud Run
asociada** a esta prueba. El UUID calculado localmente para anticipar el seguimiento
no se considera un ID de ejecución real y no se enlaza como informe.

| Fuente | Cobertura/páginas | Incremental/contadores | Guardado nuevo |
| --- | --- | --- | --- |
| Metrocuadrado | No ejecutada | No verificables en esta prueba | Ninguno |
| Wasi | No ejecutada | No verificables en esta prueba | Ninguno |
| Fincaraíz | No ejecutada | No verificables en esta prueba | Ninguno |

No se declaran cobertura completa, protección de ausencias ni conciliación operativa
validadas por esta prueba. Al no empezar ningún scraper tampoco se aplicaron bajas,
retiros o actualizaciones. El snapshot conserva generación 1794792532218538 y
54.278.100 bytes. El Job conserva executionCount=8 y su ejecución histórica anterior;
no hubo un Job nuevo con salida 0 que pudiera interpretarse como prueba de guardado.
Lock final ausente (404). Los históricos y el catálogo permanecen intactos.
El snapshot sin cambios conserva también las tablas Gemini previamente vacías.

URL privada de configuración (no de un informe nuevo):
https://ejecuciones-review---radar-dvhqhy5u3q-uc.a.run.app/v0.6/ejecuciones#programacion

## Defecto reproducido y corrección mínima propuesta

La documentación oficial vigente describe X-CloudScheduler-JobName como el **ID
corto del Job**, y pide incorporar el contexto de proyecto/región al deduplicar:
https://docs.cloud.google.com/scheduler/docs/configuring/deduplicate-job-requests
(consulta del 16/11/2026, sección How request deduplication works).

Programacion.deliver compara el header directamente con el nombre completo fijo
`projects/radar-inmobiliario-co/locations/us-central1/jobs/radar-weekly-review`.
La entrada corta `radar-weekly-review`, en el código desplegado, produce
ValueError: Job de Scheduler no permitido, antes de leer el control. Se reprodujo
con el código real y objetos inertes, sin ADC, Cloud, SQLite o portales. Las pruebas
sintéticas anteriores solo enviaban el nombre completo y omitieron este contrato.
Es un defecto confirmado y compatible con el 422 observado. Los logs actuales no
incluyen el header recibido ni un código específico por validación, por lo que
no se afirma haber capturado su valor exacto o descartado toda causa adicional.
El body configurado se comprobó válido: JSON con revision UUID de 36 caracteres.

Propuesta acotada, **no aplicada ni desplegada**:

```python
canonical = self.scheduler.name  # proyecto, región y Job fijados por el operador
short_id = canonical.rsplit('/', 1)[-1]
if job not in {short_id, canonical}:
    raise ValueError('Job de Scheduler no permitido.')
job = canonical  # identidad durable única para ambas formas aceptadas
```

Aceptar únicamente ese ID esperado, dentro del endpoint autenticado por la cuenta
exacta de Scheduler, y canonicalizar antes de calcular UUID5/recibos. Seguir rechazando
otros Jobs, nombres completos de otro proyecto/región, horarios inválidos, revisiones
sustituidas y programación pausada. No alterar IAM, ingress, validación OIDC, CAS,
exclusión compartida, tolerancia de quince minutos ni política de reintentos.
Antes de otro intento real: añadir pruebas aisladas con el formato corto oficial,
compatibilidad exacta del formato completo, nombres ajenos y deduplicación entre
formas; añadir diagnóstico por códigos fijos de rechazo sin tokens/headers crudos.
Después revisar y desplegar la corrección mínima en componentes privados bajo su
alcance autorizado. Otra prueba real requiere una nueva autorización: no se intentó.

## Configuración temporal final y reactivación posterior

Quedó guardado lunes a las 08:15, America/Bogota, con las tres búsquedas anteriores.
Radar enabled=false, sin pending, revisión 89f5b928-4d02-4a9b-863c-601032a60bea;
Cloud Scheduler PAUSED. Se conserva el recurso, no se elimina. No queda una futura
ocurrencia operativa habilitada ni una cola de capturas.

Tras corregir el contrato y validar con datos aislados:
1. Abrir Radar Central, revisar fuentes y selección, cambiar días y hora a una fecha
   futura adecuada de Bogotá; Guardar manteniendo Desactivada.
2. Revisar resumen, frecuencia y fecha/hora actuales; con autorización operativa,
   pulsar Activar. Confirmar Activa y la próxima fecha efectiva (hoy u otra elegida).
3. Una prueba posterior debe usar un único horario futuro, esperar el disparo real,
   pausar tras started y comprobar los resultados completos. No usar Ejecutar ahora
   o iniciar manualmente para sustituir la cadena pendiente.

## Archivos y comprobaciones de esta tarea

Evidencia local excluida en .tmp/programacion-operativa-20261116-1258: control previo,
guardado, activado y final; snapshot anterior; filtros verificados; metadatos de
servicios/Job; policies relevantes; logs del horario; metadatos finales y lock 404.
Solo se conservaron identificadores operativos y agregados necesarios en este informe.
No se publican bases, HTML de portales, tokens, cookies o credenciales.

Se ejecutó la prueba de horario real descrita y una reproducción local del contrato
de header. No se repitieron las suites sintéticas de la entrega anterior ni se
presentan como resultados nuevos. No se modificaron scrapers o código de app.
Documentación modificada: este informe, PROGRAMACION.md y documento rector.
Sin conflictos, push, merge o tags; la rama autorizada se conserva.

Comprobación de cierre adicional a las 08:23 Bogotá: Scheduler PAUSED, contador del
Job 8, Radar enabled=false sin pending, cero reservas nuevas y cero recibos.
