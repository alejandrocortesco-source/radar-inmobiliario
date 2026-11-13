param(
    [Parameter(Mandatory)][string]$WebDigest,
    [Parameter(Mandatory)][string]$JobsDigest,
    [Parameter(Mandatory)][ValidatePattern('^[a-f0-9]{40}$')][string]$SourceSha,
    [string]$RevisionSuffix='ejecuciones-20261113'
)
$ErrorActionPreference='Stop'
foreach($item in @(@('web',$WebDigest),@('jobs',$JobsDigest))) {
    if($item[1] -notmatch "^us-central1-docker.pkg.dev/radar-inmobiliario-co/radar/$($item[0])@sha256:[a-f0-9]{64}$") {throw 'Se requieren digests exactos de Radar'}
}
$cloud=Join-Path $PSScriptRoot '../../cloud.ps1'
$project='radar-inmobiliario-co'
$region='us-central1'
$job='radar-manual-review'
# Crear solo el Job manual nuevo. No ejecutar ni sustituir los tres Jobs anteriores.
& $cloud run jobs create $job --project=$project --region=$region --image=$JobsDigest --service-account=radar-jobs@radar-inmobiliario-co.iam.gserviceaccount.com --tasks=1 --parallelism=1 --max-retries=0 --task-timeout=10800 --cpu=1 --memory=2Gi '--args=--execution,00000000-0000-0000-0000-000000000000' '--set-env-vars=RADAR_STATE_BUCKET=radar-inmobiliario-co-state,RADAR_STATE_OBJECT=radar/state.tar.gz,RADAR_CONTROL_OBJECT=radar/executions/control.json,RADAR_EXECUTION_JOB=radar-manual-review,RADAR_DATA_DIR=/data,PYTHONPATH=/app:/app/scraper,WASI_USER_FILE=/secrets/wasi-user/value,WASI_PASSWORD_FILE=/secrets/wasi-password/value' '--set-secrets=/secrets/wasi-user/value=wasi-user:1,/secrets/wasi-password/value=wasi-password:1' --labels="app=radar,source-sha=$($SourceSha.Substring(0,12))" --quiet
if($LASTEXITCODE -ne 0){throw 'Job manual no creado: revisar antes de reemplazar recursos existentes'}
$roleFile=Join-Path $PSScriptRoot 'manual-job-role.json'
& $cloud iam roles create radarManualExecution --project=$project "--file=$roleFile" --quiet
if($LASTEXITCODE -ne 0){throw 'Rol no creado: revisar antes de reutilizar uno existente'}
& $cloud run jobs add-iam-policy-binding $job --project=$project --region=$region --member=serviceAccount:radar-web@radar-inmobiliario-co.iam.gserviceaccount.com --role=projects/radar-inmobiliario-co/roles/radarManualExecution --quiet
if($LASTEXITCODE -ne 0){throw 'Permiso de ejecución no confirmado'}
# --no-traffic conserva la revisión que atendía producción. No cambia IAP, OAuth, IAM web ni secretos.
$origin='https://ejecuciones-review---radar-dvhqhy5u3q-uc.a.run.app'
& $cloud run services update radar --project=$project --region=$region --image=$WebDigest --revision-suffix=$RevisionSuffix --no-traffic --tag=ejecuciones-review "--update-env-vars=RADAR_PUBLIC_ORIGIN=$origin,RADAR_EXECUTION_JOB=$job,RADAR_CONTROL_OBJECT=radar/executions/control.json" --update-labels="app=radar,source-sha=$($SourceSha.Substring(0,12))" --quiet
if($LASTEXITCODE -ne 0){throw 'Revisión privada no confirmada'}
& $cloud run services describe radar --project=$project --region=$region --format='yaml(status.traffic,status.latestReadyRevisionName)'
if($LASTEXITCODE -ne 0){throw 'No se pudo verificar el tráfico'}
