# Aplicar únicamente tras la aprobación específica del operador.
$ErrorActionPreference = 'Stop'
$cloud = Join-Path $PSScriptRoot '../../cloud.ps1'
$project = 'radar-inmobiliario-co'
$region = 'us-central1'
function Cloud { & $cloud @args; if ($LASTEXITCODE -ne 0) { throw 'Falló una operación de Google Cloud' } }

# Build: escribir únicamente imágenes en el repositorio radar y logs en Radar.
Cloud artifacts repositories add-iam-policy-binding radar --location=$region --member=serviceAccount:radar-build@radar-inmobiliario-co.iam.gserviceaccount.com --role=roles/artifactregistry.writer --project=$project --format='value(etag)'
Cloud projects add-iam-policy-binding $project --member=serviceAccount:radar-build@radar-inmobiliario-co.iam.gserviceaccount.com --role=roles/logging.logWriter --project=$project --format='value(etag)'
# El build solo lee sus fuentes; no puede leer snapshots ni backups.
Cloud storage buckets add-iam-policy-binding gs://radar-inmobiliario-co-state --member=serviceAccount:radar-build@radar-inmobiliario-co.iam.gserviceaccount.com --role=roles/storage.objectViewer --condition="expression=resource.name.startsWith('projects/_/buckets/radar-inmobiliario-co-state/objects/builds/'),title=radar-build-sources" --project=$project --format='value(etag)'
# Web y Jobs comparten solo el estado activo y su bloqueo, no backups ni builds.
foreach ($identity in @('radar-web','radar-jobs')) {
    Cloud storage buckets add-iam-policy-binding gs://radar-inmobiliario-co-state --member="serviceAccount:$identity@$project.iam.gserviceaccount.com" --role=roles/storage.objectUser --condition="expression=resource.name.startsWith('projects/_/buckets/radar-inmobiliario-co-state/objects/radar/'),title=radar-runtime-state" --project=$project --format='value(etag)'
}
Cloud secrets add-iam-policy-binding gemini-api-key --member=serviceAccount:radar-web@radar-inmobiliario-co.iam.gserviceaccount.com --role=roles/secretmanager.secretAccessor --project=$project --format='value(etag)'
# Tras existir el servicio radar: solo el agente IAP puede invocar el contenedor.
# Cloud run services add-iam-policy-binding radar --region=$region --member=serviceAccount:service-56106530298@gcp-sa-iap.iam.gserviceaccount.com --role=roles/run.invoker --project=$project
# El usuario final alejandro.cortes.co@gmail.com tendrá únicamente roles/iap.httpsResourceAccessor sobre ese servicio.
# No se concederá acceso a Mónica, allUsers, allAuthenticatedUsers ni otros proyectos.
