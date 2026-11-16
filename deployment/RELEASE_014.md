# Corte y reversión 0.14.0 — procedimiento pendiente de autorización

Esta guía no autoriza comandos productivos. El candidato incluye programación
múltiple, selector de tres portales y UI Carbon. HEAD sigue 7283bc4; el contenido
local se identifica adicionalmente mediante SHA-256 del árbol y un tar verificado.
No atribuir la imagen únicamente al commit base. No hacer commit/push/tag implícitos.

## Barrera y compatibilidad

ControlGCS 0.14 lee versiones 1 y 2. La primera escritura de programación múltiple
rechaza la conversión si queda un trabajador activo y mueve el control a versión 2 dentro del mismo CAS que reserva pending. El binario
0.13.1 real solo acepta versión 1 y rechaza leer/escribir 2. Una escritura antigua
que ya había leído 1 falla por generación y al reintentar encuentra la barrera 2.
El adaptador nuevo también rechaza propuestas antiguas con desired sin modo
multiple antes de confirmar pending: no toca Scheduler. Se preservan las bases,
búsquedas, ejecuciones y recibos. No convertir top.version manualmente.

## Preparación local, sin Cloud

Desde el clon, ejecutar:

```powershell
.\.venv\Scripts\python.exe deployment/prepare_release.py
```

La salida devuelve package, source_tree, base_commit y versión 0.14.0. El paquete
incluye todos los archivos versionados y nuevos no ignorados, RELEASE.json con
huellas individuales y metadatos tar normalizados; dos preparaciones sin cambios
son byte a byte iguales. No incluye .tmp, .local ni datos ignorados. verify() rechaza
contenido alterado. No editar archivos después de fijar esa huella: producir un
nuevo paquete y repetir validación si cambian. Las imágenes deben llevar el
source_tree completo como etiqueta OCI; las labels Cloud Run usan un prefijo.

No se construyen imágenes ni se publica nada al preparar el tar.

## Construcción futura (requiere autorización de consumo/build)

Usar exclusivamente el source.tar congelado, no el directorio de trabajo vivo.
Cloud Build permite --source con archivo tar local. Ejecutar por separado para web
y jobs, usando sus cloudbuild.*.yaml y sustituciones _SOURCE_SHA=base_commit,
_SOURCE_TREE=source_tree y _IMAGE=etiqueta única de candidato. Tras SUCCESS obtener
digests inmutables, cotejar etiquetas OCI/manifest y probar ambas imágenes con SDK
simulados y datos aislados. No declarar validación de imagen por haber aprobado
pytest en Windows. No se dispone de Docker/Podman local en este entorno.

### Plantilla exacta de construcción, NO ejecutada aquí

Primero revisar/autorización de consumo; estas líneas publican imágenes, no son
parte de la revisión local. Sustituir SOURCE_TAR por el paquete aprobado y comprobar
que ambos cloudbuild.*.yaml coinciden con sus SHA-256 en RELEASE.json.

```powershell
$manifest = Get-Content RUTA_MANIFEST_JSON -Raw | ConvertFrom-Json
$tree = $manifest.source_tree
$baseSha = $manifest.base_commit
$sourceTar = 'SOURCE_TAR_APROBADO'
foreach ($kind in @('web','jobs')) {
    $config = "cloudbuild.$kind.yaml"
    $expectedHash = $manifest.files.$config
    if ((Get-FileHash -LiteralPath $config -Algorithm SHA256).Hash.ToLower() -ne $expectedHash) { throw 'Config distinta del paquete' }
    $imageTag = "us-central1-docker.pkg.dev/radar-inmobiliario-co/radar/${kind}:candidate-014-$($tree.Substring(0,16))"
    & ../cloud.ps1 builds submit $sourceTar --project=radar-inmobiliario-co --region=us-central1 --config=$config "--substitutions=_SOURCE_SHA=$baseSha,_SOURCE_TREE=$tree,_IMAGE=$imageTag"
    if ($LASTEXITCODE -ne 0) { throw 'Build no confirmado; detener corte' }
}
```

Conservar outputs de builds y resolver DIGEST_WEB/DIGEST_JOBS efectivos, nunca
pasar las etiquetas mutables a deploy-web. Antes de promover, contrastar la etiqueta
OCI org.opencontainers.image.source-tree con $tree en ambas imágenes.

Comandos de actualización del trabajador/disparador (solo en la ventana autorizada,
tras comprobar pausa y ausencia de trabajos):

```powershell
& ../cloud.ps1 run jobs update radar-manual-review --project=radar-inmobiliario-co --region=us-central1 --image=DIGEST_JOBS
& ../cloud.ps1 run services update radar-schedule-review --project=radar-inmobiliario-co --region=us-central1 --image=DIGEST_WEB
```

La promoción, cuando se autorice, se hace solo a la revisión Public confirmada:

```powershell
& ../cloud.ps1 run services update-traffic radar --project=radar-inmobiliario-co --region=us-central1 --to-revisions=REVISION_PUBLIC_CONFIRMADA=100
```

Para revertir tráfico usar el mismo comando con radar-verify-20261111=100, después
de completar la reversión lógica que corresponda. No restaurar el tag privado a
un escritor antiguo hasta que control.version vuelva a 1. Las imágenes de Job y
disparador se restauran con los comandos update anteriores y los digests previos
verificados del informe predeploy; las variables y secretos no se sustituyen.

## Corte futuro, sin captura ni reactivación

1. Obtener autorización expresa para la ventana. Guardar configuraciones efectivas,
   digests, porcentajes/tags y generaciones de control/snapshot. Releer que no hay
   trabajadores. Pausar el calendario por el mecanismo existente y confirmar gate
   y Scheduler PAUSED; no borrar el recurso ni lanzar Jobs. Guardar este punto como
   referencia lógica de reversión. La pausa modifica producción: NO ejecutada aquí.
2. Actualizar imagen del Job radar-manual-review mediante jobs update --image con
   digest exacto; conservar secrets, identidad, taskCount=1, parallelism=1 y
   maxRetries=0. Nunca ejecutar el Job como smoke test.
3. Actualizar solo imagen del disparador radar-schedule-review; conservar comando
   uvicorn ejecuciones.disparador:app, OIDC, ingress internal, identidad, entorno,
   IAM, timeout y recursos existentes. No usar el antiguo bootstrap, ahora bloqueado.
4. Preparar la revisión privada con el script corregido, inicialmente en PlanOnly:

```powershell
./deployment/deploy-web.ps1 -WebDigest DIGEST_WEB -SourceSha COMMIT_BASE -SourceTree HUELLA_64 -RevisionSuffix candidato-014-private -Mode Private -PlanOnly
```

   Revisar el JSON de argumentos. Solo tras aprobación repetir sin PlanOnly. El
   script actualiza y conserva variables/secretos desconocidos, añade los destinos
   requeridos, no asigna tráfico general ni cambia IAP, IAM o Scheduler. El tag
   ejecuciones-review pasa al código compatible; retirar cualquier otro tag de
   edición antiguo. Conservar su información para rollback. Ninguna edición en la
   revisión de producción se usa como prueba: su bucket está compartido.
5. Preparar otra revisión con -Mode Public y sufijo candidato-014-public, también
   sin tráfico. RADAR_PUBLIC_ORIGIN es el dominio productivo canónico. No promover
   la revisión privada: su Origin es deliberadamente distinto. No ampliar la lista
   de orígenes ni desactivar IAP/Origin. Verificar por describe env, secrets refs,
   digests y estado Ready; smoke de /health, sin acciones de negocio.
6. Cuando todos los escritores sean compatibles y estén cerrados los accesos de
   edición antiguos, migrar mediante operación explícita mientras el calendario
   está pausado. Guardar una programación pausada no debe iniciar una captura;
   comprobar versión 2, selección y recibos. Mantener Scheduler PAUSED. La prueba
   funcional completa se hace antes sobre servicios simulados, no en el bucket real.
7. Solo con autorización de promoción actualizar tráfico a la revisión pública por
   nombre exacto (no latest); verificar el origen canónico. No reactivar horarios.
   Cualquier reactivación automática requiere una autorización posterior separada.

## Rollback exacto

Conservar los digests anteriores del informe predeploy. Antes de bajar de versión:

1. Cerrar editores, mantener Scheduler y gate pausados y confirmar cero trabajos.
2. Si no hubo migración, restaurar imágenes/tráfico/tags/env específicos anteriores
   sin restaurar datos. Mantener la pausa: no recuperar enabled=true de un backup.
3. Si existe versión 2, usar rollback_legacy(control, scheduler, expected_revision)
   del código 0.14, con la revisión recién consultada. Este es el único descenso
   permitido; no editar JSON ni hacer cp de un control viejo. Ejemplo operativo
   (NO ejecutar sin autorización, requiere entorno/ADC del operador configurados):

```python
from ejecuciones.control import ControlGCS
from ejecuciones.scheduler import Scheduler
from ejecuciones.transicion import rollback_legacy
rollback_legacy(ControlGCS(), Scheduler(), 'REVISION_VERIFICADA')
```

   Primero reserva gate pending con CAS, verifica la pausa y cron legado a través
   de Scheduler.sync, y luego confirma formato 1. Archiva toda la colección múltiple
   en schedules_archives; conserva todos los runs, recibos, auditoría, búsquedas y
   campos posteriores. No toca snapshots ni SQLite. No aplica retención durante la
   transición; si excede 2 MB aborta sin borrar historial. Si falla Scheduler o CAS,
   conserva gate cerrado en 2. Tras 90 s y con revisión correcta se permite retry
   explícito; no existe recuperador que active por su cuenta. Si aparece un trabajo
   antes del finish, aborta el descenso y espera su cierre.
4. Confirmar versión 1 y enabled=false antes de restaurar imágenes 0.13.1 del
   disparador/trabajador o volver a habilitar un editor antiguo. Restaurar tráfico
   y tags con sus valores originales y su Origin específico. Ningún paso reactiva
   Scheduler ni ejecuta Jobs. Nunca restaurar todo el snapshot: se perderían altas
   y cambios comerciales posteriores.
5. Tras rollback, la colección está archivada y no se ejecuta. La UI antigua ofrece
   el calendario legado pausado. La recuperación de los horarios múltiples requiere
   una operación futura revisada desde el archivo, no una activación implícita.

## Criterios de autorización

Las simulaciones de contratos y regresiones deben aprobar. Además hacen falta
imágenes exactas construidas/probadas y revisar el plan contra la configuración
vigente de la ventana. Sin esos artefactos no hay GO productivo, aunque el código
esté validado localmente. El pulso central por minuto aumenta solicitudes/lecturas;
la operación desatendida y su costo real siguen sin medirse. No hay recursos nuevos
ni ampliación IAM prevista. Cambios de infraestructura detectados en la ventana
obligan a revisar el plan, no a aplicar defaults de bootstrap.
