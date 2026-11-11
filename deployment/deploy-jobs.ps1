param([Parameter(Mandatory)][string]$JobsDigest)
$ErrorActionPreference='Stop'
if($JobsDigest -notmatch '^us-central1-docker.pkg.dev/radar-inmobiliario-co/radar/jobs@sha256:[a-f0-9]{64}$'){throw 'Digest Jobs exacto obligatorio'}
$cloud=Join-Path $PSScriptRoot '../../cloud.ps1'
foreach($entry in @(@('radar-metro','metrocuadrado'),@('radar-wasi','wasi'),@('radar-fincaraiz','fincaraiz'))) {
    & $cloud run jobs create $entry[0] --image=$JobsDigest --region=us-central1 --project=radar-inmobiliario-co --service-account=radar-jobs@radar-inmobiliario-co.iam.gserviceaccount.com --tasks=1 --parallelism=1 --max-retries=0 --task-timeout=3600 --cpu=1 --memory=2Gi "--args=--source,$($entry[1])" '--set-env-vars=RADAR_STATE_BUCKET=radar-inmobiliario-co-state,RADAR_STATE_OBJECT=radar/state.tar.gz,RADAR_DATA_DIR=/data,PYTHONPATH=/app:/app/scraper' --labels=app=radar --quiet
    if($LASTEXITCODE -ne 0){throw 'Job no creado; no sustituir uno existente sin revisarlo'}
}
& $cloud run jobs create radar-state-check --image=$JobsDigest --region=us-central1 --project=radar-inmobiliario-co --service-account=radar-jobs@radar-inmobiliario-co.iam.gserviceaccount.com --tasks=1 --parallelism=1 --max-retries=0 --task-timeout=300 --cpu=1 --memory=2Gi --command=python '--args=deployment/state_probe.py,--browser' '--set-env-vars=RADAR_STATE_BUCKET=radar-inmobiliario-co-state,RADAR_STATE_OBJECT=radar/state.tar.gz,RADAR_DATA_DIR=/data,PYTHONPATH=/app:/app/scraper' --labels=app=radar --quiet
if($LASTEXITCODE -ne 0){throw 'Job de comprobación no creado'}
