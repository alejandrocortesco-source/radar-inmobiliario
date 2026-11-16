# Validación aislada v0.14.1

Preserva v0.14.0/be020d6. No modificar producción, publicar ni activar Scheduler.

## Diferencias mínimas

`ejecuciones.entorno.settings` centraliza proyecto/región e identidad OIDC del
coordinador. Nombres radar-manual-review y radar-weekly-review se pueden repetir
en otro proyecto; los parents completos antes fijos sí eran productivos.
El perfil production conserva sus defaults y exige IAP en la web.
El perfil isolated rechaza configuración incompleta antes de crear clientes GCS/API.
Exige proyecto radar-test-*, bucket propio, número distinto de producción, URLs
canónicas propias, cuentas propias y RADAR_SYNTHETIC_DATA=1. La web isolated exige
OIDC Google firmado para RADAR_WEB_CALLER; POST conserva Origin exacto.
El trabajador isolated rechaza invocaciones sin --execution; el adaptador sustituye
solo los datos de entrada y permite éxito/error sintético sin portales ni Chromium.

La validación real detectó que una generación GCS puede desaparecer entre reload y
la descarga fijada a esa generación. ControlGCS.read reintenta 404/412 de la descarga
hasta ocho veces y después falla cerrado; solo 404 de metadatos significa objeto
ausente. No se cambia la exclusión mutua ni la escritura CAS.

## Recursos y límites

Proyecto sin organización/padre; bucket propio con soft delete deshabilitado,
Artifact Registry, dos servicios privados min0/max1 CPU1/mem512Mi/concurrency1,
un Job CPU1/mem1Gi tasks1/parallelism1/retries0/timeout120s, cuentas dedicadas,
secreto ficticio. Ningún Scheduler. Región us-central1. Builder dedicado sin Editor.
Runtime: objectAdmin solo bucket sintético, secretAccessor solo secreto ficticio;
web/dispatcher: get de Scheduler en proyecto temporal y ejecución solo Job temporal.
No conceder permisos en producción. Auditar ancestors, IAM y testIamPermissions
con credenciales impersonadas: positivas en bucket propio, negativas en productivo.

## Reproducción y aceptación

1. Revisar git, ejecutar pruebas sintéticas, commit local y tag nuevo. Preparar tar
   con deployment/prepare_release.py, registrar SHA de commit y source_tree.
2. Cloud Build en proyecto temporal, SA builder, staging propio; configuraciones
   cloudbuild.web.yaml/cloudbuild.jobs.yaml. Registrar build IDs y digests; desplegar
   solo esos digests. No utilizar scripts bootstrap de producción.
3. Configurar RADAR_ENV=isolated y todas las variables de entorno requeridas por
   settings, RADAR_AUTH_MODE=oidc. Secret ficticio sin credenciales de portales.
   Registrar como custom audience en cada servicio únicamente su URL canónica
   RADAR_PUBLIC_ORIGIN/RADAR_SCHEDULE_TARGET: `run services update NOMBRE
   --add-custom-audiences=URL --project=TEMPORAL --region=us-central1`.
   Cloud Run usa también una URL con hash como audiencia por defecto; no asumir que
   acepta automáticamente la URL basada en número de proyecto.
4. Sembrar snapshot sintético con búsquedas de tres fuentes. Llamar web autenticada
   usando token Google OIDC con audience URL web y Origin exacto. Authorization y
   X-Serverless-Authorization conservan token firmado para aplicación y plataforma.
5. Manual web → API Run → Job → resultado GCS. Repetir request_id, comprobar una
   ejecución. Pulso manual firmado → dispatcher → mismo Job. Ninguna recurrencia.
   Error sintético debe conservar registro y liberar lock; reiniciar web y releer.
6. Migrar control temporal; crear registros y cliente después; rollback_legacy con
   revisión actual. Comparar runs/receipts/archivos y snapshot antes/después. Jamás
   restaurar snapshot/control antiguos. El rollback productivo sigue RELEASE_014.md.
7. Medir invocaciones idle/work, tiempos y recursos; proyectar 43.200 pulsos por mes,
   CPU/mem/requests y operaciones GCS. No equiparar latencia HTTP a costo facturado.
8. Exportar evidencias locales; eliminar servicios, Job, registry, bucket, secretos,
   cuentas y proyecto temporal. Comprobar DELETE_REQUESTED; documentar retenciones.

Estimación previa: menos de US$1 para dos builds de hasta 20min (e2-standard-2,
US$0,006/min), pruebas acotadas y almacenamiento temporal; límite autorizado US$3.
No existe tope técnico de facturación instantáneo. Precios sin asumir free tier.
Fuentes: https://cloud.google.com/build/pricing, https://cloud.google.com/run/pricing,
https://cloud.google.com/storage/pricing. Evidencia final se entrega por separado.
