param(
    [Parameter(Mandatory)][string]$WebDigest,
    [Parameter(Mandatory)][string]$JobsDigest,
    [Parameter(Mandatory)][ValidatePattern('^[a-f0-9]{40}$')][string]$SourceSha,
    [Parameter(Mandatory)][string]$RevisionSuffix
)
$ErrorActionPreference='Stop'
$cloud=Join-Path $PSScriptRoot '../../cloud.ps1'
$project='radar-inmobiliario-co'
$region='us-central1'
foreach($item in @(@('web',$WebDigest),@('jobs',$JobsDigest))) {
    if($item[1] -notmatch "^us-central1-docker.pkg.dev/radar-inmobiliario-co/radar/$($item[0])@sha256:[a-f0-9]{64}$") {throw 'Se requieren digests exactos de Radar'}
}
function Invoke-RadarCloud {
    & $cloud @args
    if($LASTEXITCODE -ne 0){throw "Falló una operación Cloud; inspeccionar antes de continuar: $($args[0..2] -join ' ')"}
}
# API únicamente. No crea un calendario: state PAUSED es output-only en CreateJob.
Invoke-RadarCloud services enable cloudscheduler.googleapis.com --project=$project --quiet
foreach($account in @('radar-scheduler','radar-schedule-dispatch')) {
    & $cloud iam service-accounts describe "$account@$project.iam.gserviceaccount.com" --project=$project --format='value(email)' 2>$null
    if($LASTEXITCODE -ne 0) { Invoke-RadarCloud iam service-accounts create $account --project=$project --display-name=$account --quiet }
}
foreach($role in @(@('radarScheduleManager','schedule-manager-role.json'),@('radarScheduleStorage','schedule-storage-role.json'))) {
    $rolePath=Join-Path $PSScriptRoot $role[1]
    & $cloud iam roles describe $role[0] --project=$project --format='value(name)' 2>$null
    if($LASTEXITCODE -eq 0) { Invoke-RadarCloud iam roles update $role[0] --project=$project "--file=$rolePath" --quiet }
    else { Invoke-RadarCloud iam roles create $role[0] --project=$project "--file=$rolePath" --quiet }
}
Invoke-RadarCloud projects add-iam-policy-binding $project --member="serviceAccount:radar-web@$project.iam.gserviceaccount.com" --role="projects/$project/roles/radarScheduleManager" --condition=None --quiet
Invoke-RadarCloud iam service-accounts add-iam-policy-binding "radar-scheduler@$project.iam.gserviceaccount.com" --project=$project --member="serviceAccount:radar-web@$project.iam.gserviceaccount.com" --role=roles/iam.serviceAccountUser --quiet
# El disparador solo lee/escribe control y consulta/recupera el lock exacto. No lee el snapshot.
$dispatch="serviceAccount:radar-schedule-dispatch@$project.iam.gserviceaccount.com"
$base="projects/_/buckets/$project-state/objects/"
$controlCondition="expression=resource.name == '${base}radar/executions/control.json' || resource.name == '${base}radar/state.tar.gz.lock',title=radar-schedule-control"
Invoke-RadarCloud storage buckets add-iam-policy-binding "gs://$project-state" --member=$dispatch --role="projects/$project/roles/radarScheduleStorage" "--condition=$controlCondition" --quiet
Invoke-RadarCloud run jobs add-iam-policy-binding radar-manual-review --project=$project --region=$region --member=$dispatch --role="projects/$project/roles/radarManualExecution" --quiet
# Sin secretos ni sesiones de portales, min-instances=0 y CPU bajo demanda.
$target='https://radar-schedule-review-56106530298.us-central1.run.app'
$envVars="RADAR_STATE_BUCKET=$project-state,RADAR_STATE_OBJECT=radar/state.tar.gz,RADAR_CONTROL_OBJECT=radar/executions/control.json,RADAR_EXECUTION_JOB=radar-manual-review,RADAR_SCHEDULE_TARGET=$target,RADAR_DATA_DIR=/data"
Invoke-RadarCloud run deploy radar-schedule-review --project=$project --region=$region --image=$WebDigest --service-account="radar-schedule-dispatch@$project.iam.gserviceaccount.com" --no-allow-unauthenticated --ingress=internal --min-instances=0 --max-instances=1 --cpu=1 --memory=512Mi --concurrency=4 --timeout=120 --no-cpu-boost --command=python '--args=-m,uvicorn,ejecuciones.disparador:app,--host,0.0.0.0,--port,8080,--no-access-log' "--set-env-vars=$envVars" --labels="app=radar,source-sha=$($SourceSha.Substring(0,12))" --quiet
Invoke-RadarCloud run services add-iam-policy-binding radar-schedule-review --project=$project --region=$region --member="serviceAccount:radar-scheduler@$project.iam.gserviceaccount.com" --role=roles/run.invoker --quiet
# Nunca ejecutar el Job, ni tocar porcentajes/IAP/identidades de la web existente.
Invoke-RadarCloud run jobs update radar-manual-review --project=$project --region=$region --image=$JobsDigest --quiet
Invoke-RadarCloud run services update radar --project=$project --region=$region --image=$WebDigest --revision-suffix=$RevisionSuffix --no-traffic --tag=ejecuciones-review "--update-env-vars=RADAR_SCHEDULE_TARGET=$target" --update-labels="source-sha=$($SourceSha.Substring(0,12))" --quiet
Invoke-RadarCloud scheduler jobs list --project=$project --location=$region --format='table(name,state)'
Invoke-RadarCloud run services describe radar --project=$project --region=$region --format='yaml(status.traffic,status.latestReadyRevisionName)'
