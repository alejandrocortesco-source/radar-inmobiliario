# Entrega de Ejecuciones — 13 de noviembre de 2026

Implementada v0.12.0 y disponible en una revisión privada de prueba:

https://ejecuciones-review---radar-dvhqhy5u3q-uc.a.run.app/v0.6/ejecuciones

Revisión final: **radar-ejecuciones-20261113-b**, 0% del tráfico de producción.
**radar-verify-20261111 conserva el 100%**. Acceso IAP comprobado con la cuenta
original autorizada de Alejandro, sin probar la segunda cuenta ni cambiar OAuth/IAP.

## Funcionalidad y decisiones

- Página integrada en la navegación, con diseño de Inicio y sus cuatro secciones conservadas.
- Búsquedas de las tres fuentes por sus IDs existentes; selección individual/todas activas,
  nombres, URL/criterios con etiquetas, estado, últimos resultados técnicos y carga medida.
- Guardar/editar no captura. Validación de selección en servidor y de nuevo en el Job.
- Reserva UUID/idempotencia por CAS; Job durable, un scraper y una búsqueda a la vez.
- Sin procesos de scraping en HTTP, cola adicional, Scheduler ni Gemini.
- Registro GCS separado del snapshot: progreso/historial consultables durante el bloqueo.
- Reconciliación con el Job real, control de lanzamientos inciertos, arranques concurrentes,
  workers tardíos y recuperación segura del bloqueo por token/generación.
- Resultados por búsqueda y generales, métricas N/D cuando faltan y guardado remoto
  separado de extracción terminada. Fallos de integridad/persistencia detienen el lote.
- Historia: 30 días, máximo 100 terminales y 2 MB vivos; nunca borra activas ni catálogo.

Criterios de carga, contadores, estimación, seguridad y límites completos:
[EJECUCIONES.md](EJECUCIONES.md).

## Pruebas y límites

Validación nueva de esta tarea, con bases sintéticas en `.tmp/`, sin portales reales
ni solicitudes Gemini:

| Comprobación | Resultado |
| --- | --- |
| Consola completa, cierre final | 440 aprobadas |
| Catálogo completo | 249 aprobadas |
| Scraper completo | 122 aprobadas |
| Ejecuciones y durabilidad, después de los últimos ajustes | 48 aprobadas |
| Editor histórico v0.4, repetición específica | 5 aprobadas |
| Dependencias / sintaxis / diff | pip check, compileall, parseo PowerShell y diff --check correctos |

Las 48 específicas incluyen Chromium y no se suman otra vez al total de consola.
Las tres suites completas se ejecutaron en procesos separados durante esta tarea;
no se reutilizan cifras de entregas históricas. La consola final corresponde al
runtime adccc7a más la sincronización de la prueba v0.4, sin cambios funcionales posteriores.
Catálogo y scraper no recibieron cambios de código después de sus pasadas aprobadas.
Se verificaron 1440×900, 768×1024 y 390×844; selección, foco, labels, inactivas,
vacíos, progreso, completado, fallo y desplazamiento de tablas sin overflow de página.
El envío real del formulario en Chromium usa Cloud Run simulado: solo B seleccionada,
un lanzamiento y mismo UUID después de recargar.

En una pasada anterior, la prueba histórica de edición del cliente navegó por el
enlace nativo en lugar de abrir el modal; el enlace existe antes de ejecutar el
script defer. Se corrigió la sincronización de la prueba, esperando la carga completa.
La repetición de sus cinco flujos pasó. Se añadió espera explícita de `load` en esa
prueba; no cambió el editor ni se aumentó arbitrariamente su timeout.
Se corrigieron también dos argumentos PowerShell de preparación durante la operación;
los pasos restantes se completaron sin recrear el Job ni alterar el tráfico.
Permanece la advertencia conocida de BlockingPortal de Starlette/AnyIO.

No se inició ninguna captura real ni el Job manual en Google Cloud. La primera
validación operativa de portales/credenciales del nuevo flujo queda pendiente de la
selección concreta del usuario; las simulaciones no se presentan como scraping real.
La revisión sí fue probada por IAP y se confirmó la lista real de tres búsquedas,
sus mediciones previas y la selección/todas sin pulsar Iniciar ejecución.
Cuatro GET sin sesión (página, estado, JS, catálogo) devolvieron 302 a Google;
POST sin sesión y con identidad falsa devolvió 401. No se hizo público el servicio.

## Infraestructura y datos compartidos

Proyecto único radar-inmobiliario-co, us-central1, servicio radar.

- Job nuevo radar-manual-review: 1 tarea/paralelismo 1, sin reintentos, 1 vCPU/2 GiB,
  timeout total 10800 s. Reutiliza Dockerfile.jobs y scraper/job.py; los Jobs de las
  tres fuentes preparados antes de esta tarea permanecen intactos.
- Identidad radar-jobs y montajes Wasi de Secret Manager existentes, sin nuevas claves.
- Rol personalizado radarManualExecution, enlazado únicamente al Job nuevo para
  radar-web: run.jobs.run, run.jobs.runWithOverrides, run.executions.get/list.
  La definición del rol es del proyecto; su binding está limitado al Job.
- Registro `gs://radar-inmobiliario-co-state/radar/executions/control.json`.
  Usa el permiso existente sobre radar/. Sin nueva base de datos ni permisos de personas.
- Revisión web etiquetada, origen de formularios del tag y `--no-traffic`.
  La política Run Invoker mantiene solo al agente IAP, con el mismo etag observado.

**La revisión comparte catálogo, snapshot, lock, cuentas de servicio, secretos y
recursos con producción. La URL de prueba no implica aislamiento de datos.**
Una captura iniciada allí puede actualizar el catálogo común y ocupar las operaciones
CRM/catálogo en producción; el seguimiento continúa disponible. No iniciar scraping
real hasta explicar ese alcance y obtener los IDs/nombres concretos seleccionados.

El snapshot no recibe nueva estructura SQLite de negocio por esta función. El
registro de control es aditivo y separado. Se verificó el respaldo inicial recuperable
por su hash local y existencia remota:
`backups/initial-20261111.tar.gz`, SHA256
`9e5fcd3e4d2f70d7c34cfd49adf3ebec089254c4aad6049dfaf283bd406d0840`.
La generación del snapshot antes de la comprobación web fue 1794522630683889;
la comprobación final conservó esa misma generación, tamaño 6048511 y MD5 JHy1rLK0R+Oc/TNzriWSZg==.
No se sustituyeron datos reales por pruebas ni se ejecutaron migraciones nuevas.

Impacto: builds privados de esta entrega, arranques de consulta, operaciones GCS de
control y futuros Jobs manuales. No hay costo mensual prometido ni precios inventados;
el consumo real sigue por medir. Versionado/soft delete del bucket conservan bytes
adicionales según su política existente. No se cambió esa política global.

## Builds y código desplegado

Runtime de ambas imágenes: **adccc7a10cefdc048cb427bd36a854975ca7a48d**.
Cambios posteriores son únicamente evidencia y sincronización de la prueba histórica.

| Imagen | Build final | Digest |
| --- | --- | --- |
| web | 9e2abbe8-8f7e-4913-95e4-97e5dd246f91 | sha256:e071ee7a1fd2f5d736be25deafb5a3f421e3e29e7bf47e67ad0fe43f6d0b59f0 |
| jobs | a423ae3a-a2dc-47f3-bbf7-5b3ac1b68f4d | sha256:c41811d3c16e6cf71e374a4cad9e4f5d6b6c89b1c2bd3682406b92db791832e8 |

Ambos builds finalizaron SUCCESS. Repositorio de imágenes privado existente:
us-central1-docker.pkg.dev/radar-inmobiliario-co/radar.
Las imágenes intermedias de preparación no atienden producción ni se atribuyen como
runtime final; permanecen sujetas a la limpieza habitual del registro.

## Cuatro casos manuales breves

1. Abrir la URL por IAP. Ver las tres fuentes, nombre/criterios, carga y última captura;
   el botón debe estar deshabilitado sin selección.
2. Seleccionar individualmente y todas las activas, luego desmarcar. Inactivas no
   ejecutables. Guardar una búsqueda nueva desde Inicio debe mostrarla aquí sin capturar.
   Usar datos sintéticos para ensayar altas ajenas a la configuración real deseada.
3. Solo con selección concreta autorizada: iniciar una vez, recargar y abrir su enlace
   en otra pestaña. Mismo UUID/Job; progreso consultable mientras catálogo está ocupado.
4. Al terminar, revisar resultado por búsqueda, no ejecutadas, contadores/N/D, tiempos,
   confirmación de generación e historial. Los fallos/parciales se prueban localmente
   con simulaciones; no provocar fallos en los datos compartidos.

## Reversión compatible

Producción ya sigue en radar-verify-20261111; no hay que restaurar datos para retirar
la prueba. Comprobar primero que no hay ejecución activa y retirar solo el tag:

```powershell
& ../cloud.ps1 run services update-traffic radar --remove-tags=ejecuciones-review --project=radar-inmobiliario-co --region=us-central1
```

No cambiar porcentajes ni restaurar SQLite para revertir la interfaz. Mantener Job,
registro y permiso hasta cerrar las ejecuciones activas; su retiro posterior se hace
con autorización operativa. La versión anterior puede leer los datos de negocio;
el control nuevo se conserva separado para no perder informes. Los scrapers previos,
clientes, matching, anunciantes, CSV e historial técnico conservan sus mecanismos.

## Git y archivos

Clon independiente: `C:/Users/Palex25/Documents/Boch-Lab/Radar-CloudRun-20261111/repo`.
Rama `codex/ejecuciones-manuales`, creada desde develop a564dad. No hubo merge,
push ni tags. Se conservaron los cambios posteriores legítimos de la referencia.
No hubo conflictos. Todos los cambios del agente se realizaron en este clon;
no se ejecutaron comandos de escritura sobre el proyecto original.

Commits locales de código:
- 03132a4: implementación inicial.
- 85a9828: cierre/reconciliación sin carreras.
- f3a17f1: etiquetas Wasi y argumento del despliegue.
- adccc7a: envío web verificado y espera de persistencia.

El commit documental final incluye este informe y la espera de carga de la prueba
v0.4. El cierre se registra en un commit local de evidencia y pruebas; el árbol de trabajo queda limpio (los temporales sintéticos permanecen ignorados)..

Archivos modificados o añadidos frente a a564dad:

- `CHANGELOG.md`
- `Dockerfile.jobs`
- `Dockerfile.web`
- `RADAR_PROYECTO_RECTOR.md`
- `README.md`
- `consola/docs/EJECUCIONES.md`
- `consola/docs/ENTREGA_EJECUCIONES_20261113.md`
- `consola/durable.py`
- `consola/ejecuciones.py`
- `consola/static/ejecuciones.css`
- `consola/static/ejecuciones.js`
- `consola/templates/v04/base.html`
- `consola/templates/v06/_ejecucion06.html`
- `consola/templates/v06/_ejecuciones_historial06.html`
- `consola/templates/v06/base06.html`
- `consola/templates/v06/ejecuciones06.html`
- `consola/tests/test_ejecuciones.py`
- `consola/tests/test_v04_browser.py`
- `deployment/README.md`
- `deployment/deploy-review.ps1`
- `deployment/manual-job-role.json`
- `docs/ESTRUCTURA.md`
- `docs/README.md`
- `ejecuciones/__init__.py`
- `ejecuciones/cloud_run.py`
- `ejecuciones/control.py`
- `ejecuciones/mediciones.py`
- `ejecuciones/servicio.py`
- `ejecuciones/worker.py`
- `scraper/fincaraiz/scraper.py`
- `scraper/job.py`
- `scraper/metro/__init__.py`
- `scraper/metro/scraper.py`
- `scraper/metro/web.py`
- `scraper/wasi/durable.py`
- `scraper/wasi/scraper.py`
