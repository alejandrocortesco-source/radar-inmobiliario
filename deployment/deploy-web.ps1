param(
    [Parameter(Mandatory)][string]$WebDigest,
    [Parameter(Mandatory)][ValidatePattern('^[a-f0-9]{40}$')][string]$SourceSha,
    [Parameter(Mandatory)][ValidatePattern('^[a-f0-9]{64}$')][string]$SourceTree,
    [Parameter(Mandatory)][ValidatePattern('^[a-z0-9-]+$')][string]$RevisionSuffix,
    [ValidateSet('Private','Public')][string]$Mode='Private',
    [switch]$PlanOnly
)
$ErrorActionPreference='Stop'
if($WebDigest -notmatch '^us-central1-docker.pkg.dev/radar-inmobiliario-co/radar/web@sha256:[a-f0-9]{64}$'){throw 'Digest web exacto obligatorio'}
$origin=if($Mode -eq 'Private'){'https://ejecuciones-review---radar-dvhqhy5u3q-uc.a.run.app'}else{'https://radar-56106530298.us-central1.run.app'}
# Actualizar conserva todas las demás variables y referencias a secretos.
$envVars="RADAR_AUTH_MODE=iap,RADAR_IAP_AUDIENCE=/projects/56106530298/locations/us-central1/services/radar,RADAR_PUBLIC_ORIGIN=$origin,RADAR_STATE_BUCKET=radar-inmobiliario-co-state,RADAR_STATE_OBJECT=radar/state.tar.gz,RADAR_CONTROL_OBJECT=radar/executions/control.json,RADAR_EXECUTION_JOB=radar-manual-review,RADAR_SCHEDULE_TARGET=https://radar-schedule-review-56106530298.us-central1.run.app,RADAR_DATA_DIR=/data"
$cloud=Join-Path $PSScriptRoot '../../cloud.ps1'
$cloudArgs=@('run','services','update','radar','--project=radar-inmobiliario-co','--region=us-central1',"--image=$WebDigest", "--revision-suffix=$RevisionSuffix",'--no-traffic',"--update-env-vars=$envVars", "--update-labels=app=radar,source-sha=$($SourceSha.Substring(0,12)),source-tree=$($SourceTree.Substring(0,40))",'--quiet')
if($Mode -eq 'Private'){$cloudArgs+='--tag=ejecuciones-review'}
# No se promociona tráfico, modifica IAM, secretos ni Scheduler.
if($PlanOnly){$cloudArgs | ConvertTo-Json; return}
& $cloud @cloudArgs
if($LASTEXITCODE -ne 0){throw 'Revisión web no confirmada'}
