# Metrocuadrado: reconocimiento del listado y revisión privada

15/11/2026, America/Bogota. Clon independiente autorizado y rama
`codex/ejecuciones-manuales`. Corrección compatible sin migración. No cambia Wasi,
Fincaraíz, interfaz, autenticación, producción ni tráfico. No hay scraping real,
Gemini, Scheduler, push, merge ni tags Git en esta tarea.

## Causa y cambio

El diagnóstico autorizado del 13 de noviembre comprobó HTTP 200 en aproximadamente
0,38 s por `/api/rest-search/search`, página activa 2 y reemplazo completo de los
50 principales. El listener desplegado solo aceptaba `/rest-search/search`, por
lo que descartaba la respuesta y agotaba 45 s. No era instalación tardía del
observador ni repetición del destacado. Los artefactos privados se conservan en
`.tmp/metro-page-diagnostic-20261113-session2/`, fuera de Git e imágenes.

`is_listing_response_url` analiza hostname y path una sola vez. Acepta únicamente
`www.metrocuadrado.com` y las dos rutas exactas observadas; ignora la query para
este reconocimiento. No admite subdominios, sufijos, trailing slash, otros hosts,
otras rutas ni el endpoint seoelements. El único reconocedor operativo encontrado
usa esta función. No se fabrican solicitudes: las hace el portal tras el clic normal.

No cambia la estructura requerida (objeto con results lista), el observador previo
al clic, la página activa, fingerprint de principales, DOM contra JSON, checkpoint,
paginador final ni comparación de cobertura. Mantiene la protección de ausencias.
La versión visible de la web se conserva; esta corrección del Job se identifica
mediante commit fuente y digest inmutable, sin crear un tag.

## Validación aislada

Prueba nueva `scraper/tests/test_metro_responses.py`: rutas antigua/nueva, query,
hosts y paths ajenos; Chromium con todas las solicitudes interceptadas, sin red
real ni fichas. Doce escenarios de navegador verifican avance real, respuesta raíz
inválida, results inválido, JSON inválido, página activa sin cambio, principales
sin cambio, cambio solo de destacado, DOM divergente y cobertura insuficiente.
Los casos válidos incluyen destacado idéntico con principales distintos. Cada error
comprueba que la búsqueda siga incompleta y que no cambie el estado ni la racha
de ausencia de un inmueble sintético anterior. Los límites de páginas y anuncios
son None. Chromium y sus contextos se cierran también ante errores.

Resultados nuevos de esta tarea, procesos separados con bases en `.tmp/`:

| Comprobación | Resultado |
| --- | --- |
| Pruebas específicas del nuevo archivo | 12 aprobadas (incluyen 12 escenarios de Chromium) |
| Suite completa scraper | 144 aprobadas, 93,19 s |
| Suite completa catálogo | 249 aprobadas, 11,05 s |
| Suite completa consola, ejecución durable y generaciones GCS | 457 aprobadas, 272,90 s |
| pip check, compileall metro/ejecuciones, git diff --check | Correctos |

Cada suite emitió únicamente la advertencia de deprecación de BlockingPortal de
Starlette/AnyIO. No hubo fallos. La consola incluye sus verificaciones sintéticas
Chromium de escritorio, tablet y móvil; no cambia presentación. No son capturas
reales de portales ni nuevas mediciones del catálogo operativo.

Comando por suite, con PYTHONPATH apuntando a raíz, scraper y consola/tests:
` .venv/Scripts/python.exe -m pytest --rootdir=. -o pythonpath= COMPONENTE/tests -q --basetemp=.tmp/metro-response-regression-COMPONENTE-20261115 `.
Evidencias locales excluidas: `.tmp/metro-response-20261115/tests-*.txt`.

## Imagen desplegada y verificación posterior

- Commit fuente de runtime: `aa260cc4163e1e88ee6c973ff74ff8e6119be3a4`.
- Build regional: `cd551d75-54fc-4636-b981-0db15c0110fa`, SUCCESS.
  Inicio/fin: 15/11/2026 19:14:49–19:16:59 America/Bogota.
- Imagen construida: `us-central1-docker.pkg.dev/radar-inmobiliario-co/radar/jobs:aa260cc4163e`.
- Imagen efectiva de `radar-manual-review`:
  `us-central1-docker.pkg.dev/radar-inmobiliario-co/radar/jobs@sha256:890356e5be7562dab9bb9c510cab4f1883fbee6441ba781f1c91e0b15bd8025d`.
- Digest coincidente entre Cloud Build, Artifact Registry y spec del Job. Job Ready=True.
  Se fijó por digest inmutable, no por un tag móvil. No se ha lanzado una ejecución
  nueva con esta imagen; su comportamiento real sigue pendiente de prueba manual.
- Única modificación de spec: imagen y nonce de plantilla generado por Cloud Run.
  Idénticos argumentos, entorno, referencias Secret Manager, cuenta de servicio,
  recursos, una tarea, paralelismo, reintentos y timeout. La etiqueta histórica
  `source-sha=adccc7a10cef` no se cambió: no identifica este runtime; usar digest y
  commit fuente de este informe, acreditados en el build y el argumento OCI.
- No se reconstruyó ni desplegó web: el cambio está exclusivamente en el scraper.
  Web spec, anotaciones de acceso y status.traffic idénticos antes/después.
  Producción mantiene `radar-verify-20261111` al 100%; el tag de revisión sigue
  `radar-wasi-overlay-20261113` sin tráfico de producción.
- Todos los demás Jobs mantienen su spec. Las generaciones y MD5 de snapshot
  y control son idénticas a las del apartado de estado previo. Lock sigue 404.
  Lista de ejecuciones idéntica antes/después, todas con completionTime.
- No se añadieron recursos permanentes ni permisos. Se generaron imagen, build,
  fuente temporal y logs asociados; solo costo habitual de construcción/almacenamiento.
  El scraping manual futuro conserva sus recursos y persistencia compartidos.

Evidencia local excluida: `.tmp/metro-response-20261115/verification.json`,
`build.json`, `registry-image.json`, descripciones before/after y metadatos GCS.
No se borró ni modificó control, bloqueo, snapshot o catálogo.

## Cómo repetir manualmente

Abrir por IAP, con la cuenta ya autorizada:
https://ejecuciones-review---radar-dvhqhy5u3q-uc.a.run.app/v0.6/ejecuciones

Esta revisión comparte datos, snapshot, bloqueo, secretos e identidades con
producción. La repetición escribirá en el catálogo compartido. No se ha iniciado
automáticamente y no se requiere cambiar autenticación.

1. Seleccionar solamente Metrocuadrado «En la Carolina» y pulsar Iniciar ejecución.
2. Conservar el ID, abrir seguimiento y comprobar que pasa de página 1 a 2 y sigue
   con las páginas restantes. Puede cerrar/recargar la página sin lanzar otra ejecución.
3. Al terminar, comprobar el informe y detalle técnico, incidencias de listado y
   anuncios, guardado durable confirmado y cierre del Job. No repetir si queda
   verificando estado o aparece una ejecución incompatible.

Cobertura completa requiere página activa y principales distintos en cada avance,
coincidencia del DOM con el JSON, paginador Siguiente deshabilitado al final y
principales únicos iguales al total anunciado registrado para la captura actual.
No se deben contar destacados como principales ni fijar una cifra histórica.
Si cambia el total o hay discrepancias, conservar parcial e investigar, sin debilitar
la guarda. El estado completado exige además procesamiento seguro de las fichas,
confirmación remota del snapshot y cierre del bloqueo. La preparación de la imagen
y las pruebas sintéticas **no validan el scraper en operación**; queda pendiente
la captura real manual y su guardado durable.

## Reversión

Sin procesos activos, volver únicamente la imagen de `radar-manual-review` al digest
anterior indicado abajo mediante `../cloud.ps1 run jobs update`, indicando
`--project=radar-inmobiliario-co --region=us-central1 --image=IMAGEN_ANTERIOR --quiet`.
Comprobar después el digest efectivo. No ejecutar el Job como parte del rollback.
No cambiar web/tráfico ni restaurar SQLite, snapshot, control o historial: no existe
migración. La imagen anterior reproduce el defecto de reconocimiento del endpoint
nuevo; conservar ese límite al decidir repetir. No cancelar procesos ni retirar
bloqueos para revertir código.

Desde el clon autorizado, una vez confirmado que no hay procesos activos:

```powershell
& ../cloud.ps1 run jobs update radar-manual-review --project=radar-inmobiliario-co --region=us-central1 --image=us-central1-docker.pkg.dev/radar-inmobiliario-co/radar/jobs@sha256:096dd89ccf155ad93d411ad91594cf8987db88f2b75fc01c6884f90f471a4c4e --quiet
& ../cloud.ps1 run jobs describe radar-manual-review --project=radar-inmobiliario-co --region=us-central1 --format="value(spec.template.spec.template.spec.containers[0].image)"
```

## Git y archivos

Rama `codex/ejecuciones-manuales`, base conservada `195b521`. Commit de runtime
`aa260cc` y un commit documental posterior para registrar resultados del despliegue.
Sin push, merge ni tags Git. Ningún archivo del checkout original fue modificado.

Archivos de esta entrega:

- `scraper/metro/scraper.py`: comparación exacta y uso en el único listener.
- `scraper/tests/test_metro_responses.py`: pruebas aisladas de rutas, avance y cobertura.
- `scraper/README.md`: endpoints y principales.
- `consola/docs/EJECUCIONES.md`: criterio de reconocimiento y cobertura.
- `consola/docs/METRO_RESPUESTAS_20261115.md`: entrega, evidencia y reversión.
- `docs/README.md`: acceso al informe.
- `CHANGELOG.md`: corrección compatible sin nueva publicación funcional.

Sin conflictos. Al cerrar se comprueba árbol limpio. Los artefactos locales de
`.tmp/` permanecen excluidos de Git y de las imágenes. No hay migración de datos.


## Estado previo verificado en Cloud

Proyecto `radar-inmobiliario-co`, región `us-central1`, consultas por `../cloud.ps1`.
Los 13 registros de ejecución Cloud Run disponibles tienen completionTime. El
control tiene seis ejecuciones terminales y el lock operativo responde 404.
No se ha reconciliado ni alterado ningún registro.

- Producción: `radar-verify-20261111`, 100% del tráfico.
- Web privada: `radar-wasi-overlay-20261113`, tag `ejecuciones-review`, sin porcentaje.
- Job revisión anterior: `us-central1-docker.pkg.dev/radar-inmobiliario-co/radar/jobs@sha256:096dd89ccf155ad93d411ad91594cf8987db88f2b75fc01c6884f90f471a4c4e`.
- Snapshot: generación `1794587388484439`, MD5 `0kyUpjcJ9IJ5AHYKUM2JMg==`.
- Control: generación `1794587397321531`, MD5 `p2jNHAQqLTaw6/uac+7jZQ==`.
- Job manual sin max_pages ni max_details: el factory configura solo la URL
  seleccionada y concurrencia 1. Se conserva la infraestructura existente de
  una tarea/paralelismo 1, 1 CPU/2 GiB, cero reintentos automáticos y timeout 10800 s.
  No se añaden límites de páginas/anuncios ni se promete duración ilimitada.
