# Resultados finales de ejecución y revisión privada

16/11/2026, America/Bogota. Solo clon independiente y rama autorizados,
`codex/ejecuciones-manuales`, base limpia `6c68007`. Se conservan las correcciones
operativas Metrocuadrado (`aa260cc`) y Wasi (`48b22a0`); ningún archivo del scraper
se modifica. Sin nuevas capturas reales, Gemini, Scheduler, push, merge o tags Git.

## Definición y cambio

El fallo confirmado mostraba 69 procesados pero 1 nuevo + 55 sin cambios. Trece
fichas previas releídas con éxito conservaban classification=review y quedaban
fuera de la proyección del informe. Esa clasificación es una decisión inicial.

`ejecuciones/resultados.py` calcula solo la presentación final por anuncio:

- Estado parcial/fallido/bloqueado conserva su resultado.
- Pendiente/processing queda fuera de procesados y se informa aparte.
- Ficha fiable nueva con evidencia no_catalog_detail cuenta como nueva.
- Las otras fichas fiables comparan precio previo y final con los normalizadores
  monetarios existentes. Igual cuenta sin cambios; distinto cuenta actualizada.
- Éxito técnico sin documento fiable o evidencia de comparación suficiente cuenta
  sin clasificación final, sin inventar igualdad. Valores inválidos no prueban cambio.

**Actualizados significa cambio de precio comparable.** No representa cualquier
cambio de texto, foto o atributo. Sin cambios de precio tampoco demuestra igualdad
de toda la ficha. No se cambia el matching ni la política COP del negocio.

Procesados = nuevos + actualizados + sin cambios + parciales + fallidos + bloqueados
+ sin clasificación final. Reutilizados y releídos sin cambio están dentro de sin
cambios, no se suman otra vez. El método no documentado en un histórico se informa.
La comparación no modifica classification, decision_reason, jobs, fichas, cobertura,
checkpoints, ausencias ni condiciones de éxito/persistencia del scraper.

## Arquitectura e históricos

Worker.metrics y el informe web/API comparten el mismo cálculo. Las capturas
futuras guardan métricas agregadas aditivas report_version=2 en el control habitual;
no se añade esquema SQLite ni otro almacenamiento. Los motivos originales siguen
sirviendo para diagnóstico.

Una ejecución antigua cerrada sin métricas nuevas se proyecta desde su snapshot
confirmado: generación explícita, captura técnica y búsqueda comprobadas, total
contrastado con el control. Las identidades se conservan, reutilizando la
normalización de fuente cuando aplica. Se extraen solamente las bases técnicas
necesarias a un temporal; SQLite se abre ro+immutable+query_only y se cierra antes
de eliminarlo. No se llama a Store, cargar, __enter__, guardar o al lock del estado.
No se vuelve a tomar el catálogo vigente para reclasificar un histórico.

La proyección es una copia en memoria. El control original con 1/0/55 y los
snapshots de la ejecución investigada permanecen intactos. Se muestra una nota de
derivación y un detalle con los contadores originalmente registrados. Si falta
snapshot/generación/referencia/esquema, se presenta la limitación; si hay estados
terminales pero no comparación suficiente, se conserva un grupo sin clasificación.
Un histórico no compatible nunca se trata como nuevo ni sin cambios por defecto.

La caché guarda solo hasta cuatro resúmenes por generación y selección técnica,
una hora para lecturas correctas y treinta segundos para fallos, sin cuerpos de
fichas ni tarballs. La primera consulta antigua puede descargar el tar existente;
no necesita infraestructura o IAM nuevos. Durante un Job, el seguimiento activo
solo lee control. Consultar otro histórico usa su versión inmutable y no interfiere.
No se cambian retención ni reconciliación operativa preexistentes.

## Evidencia aislada y pruebas

Fixture sintético construido con el Store existente: baseline de 68 fichas, nueva
captura con 55 reutilizaciones, 13 review/price_not_comparable resueltas por lectura
y una nueva. Resultado 69 = 1 nuevo + 0 cambios de precio + 68 sin cambios; dentro
de esos 68, 55 reutilizados y 13 releídos. Se verifica la preservación byte a byte
de la base al calcular las métricas y de los motivos técnicos. Se ejecuta para
Metrocuadrado, Wasi y Fincaraíz.

Se añaden casos de revisión con cambio, parciales/fallos/bloqueos/pendientes,
success sin evidencia, esquemas históricos incompletos, importes inválidos,
igualdad de precio con cambio de contenido, scope/identidades, generación exacta,
catálogo posterior diferente, snapshot no disponible, caché y temporales eliminados.
La simulación falla si se intenta adquirir lock o cargar la versión vigente.

API y Chromium verifican los mismos contadores, recarga, polling, desktop
1440x900, tablet 768x1024 y móvil 390x844, ausencia de overflow y estados sin
evidencia o con parciales/pendientes. Todo usa bases sintéticas y transporte
interceptado. Evidencia local excluida:
`.tmp/resultados-finales-20261116/informe-69-{1440,768,390}.png`,
`historico-sin-evidencia-{1440,768,390}.png` y `parcial-pendiente-390.png`.
Se inspeccionan las capturas reales de Chromium; no son imágenes generadas.

Resultados de esta tarea, procesos separados y datos aislados:

| Comprobación | Resultado real |
| --- | --- |
| Consola completa | 486 aprobadas, 275,38 s |
| Scraper completo | 171 aprobadas, 143,19 s |
| Catálogo completo | 249 aprobadas, 11,05 s |
| Regresión final de resultados/ejecuciones/generaciones | 87 aprobadas, 33,83 s |
| Archivo nuevo final y capturas | 33 aprobadas, 13,92 s |
| pip check, compileall y git diff --check | Correctos |

Las pruebas específicas son subconjuntos, no se suman como pruebas distintas.
La suite completa de consola corrió antes de la última ampliación de identidad
histórica; el conjunto final de 87 y el archivo nuevo de 33 comprueban ese ajuste.
Única advertencia: deprecación conocida de BlockingPortal en Starlette/AnyIO.
Los fallos iniciales del helper de hash (ruta str/Path) se corrigieron en pruebas;
la comprobación de limpieza detectó y corrigió una conexión SQLite que requería
closing explícito para eliminar el temporal también en Windows.

Se inspeccionaron visualmente desktop y móvil, además de las comprobaciones
Chromium de tablet. Panel recortado al informe: informe-69-panel-{1440,768,390}.png.
Los datos son sintéticos, sin IDs ni contenido de fichas operativas.

## Builds y componentes efectivos

Commit fuente compartido: `680ef8b45a4f1773f8e8ef5c98a4f46241a51809`.
Ambos builds SUCCESS, proyecto radar-inmobiliario-co, us-central1:

| Componente | Build | Horario Bogotá 16/11/2026 |
| --- | --- | --- |
| Job | 3c1f7856-bc3b-47d0-a266-6d0adc5f3bde | 06:21:54–06:23:46 |
| Web | 4e810438-6f21-4816-8fce-e053015984db | 06:21:58–06:23:19 |

Imagen efectiva de radar-manual-review, Ready=True:
`us-central1-docker.pkg.dev/radar-inmobiliario-co/radar/jobs@sha256:cba1da6dc8eab2e4dde7af9b4ec0d303cebf7fff7bfa58df00f0f54e0b3ea7e3`.

Revisión web privada: `radar-resultados-20261116-680ef8b`, Ready=True, 0% de tráfico.
Imagen efectiva en spec y status.imageDigest de la revisión:
`us-central1-docker.pkg.dev/radar-inmobiliario-co/radar/web@sha256:b9681ad636a3b1909199b86057466bcf60dc563a9ceee1471227596c5455933d`.

Los dos digests coinciden entre Cloud Build, Artifact Registry y recursos efectivos.
La identificación del runtime es commit/digest; no se creó un tag Git ni se cambió
la versión visible de la cabecera para identificar estas imágenes.

El Job conserva toda su configuración salvo imagen y nonce generado por Cloud Run.
En web se cambian imagen, metadatos de revisión/source-sha y destino del tag privado.
Se compararon entorno, secretos, identidad, recursos, probes y anotaciones de acceso:
ningún cambio funcional de configuración o IAP. Producción mantiene exactamente
100% en radar-verify-20261111 y la spec de esa revisión es idéntica. Otros Jobs intactos.
No se añadieron permisos, identidades, secretos, Jobs o infraestructura permanente;
solo los dos builds, imágenes, fuente/logs y la revisión web de prueba.

## Verificación privada y conservación

Se utilizó la sesión IAP disponible mediante la habilidad computer-use y la
superficie de navegador de solo lectura. Se abrió únicamente el endpoint existente
`/v0.6/ejecuciones/estado?run=e0cb409c-ee6a-41cb-b4bc-56bc8116cb21` para evitar
refrescar proyecciones operativas del catálogo al comprobar el informe.
No se interactuó con autenticación ni se seleccionaron búsquedas.

La respuesta privada real confirmó:

- status=completed; processed=69; new=1; changed=0; unchanged=68.
- reused=55; reread_unchanged=13.
- report_origin=snapshot y nota explícita de derivación.
- reported.unchanged=55: el control original no se reescribe.
- El HTML del mismo endpoint contiene 1 / 0 / 68, consistente con el JSON.

Después de esa lectura, snapshot y control mantienen exactamente sus generaciones
y MD5 previos. Lista de ejecuciones idéntica antes/después: ninguna nueva captura.
Lock ausente (404); no se retiró ningún bloqueo. No hubo scraping, Gemini o Scheduler.
Esto verifica el cálculo/presentación y la lectura histórica privada, no una nueva
prueba operativa de extracción o persistencia de futuros Jobs.

Evidencia local excluida: `.tmp/resultados-finales-20261116/verification.json`,
metadatos before/after, builds, Registry, logs de suites y capturas sintéticas.
No se publican snapshots operativos ni registros crudos con datos privados.

## Componentes y revisión

Se necesita actualizar web (proyección histórica, HTML y API) y radar-manual-review
(métricas futuras). Ambos se construyen desde un mismo commit limpio del estado
actual, que incluye las dos correcciones operativas. Solo componentes de revisión.
Producción conserva radar-verify-20261111 al 100%; el tag ejecuciones-review es privado
y sin porcentaje de tráfico. No cambia autenticación, identidades o secretos.

Antes de actuar: Job imagen f70659597246158745994c6fe5efd8a33c459166c546b11f837b570e4c28519d;
web privada radar-wasi-overlay-20261113. Snapshot 1794792532218538,
MD5 DRwFJe7timIHEIq62G6vpA==; control 1794792546779732,
MD5 JMyN66USKor5Fz3Lz9VwLQ==. No hay Jobs activos ni lock operativo.

## Revisión manual de presentación

URL estable por IAP:
https://ejecuciones-review---radar-dvhqhy5u3q-uc.a.run.app/v0.6/ejecuciones?run=e0cb409c-ee6a-41cb-b4bc-56bc8116cb21

1. Abrir el enlace, sin iniciar una captura. Debe derivar 69 / 1 / 0 / 68 del
   snapshot de cierre, con 55 reutilizados y 13 releídos dentro de sin cambios.
2. Abrir Conciliación y método y Contadores registrados originalmente. El original
   sigue 1 / 0 / 55 y no se ha reescrito; la nota explica la presentación derivada.
3. Recargar y comprobar las mismas cifras; en móvil las tablas desplazan en su
   contenedor. Las categorías no satisfactorias y pendientes se verifican con
   simulaciones, sin provocar errores o nuevas capturas en datos reales.
4. Consultar /v0.6/ejecuciones/estado?run=ID conserva la misma clasificación final
   en JSON y HTML. Si la evidencia histórica ya no existe, debe indicar N/D o la
   limitación, nunca asegurar sin cambios por recibir success.

La revisión comparte datos, snapshot, control y recursos con producción. Esta
corrección se verifica con datos aislados y lectura histórica; no acredita una
nueva captura operativa de ningún portal. Las pruebas reales posteriores siguen
requiriendo selección manual concreta y no forman parte de esta entrega.

## Reversión

Sin procesos activos, devolver únicamente la imagen de radar-manual-review al
inmutable anterior f70659597246158745994c6fe5efd8a33c459166c546b11f837b570e4c28519d.
Esa imagen conserva Metrocuadrado y Wasi. Reasignar solamente el tag privado
mediante run services update-traffic --update-tags=ejecuciones-review=radar-wasi-overlay-20261113,
indicando proyecto radar-inmobiliario-co y región us-central1, sin tocar porcentajes.
No restaurar control, catálogos o snapshots, ni retirar locks. No existe migración.

Los campos nuevos del control son aditivos: el código anterior ignora los detalles
nuevos y puede seguir leyendo los tres contadores principales. La reversión de web
reintroduce la limitación de informes antiguos sin proyección derivada. No se vuelve
a imágenes anteriores a las correcciones operativas de los portales.


## Archivos y Git

- ejecuciones/resultados.py: clasificación final y conciliación común.
- ejecuciones/informes.py: lectura histórica de versión fija, caché y proyección.
- ejecuciones/worker.py: métricas futuras con el cálculo compartido.
- ejecuciones/servicio.py: exposición de la proyección de solo lectura.
- consola/ejecuciones.py: mismos datos finales para resumen, detalle y API.
- consola/templates/v06/_ejecucion06.html y _resultados06.html: contadores, subconjuntos y límites.
- consola/tests/test_resultados_finales.py: fixtures y pruebas nuevas compartidas.
- RADAR_PROYECTO_RECTOR.md, consola/docs/EJECUCIONES.md, este informe,
  CHANGELOG.md y docs/README.md: definición, evidencia y operación.

Sin cambios en scraper/, catalogo/, oportunidades/, bases o configuración de
extracción. Se verifica diff vacío de todos los scrapers frente a 6c68007.
Rama conservada, sin conflictos. Commit local para build reproducible; sin push,
merge ni tags. El commit documental posterior registra digests y no cambia runtime.


Comandos de reversión (documentados, no ejecutados), tras confirmar que no hay
procesos activos:

```powershell
& ../cloud.ps1 run jobs update radar-manual-review --project=radar-inmobiliario-co --region=us-central1 --image=us-central1-docker.pkg.dev/radar-inmobiliario-co/radar/jobs@sha256:f70659597246158745994c6fe5efd8a33c459166c546b11f837b570e4c28519d --quiet
& ../cloud.ps1 run services update-traffic radar --update-tags=ejecuciones-review=radar-wasi-overlay-20261113 --project=radar-inmobiliario-co --region=us-central1 --quiet
```

Comprobar después Job digest, tag privado y radar-verify-20261111 al 100%.
No restaurar datos ni cambiar porcentajes como sustituto de revertir la revisión.

Cierre: rama conservada, árbol limpio y scrapers sin diferencias frente a la base.
El commit documental posterior no requiere reconstruir imágenes. No hay push,
merge, tags ni conflictos.
