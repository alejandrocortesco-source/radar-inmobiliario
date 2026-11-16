# Diagnóstico por etapas Wasi — 16/11/2026

Base limpia 9c01f9a, rama codex/ejecuciones-manuales y clon autorizados conservados.
Evidencia previa: captura automática 1f6df037-7dbc-55e1-a216-23d6bc6034c2,
Wasi run 6: authenticated, listing_incomplete/wasi_listing_unverified; cero páginas,
listing_complete=0 y absence_applied=0. No permite atribuir causa a popup o sesión.
El wrapper discover perdía las excepciones originales de filtros, resumen, tabla y
paginador. Las condiciones booleanas de lote agotaban su espera y acababan igual.

Instrumentación sin cambios de filtros, clics, retiros o reintentos: contexto por
tarea del scraper; etapas authentication, network_access/network_authentication,
filter:campo, before_search, search_click, table_refresh/table_mutation, summary_read,
filter_verify/summary_verify:campo, first_page, next_page, detail y cobertura.
Cada fallo conserva última etapa completada, inicio/duración, timeout pasado,
acción/condición, intento, tipo de excepción y mensaje fijo saneado. Causa desconocida
se presenta explícitamente como causa_no_determinada. No se deduce la causa de la
clase TimeoutError. Advertencias recuperadas se distinguen mediante finish y el
resultado final; no se captura cada ficha exitosa. Los originales históricos no
se enriquecen ni reescriben retrospectivamente.

Evidencia permitida: path conocido sin query, estado/count/hit del control,
igualdad y valores numéricos de filtro (texto libre solo longitud), filas/IDs
numéricos hasta 100, paginador/processing, contador de mutaciones, tokens de resumen
permitidos, presencia de login/diálogo/anuncio/verificación. Hasta 12 metadatos de
peticiones ajax: host/path sin query ni IDs numéricos, método, HTTP y duración.
No cuerpos, HTML, HAR, trazas, contactos, cookies o credenciales. Observación antes
de cerrar la página. El viewport completo se omite porque contiene datos de cuenta
/anunciantes; solo se intenta PNG de un select fijo de filtro, nunca login o ficha.
No manipula el DOM para sanear imágenes ni altera el manejo actual de anuncios.
CAPTCHA/acceso restringido conserva las guardas actuales y detiene el portal.

Persistencia: eventos wasi_diagnostic en SQLite técnico y agregado aditivo del
control para la UI. JSON privado en radar/diagnostics/wasi/ID_RADAR/N.json y, si es
seguro, PNG de select; referencia gs:// visible en el desplegable, sin URL pública.
Máximo ocho fallos detallados por lote Wasi, 32 KiB por JSON, 100 KiB por PNG,
100 etapas en memoria y máximo 12 eventos de red; captura/subida como máximo 15 s.
Errores auxiliares se anotan por tipo y nunca cambian la excepción ni el resultado.
Retención WASI_DIAGNOSTIC_DAYS: 14 por defecto, configurable entre 1 y 90 días.
Limpieza oportunista al subir un fallo, hasta 100 eventos antiguos y sus objetos
referenciados, sin listar bucket o modificar lifecycle/IAM. Sin nuevas ejecuciones
no hay limpieza autónoma; generaciones históricas/soft delete siguen la política
existente del bucket. No se promete borrado inmediato de versiones históricas.

UI: etapa fallida y explicación breve, detalles JSON saneados desplegables y refs
privadas. Datos ausentes en históricos permanecen ausentes. Sin cambio de diseño.

Pruebas de esta tarea: 102 regresiones Wasi/anuncios/ejecuciones aprobadas (196,64 s),
12 escenarios nuevos Chromium y tres vistas (1440/768/390) aprobados juntos sobre c5ab88a: 15 passed en 21,58 s, sin portales reales. Persistencia compartida: seis pruebas de test_cloud_durable aprobadas (1,90 s).
El formulario de login sintético se corrigió para ser visible; no cambió el scraper.
La evidencia de la única ejecución real autorizada se añadirá tras cerrar su Job.

Reversión: devolver web privada a radar-programacion-20261116-61b65b8 y Job a
us-central1-docker.pkg.dev/radar-inmobiliario-co/radar/jobs@sha256:d46281a68d306745e897c561f5b07ef198a9b4ace4257d6ca8eee5f16a7f6043
tras comprobar ausencia de capturas activas; no modificar porcentajes de producción,
Scheduler, IAM, IAP ni restaurar bases. Campos/eventos son aditivos. El disparador
Scheduler conserva su imagen corregida de ID; no actualizarlo ni revertirlo.


## Única prueba real autorizada: resultado

El 16/11/2026 se inició desde Radar Central privado una sola captura Manual de la
misma búsqueda Wasi, sin límites de páginas/anuncios ni cambios en filtros:
`wasi:f531c03d6fc9771c29865577fd3b7746517a49fcf893268398a77eb64d7c05f1`.
País 1, departamento 15, ciudad 794, localidad 1; apartamento 2, vender 1;
título La Carolina. No se ejecutaron Metrocuadrado, Fincaraíz ni Gemini.

Radar: `c3dc2dbe-231b-4c08-b704-2afa08bf7ab9`.
Cloud Run: `radar-manual-review-nbkjd`, technical_run Wasi 7.
[Informe privado](https://ejecuciones-review---radar-dvhqhy5u3q-uc.a.run.app/v0.6/ejecuciones?run=c3dc2dbe-231b-4c08-b704-2afa08bf7ab9).

Horas Bogotá del 16/11/2026:

| Hito | Hora |
| --- | --- |
| Solicitud/reserva desde interfaz | 10:56:13.105 |
| Inicio trabajador durable | 10:57:10.491 |
| Autenticación confirmada | 10:57:40.333 |
| Página 1 verificada/guardada | 10:58:06.793 |
| Página 2 y cobertura completa | 10:58:15.425 |
| Extracción y agregación de búsqueda terminada | 11:03:16.870 |
| Guardado durable y cierre Radar | 11:03:54.039 |
| Cloud Run Completed=True, succeededCount=1 | 11:03:59.094 |

Wasi completó: 69 anuncios distintos, dos páginas (50 + 19), total anunciado 69,
listing_complete=1, pendientes 0. Contadores conciliados desde el SQLite remoto:
0 nuevos, 0 actualizados de precio y 69 sin cambios de precio; estos últimos son
56 fichas reutilizadas y 13 releídas. Parciales/fallidos/bloqueados/sin clasificar: 0.
Autenticación authenticated; diagnóstico listing_complete/last_completed=next_page,
recovered=false. No se registraron fallos ni recuperación de popup en esta prueba.
Los filtros, resumen, renovación, primera página y avance se validaron por el flujo
normal; 13 eventos wasi_detail_saved confirman la lectura de las fichas pendientes.

Control persisted=true y generación exacta `1794845033755129` descargada y revisada
con SQLite mode=ro: quick_check=ok; run 7 completed y cobertura coherente con las
páginas persistidas. absence_applied=1 solo tras cobertura completa; cero membresías
con last_missing_run=7: no hubo nuevas ausencias ni retiros por esta captura.
Metro y Fincaraíz son byte a byte iguales al snapshot confirmado de las 09:00.
La base auxiliar solo añadió el registro normal de identificación determinista;
clientes, búsquedas, decisiones, matching y tablas Gemini conservaron contenido.
El snapshot Wasi sí se actualizó con su ejecución, observaciones y 13 fichas releídas.
Lock efectivo `radar/state.tar.gz.lock`: 404 tras el cierre, sin bloqueo residual.

La programación se conservó íntegra (comparación del objeto schedule antes/después):
activa, lunes 09:00 America/Bogota, las tres búsquedas originales, revisión
2b09798b-9fdc-464a-afb6-f8c249950932. Scheduler ENABLED; próxima 23/11/2026 09:00
Bogotá. No se guardó/editó/pausó/activó ni invocó Scheduler durante esta tarea.
Producción continúa 100% en radar-verify-20261111; no se modificó IAM ni IAP.

## Componentes utilizados en la prueba

Fuente de imágenes: commit `c5ab88a15d175ca5ea3ce84ccae884a23ba9c60a`.

| Componente | Estado y digest |
| --- | --- |
| Web privada radar-wasi-diag-c5ab88a, tag ejecuciones-review | Ready=True, 0% de tráfico; web@sha256:625b93201edb523a9df7cc47bf95ec417cd6f1902bcb95173e693f0cba5f3d72 |
| Job radar-manual-review, generación 9 | Ready=True; jobs@sha256:aea88e592bcdd8d7c943e3bd40f1c3318818d4b0fb59b1c43ae6caf992fb1615; mismo digest en la ejecución nbkjd |

Builds regionales SUCCESS: web 5aa3e665-1cbc-42e9-8af1-b4b19c23f42c y
jobs 3c4d8fd4-16fb-47c7-87f1-01cbf0fe9d90. Disparador radar-schedule-review no
actualizado: conserva la corrección del identificador de Scheduler.

## Límites de la conclusión y evidencia

El fallo de las 09:00 NO se reprodujo. No hay causa confirmada de aquel fallo ni
corrección funcional nueva que atribuir a este resultado. La instrumentación queda
disponible para una próxima incidencia autorizada, sin iniciar otra prueba aquí.
No se crearon PNG/JSON de fallo de esta ejecución porque no hubo fallos; no se
capturó el viewport con datos de cuenta/anunciantes. La subida de evidencia ante
un fallo no se ejercitó en Cloud en esta captura exitosa, solo con pruebas aisladas.
No se reconstruyen cronologías detalladas para la ejecución anterior.

Evidencia local excluida de Git en `.tmp/wasi-diagnostico/`: control-before/pretest/
final, scheduler-before/after, job-final, revision-final, web-final, logs-final,
snapshot-verification.txt y copia de la generación final. No contiene credenciales
exportadas; snapshots operativos siguen privados y no se añaden al repositorio.
No hay artefactos públicos. La UI real mostró Completada y guardado confirmado;
el desplegable técnico de fallos se comprobó con fixtures sintéticos, pues no hubo
fallo real que mostrar. No se propone aún una corrección funcional sin reproducción.

Archivos de código: scraper/wasi/diagnostico.py, browser.py, scraper.py, overlays.py;
ejecuciones/worker.py; consola/templates/v06/_ejecucion06.html. Pruebas nuevas:
scraper/tests/test_wasi_diagnostic.py y consola/tests/test_wasi_diagnostic_ui.py.
Documentación: este informe, EJECUCIONES.md, documento rector e índice docs/README.md.
Commits locales de implementación/pruebas: a577c4b, d729728, 972dbdf y c5ab88a.
Sin conflictos, push, merge ni tags.

## Reversión operativa, sin restaurar datos

Comprobar primero que no haya ejecución activa; después, usando ../cloud.ps1:

```powershell
& ../cloud.ps1 run jobs update radar-manual-review --image=us-central1-docker.pkg.dev/radar-inmobiliario-co/radar/jobs@sha256:d46281a68d306745e897c561f5b07ef198a9b4ace4257d6ca8eee5f16a7f6043 --project=radar-inmobiliario-co --region=us-central1
& ../cloud.ps1 run services update-traffic radar --update-tags=ejecuciones-review=radar-programacion-20261116-61b65b8 --project=radar-inmobiliario-co --region=us-central1
```

Verificar Job Ready y tag, sin redistribuir porcentajes de tráfico. Los datos y
campos adicionales pueden conservarse. No restaurar el snapshot previo, no revertir
el disparador de Scheduler y no cambiar la programación semanal.

Revisión final de instrumentación: se detectó y corrigió que una etapa exitosa
purgaba las advertencias recovered del anillo en memoria y, por tanto, del informe.
Se conservan hasta ocho errores, ocho recuperaciones y 84 etapas exitosas (100 en
memoria). La prueba sintética de popup ahora comprueba también esa conservación;
12 pruebas de diagnóstico aprobadas en 22,91 s después del ajuste. No cambia el
cierre real anterior: allí no hubo advertencias ni errores. No se repite la captura.
La imagen c5ab88a de la tabla anterior identifica la prueba real; el manifiesto
final del Job después de esta mejora se detalla a continuación.


## Manifiesto final de instrumentación

Job radar-manual-review generación 10 Ready=True, imagen efectiva:
`us-central1-docker.pkg.dev/radar-inmobiliario-co/radar/jobs@sha256:3e9d12c04aa7cefcc568e29fbaa147897e29fd739c81226ee33c5a5b112e8525`.
Fuente b193cb1ec8961cb414da3a1f4033c8d1861db102; build regional
c3fe4814-133b-4c2d-9b7d-249a449db8e8 SUCCESS. La web conserva la revisión
radar-wasi-diag-c5ab88a y digest 625b93201edb523a9df7cc47bf95ec417cd6f1902bcb95173e693f0cba5f3d72;
el último ajuste solo afecta al worker. Se comprobó el digest leyendo el recurso
completo, no la etiqueta source-sha histórica del Job.

No se ejecutó la imagen final de nuevo contra Wasi: el ajuste postcaptura solo
conserva advertencias recuperadas en memoria/informe y pasó las 12 pruebas sintéticas.
Contador de ejecuciones Job: 9 antes, 10 después; última y única nueva nbkjd,
EXECUTION_SUCCEEDED. Scheduler sigue ENABLED lunes 09:00, próxima 23/11/2026,
y el lock efectivo sigue ausente. La revisión final no escribió otro snapshot.
El conjunto de pruebas de la tarea comprende 123 casos distintos aprobados
(102 regresiones, 12 diagnósticos, 3 vistas y 6 de persistencia); las 12 de diagnóstico
se repitieron tras el ajuste final. Única advertencia de pruebas: alias BlockingPortal
deprecado de Starlette/AnyIO. Sin scraping adicional ni corrección funcional del portal.
