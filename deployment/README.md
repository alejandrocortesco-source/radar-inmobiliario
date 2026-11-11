# Operación privada de Cloud Run desde copia independiente

Este directorio pertenece exclusivamente al clon de despliegue. La autorización
actual permite esta rama local, commits locales y Google Cloud; no permite push.
Origen: d84f1dda914b5a211b0e00eef61de1c5b28a2b88 (develop publicado).
Versión funcional: 0.11.0, con correcciones posteriores al tag v0.11.0.

Proyecto único: radar-inmobiliario-co (56106530298). Región elegida: us-central1,
por ausencia de destinos existentes y tarifas/free tier adecuados. No se consulta
ni modifica Mayordomo Gaya. Operador/acceso final: alejandro.cortes.co@gmail.com.

## Persistencia y límites aceptados

consola/cloud.py aplica acceso antes de storage y reutiliza la aplicación actual.
Cada petición dinámica autentica, adquiere el mismo lock GCS que scraper/job.py,
restaura bases locales independientes, ejecuta la petición y sus BackgroundTasks,
confirma el snapshot si hay cambios y solo entonces emite la respuesta retenida.
Las lecturas que escriben novedades también se confirman. Estáticos no requieren
snapshot, pero conservan autenticación. Ningún SQLite activo se monta sobre FUSE.
El máximo de una instancia reduce consumo; la integridad depende del lock y las
precondiciones de generación, incluso entre revisiones e instancias simultáneas.
Si falla storage o hay lock se responde 503, nunca éxito de una escritura local.
Ante respuesta perdida después del commit, consultar antes de repetir un alta.

El usuario aceptó que la web quede ocupada durante Jobs. Las capturas son
manuales, una tarea/paralelismo 1/sin reintentos automáticos, sin Scheduler nuevo.
SIGKILL puede dejar un lock huérfano. Antes de retirar uno: comprobar ausencia de
Jobs activos y operaciones web, conservar la generación, y borrar únicamente ese
objeto lock con --if-generation-match=GENERACION. Nunca borrar state.tar.gz.
RPO de web: operaciones confirmadas en GCS; Job: último checkpoint de 60 segundos.
Un fallo durante una petición no confirmada puede descartar sus cambios locales.

El snapshot conserva metro.sqlite, wasi.sqlite, fincaraiz.sqlite (publicaciones,
anunciantes publicados derivados, historial, runs/checkpoints), metro-consola.sqlite
(clientes, oportunidades, búsquedas, decisiones, matching, novedades, auditoría y
caché Gemini) y proyecciones geográficas existentes. No contiene credenciales.
Se conserva la separación entre catálogo y auxiliar y COP como única moneda.
Guardar/editar búsquedas no ejecuta Jobs. Gemini solo se solicita manualmente;
sus tareas ASGI terminan antes de responder, evitando depender de CPU de fondo.

## Respaldo y restauración

El respaldo inicial está fuera del repo, en ../backups/local-initial-20261111 y
../backups/local-initial-20261111.tar.gz. Su manifiesto contiene hashes, tamaños,
conteos e integrity_check; se copió sin abrir ni escribir en SQLite original,
verificando ausencia de WAL/journal con contenido y hashes antes/después.
Copia nube: gs://radar-inmobiliario-co-state/backups/initial-20261111.tar.gz.
SHA256: 9e5fcd3e4d2f70d7c34cfd49adf3ebec089254c4aad6049dfaf283bd406d0840.
La descarga verificada cloud-backup-verified.tar.gz coincide. El objeto activo es
radar/state.tar.gz; versionado y soft delete permiten recuperación adicional.

Para restaurar datos (distinto de revertir código): bloquear escrituras y Jobs,
guardar snapshot/generación activos, descargar la generación o backup deseados a
un directorio nuevo, verificar SHA e integrity_check, comparar datos que se
perderían y subir al objeto activo con la precondición de su generación actual.
Mantener el respaldo del estado sustituido. No restaurar sobre la fuente local.
Cualquier restauración posterior necesita autorización por su pérdida potencial.

## Construir, actualizar y revertir

Desde el clon limpio, deployment/build.ps1 -Target web (y -Target jobs). El build
usa Cloud Build con cuenta radar-build, fuentes solo en builds/ y registro radar;
no se conecta a GitHub. Registrar commit, ID de build y digest devuelto.
Desplegar con deployment/deploy-web.ps1 -WebDigest IMAGEN@sha256:DIGEST -SourceSha SHA_DEL_BUILD.
Comprobar IAP habilitado, IAM del agente y del usuario, OAuth External para Gmail,
URL/origen exactos, logs, acceso real y persistencia antes de declarar éxito.
No usar --allow-unauthenticated ni otorgar allUsers/allAuthenticatedUsers.

Revertir solo aplicación: gcloud run services update-traffic radar
--to-revisions=REVISION_ANTERIOR=100 --project=radar-inmobiliario-co
--region=us-central1. Conservar imagen/revisión anterior y confirmar compatibilidad
de datos. En primer despliegue no existe una revisión anterior de producción.
El rollback de tráfico no restaura bases; no sustituirlo por restore de datos.

## Costos estimados, sin garantía

Supuestos mensuales bajos: 10 000 peticiones, 2 segundos facturables medios,
1 vCPU/2 GiB; 8 capturas manuales de 30 minutos a 1 vCPU/2 GiB; 100 minutos de
build e2-standard-2; 4 GiB de imágenes; <=5 GiB incluyendo versiones/backups;
<=100 000 operaciones GCS; <=1 GiB de logs con retención 30 días; <=6 versiones
activas de secretos, <=10 000 accesos. Los Jobs no se programan en esta validación.
Web aproximadamente $0.58 antes de free tier. Jobs aproximadamente $0.32 antes de
free tier. Builds $0.60 antes de free tier. Imágenes hasta $0.40, almacenamiento
hasta $0.10 más operaciones (reservar $0.50), secretos hasta $0.36 si no hay cuota
gratuita disponible; logs $0 con la franquicia. Reservar hasta $1 de salida de red.
Estimación conjunta de infraestructura baja: alrededor de $1–5/mes, sin Gemini,
impuestos ni extracciones muy largas; depende de franquicias compartidas y uso.
Gemini manual consume saldo aparte. Gasto anterior no equivale a costo del deploy.
Una alerta de presupuesto avisa; no limita automáticamente gasto ni detiene Jobs.

Precios oficiales consultados el 11 de noviembre de 2026:
- https://cloud.google.com/run/pricing
- https://cloud.google.com/storage/pricing
- https://cloud.google.com/build/pricing
- https://cloud.google.com/artifact-registry/pricing
- https://cloud.google.com/secret-manager/pricing
- https://cloud.google.com/products/observability/pricing
- https://cloud.google.com/scheduler/pricing
- IAP directo y Gmail externo: https://docs.cloud.google.com/run/docs/securing/identity-aware-proxy-cloud-run

Resultados reales, recursos finales, digest, revisión, pruebas manuales y
pendientes se documentan en el informe externo ../evidence/ENTREGA.md.

## Estado operativo del 11 de noviembre

La cuenta de facturación usa COP. Se creó una única alerta de COP 30.000, con
umbrales 50%, 80%, 100% y previsión 100%, limitada al proyecto 56106530298.
Es una alerta conservadora (aprox. USD 9,10 con TRM Banrep 3.297,07 del 11/11),
no un límite automático ni conversión monetaria dentro de Radar.
Fuente TRM: https://www.banrep.gov.co/es . Retención _Default: 30 días.

Los builds iniciales del commit 1e193e653ed8e50563e5ddc80782e6251aaa5540
terminaron SUCCESS. Web: sha256:891c3d3b6c926ea36cd49c8a06bb9a1da713d420237032369586dfb7109c7bfa.
Jobs: sha256:cfd53b5faaff8ea0a1311b4ded15757d89a23d7e42dca780a20436960363a373.
Los ajustes posteriores de scripts operativos no alteran esos contenedores.
El health check exige entrecomillar la lista de campos al llamar gcloud desde
PowerShell; deployment/deploy-web.ps1 conserva la corrección reproducible.

Jobs creados: radar-metro, radar-wasi, radar-fincaraiz y radar-state-check.
Solo se ejecutó radar-state-check: integridad de las cinco bases y Chromium OK,
con scraping=false y gemini=false. Wasi ya tiene wasi-user:1 y wasi-password:1 montados por separado; el secreto
wasi-token preexistente se conserva sin cambios. No se ejecutó login ni captura.
No se activa Scheduler. La API Scheduler no estaba habilitada inicialmente.

## Validación final completada

URL privada https://radar-56106530298.us-central1.run.app/v0.6/ con acceso real
verificado para alejandro.cortes.co@gmail.com. OAuth externo permanece en Prueba,
un solo usuario de prueba, con cliente creado automáticamente en Google/IAP.
El secreto OAuth permanece allí y no se exportó al repo, imagen ni informes.
IAP tiene únicamente esa cuenta; Run Invoker únicamente el agente de IAP.
Las dos URLs run.app devolvieron 302 a Google en 16 comprobaciones sin sesión,
incluyendo health, páginas, API, estáticos y las dos rutas CSV.

Revisión actual: radar-verify-20261111, 100% tráfico; conserva radar-00001-69p.
Mismo digest web del commit runtime 1e193e653ed8e50563e5ddc80782e6251aaa5540.
El reemplazo cambió solo RADAR_VALIDATION_REV, conservando imagen y datos.
Cliente creado por web, matching manual 469, recuperado desde nueva revisión,
API y Job radar-state-check-fbl5d. La limpieza radar-state-check-h96b6 eliminó
exclusivamente su UUID/marcador y relaciones. Se eliminó también la búsqueda
sintética después de registrar y editar su nombre en el control existente.
La auditoría final comprobó iguales todas las tablas originales (45 en total)
y ninguna solicitud Gemini ni ejecución de scraper nueva. No quedan registros
sintéticos de esta validación. Los nuevos esquemas auxiliares son aditivos.

Wasi: Secret Manager wasi-user:1 y wasi-password:1, Secret Accessor solo radar-jobs,
montados en /secrets/wasi-user/value y /secrets/wasi-password/value. No se ejecutó
scraping, login real ni programación; esa validación operativa sigue pendiente.
Se conservan los archivos privados fuente fuera del clon y del repo original.

CSV autenticado: Cloud Run confirmó HTTP 200, 240901 bytes, 8.735 s. La espera de
archivo de la herramienta de navegador se bloqueó; no se usó ese evento como
prueba de éxito. Evidencia independiente: logs HTTP y acceso sin sesión rechazado.
El archivo descargado no se inspeccionó localmente en esta validación.

Al actualizar Jobs existentes usar run jobs update NOMBRE --image=DIGEST con
--project=radar-inmobiliario-co --region=us-central1; conservar identidad, entorno,
montajes, tareas y paralelismo. deploy-jobs.ps1 es creación inicial y falla ante
nombres existentes. configure-wasi.ps1 también evita reemplazar secretos existentes.
El script web exige SourceSha explícito del build para no atribuir a una imagen
anterior los commits posteriores de scripts/documentación.
