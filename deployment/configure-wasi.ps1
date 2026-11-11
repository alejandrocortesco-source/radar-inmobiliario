# Ejecutar tras aprobar acceso de radar-jobs a estos dos secretos exactos.
$ErrorActionPreference='Stop'
$cloud=Join-Path $PSScriptRoot '../../cloud.ps1'
$project='radar-inmobiliario-co'
foreach($entry in @(@('wasi-user','Usuario.txt'),@('wasi-password','Password.txt'))) {
    $secret=$entry[0]
    $inputFile=Join-Path 'C:/Users/Palex25/Documents/Boch-Lab/Acceso Wasi' $entry[1]
    & $cloud secrets describe $secret --project=$project --format='value(name)' 2>$null
    if($LASTEXITCODE -eq 0){throw 'Secreto ya existe; revisar versión antes de sustituir'}
    & $cloud secrets create $secret --replication-policy=automatic --data-file=$inputFile --project=$project --format='value(name)'
    if($LASTEXITCODE -ne 0){throw 'Secreto no creado'}
    & $cloud secrets add-iam-policy-binding $secret --member=serviceAccount:radar-jobs@radar-inmobiliario-co.iam.gserviceaccount.com --role=roles/secretmanager.secretAccessor --project=$project --format='value(etag)'
    if($LASTEXITCODE -ne 0){throw 'Acceso a secreto no confirmado'}
}
& $cloud run jobs update radar-wasi --region=us-central1 --project=$project '--set-secrets=/secrets/wasi-user/value=wasi-user:1,/secrets/wasi-password/value=wasi-password:1' '--update-env-vars=WASI_USER_FILE=/secrets/wasi-user/value,WASI_PASSWORD_FILE=/secrets/wasi-password/value' --quiet
if($LASTEXITCODE -ne 0){throw 'Job Wasi no configurado'}
# No ejecutar el Job ni iniciar sesión durante el despliegue.
