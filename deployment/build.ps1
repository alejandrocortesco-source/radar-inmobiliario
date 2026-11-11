param([ValidateSet('web','jobs')][string]$Target='web')
$ErrorActionPreference='Stop'
$cloud=Join-Path $PSScriptRoot '../../cloud.ps1'
Push-Location (Join-Path $PSScriptRoot '..')
try {
    $sha=(git rev-parse HEAD).Trim()
    if(git status --porcelain) { throw 'Build reproducible exige árbol limpio' }
    $image="us-central1-docker.pkg.dev/radar-inmobiliario-co/radar/${Target}:$($sha.Substring(0,12))"
    & $cloud builds submit . --config="cloudbuild.$Target.yaml" "--substitutions=_IMAGE=$image,_SOURCE_SHA=$sha" --gcs-source-staging-dir=gs://radar-inmobiliario-co-state/builds/source --region=us-central1 --service-account=projects/radar-inmobiliario-co/serviceAccounts/radar-build@radar-inmobiliario-co.iam.gserviceaccount.com --project=radar-inmobiliario-co --async --format=json
    if($LASTEXITCODE -ne 0){throw 'Build no enviado'}
} finally { Pop-Location }
