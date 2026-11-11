# Acceso privado con Google e IAP

Incluido en la entrega **v0.11.0**. La autorización posterior permite commit y sincronización con GitHub; no despliegue ni cambios Cloud. El resultado y estado Git documentados al final conservan la evidencia del cierre local anterior al versionado. Ver [changelog vigente](../../CHANGELOG.md).

Implementación local del 11 de noviembre de 2026. Abrir Radar, iniciar sesión con
Google y entrar solo si IAP autoriza la cuenta. Mónica y el propietario tienen
el mismo acceso funcional. Altas y revocaciones viven en IAP/IAM: no hay
usuarios, contraseñas, roles ni listas de correos en SQLite.

## Diseño y variables

`consola/acceso.py` es el middleware ASGI instalado en `scraper/metro/web.py`.
Actúa antes del routing y las dependencias: incluye páginas, API, rutas antiguas,
estáticos, exportaciones, formularios, escrituras y solicitudes de Gemini.
Las reglas y las bases existentes no cambian. Gemini requiere solicitud explícita.

| Variable | Desarrollo | Futuro servicio Cloud Run |
| --- | --- | --- |
| `RADAR_AUTH_MODE` | `local`, explícito | `iap`, obligatorio |
| `RADAR_IAP_AUDIENCE` | No necesaria | `/projects/PROJECT_NUMBER/locations/REGION/services/SERVICE_NAME` |
| `RADAR_PUBLIC_ORIGIN` | Origen local validado | Origen HTTPS exacto de Radar, sin barra final ni ruta |

No son secretos. La audiencia usa el **número** de proyecto, región y nombre del
servicio: no ID de proyecto, URL `run.app`, backend de balanceador ni cliente OAuth.

Se exige una única cabecera `X-Goog-IAP-JWT-Assertion`. PyJWT con `cryptography`
comprueba ES256, `kid`, firma, emisor `https://cloud.google.com/iap`, audiencia
exacta, `sub`, `iat` y `exp`, con 30 segundos de tolerancia y duración máxima de
660 segundos. Solo se usan claves de la URL oficial fija
`https://www.gstatic.com/iap/verify/public_key-jwk`; no URLs del token.
`PyJWKClient` conserva JWKS cinco minutos y gestiona rotación con cooldown de
30 segundos ante claves desconocidas. La verificación usa el pool de hilos para
no bloquear el loop HTTP. Un fallo de descarga o validación rechaza el acceso.
No se aceptan cabeceras de correo/identidad sin firma ni se registran tokens,
claims o excepciones que puedan contener credenciales.

Configuración ausente, modo desconocido, audiencia u origen incompletos devuelven
503; credencial ausente o inválida, 401. No hay fallback abierto. La presencia de
`K_SERVICE`, `K_REVISION` o `K_CONFIGURATION`, incluso vacías, prohíbe modo local.
En IAP, `/docs`, `/redoc`, `/openapi.json` y el callback se deshabilitan; sin
autenticar también quedan tras la barrera. No hay flujos WebSocket; se rechazan.

Única excepción: **GET/HEAD `/health` exacto**, sin consultar configuración ni
almacenamiento. GET responde solamente `{"status":"ok"}`; HEAD, cuerpo vacío.
`/health/`, subrutas, otras mayúsculas y escrituras no son excepciones.

## Uso local

Desde la raíz, instalar las dependencias actualizadas y elegir el modo:

```powershell
.\.venv\Scripts\python.exe -m pip install -r scraper/requirements.txt
$env:RADAR_AUTH_MODE = 'local'
.\.venv\Scripts\python.exe scraper/run.py serve --host 127.0.0.1
```

Abrir `http://127.0.0.1:8000/v0.6/`. No requiere Google. El comando rechaza un
bind local fuera de loopback y desactiva proxy headers. El middleware comprueba
IP de cliente, servidor y Host de loopback (`127.0.0.1`, `::1` o `localhost`).
Una cabecera del navegador nunca selecciona el modo. Con Uvicorn directo añadir
`--no-proxy-headers` y enlazar a loopback. No exponer mediante túneles o proxies.

## Operaciones del navegador

Todo método distinto de GET/HEAD/OPTIONS exige **un único `Origin` idéntico al
esperado**. No se admite ausencia, `null`, otro esquema, puerto o subdominio,
ni fallback con Referer. En IAP procede de `RADAR_PUBLIC_ORIGIN`, nunca de Host
o X-Forwarded. Localmente se compara con el Host de loopback ya validado.
`Sec-Fetch-Site` cross-site/same-site se rechaza como defensa adicional.

Es la protección CSRF acotada elegida: formularios HTML y fetch actuales envían
Origin al modificar datos, incluso sin JavaScript. Las tres plantillas usan
Referrer-Policy `same-origin`: conserva Origin en formularios propios y sigue
omitiendo el Referer hacia otros sitios. La política anterior `no-referrer`
provocaba `Origin: null` en los envíos nativos de Chromium. Al rechazar orígenes
ausentes no se necesita token CSRF ni sesión propia. Un navegador que omita
Origin recibirá 403; clientes de API deben enviarlo además de su acceso IAP.
No se habilita CORS ni se añaden escrituras por GET; se conservan los POST.

## Preparación futura en Google Cloud — no ejecutada

Requiere autorización posterior. No se añade Dockerfile web ni se modifican
`Dockerfile.jobs`, persistencia, Jobs o Scheduler.

1. En `PROJECT_ID`, habilitar API IAP. Cloud Run → `SERVICE_NAME` en `REGION` →
   Security → Require authentication → Identity-Aware Proxy. Integración directa,
   sin balanceador. La consola concede `roles/run.invoker` al agente
   `service-PROJECT_NUMBER@gcp-sa-iap.iam.gserviceaccount.com`; verificarlo sobre
   ese servicio. Con CLI, la opción es `--iap`.
2. En Edit policy de IAP del servicio, dar únicamente a `user:MONICA_EMAIL` y
   `user:OWNER_EMAIL` el rol `roles/iap.httpsResourceAccessor`. Revocar quitando
   el principal de ese recurso. No usar `allUsers`, `allAuthenticatedUsers`,
   dominios ni grupos amplios. Revisar políticas heredadas que amplíen acceso.
   Las usuarias no necesitan roles administrativos ni invocación pública.
3. Cuentas personales/externas o proyecto sin organización: Configure in IAP →
   consentimiento OAuth **External** → Auto generate credentials, o cliente
   OAuth personalizado según la consola. El cliente gestionado por Google cubre
   identidades internas de organización. OAuth externo permite login; IAM sigue
   restringiendo las cuentas elegidas. Resolver estado de publicación/prueba y
   requisitos que muestre Google antes del uso operativo. El secreto OAuth queda
   en Google; Radar no lo necesita ni lo guarda.
4. Obtener número con `gcloud projects describe PROJECT_ID --format="value(projectNumber)"`.
   Verificar nombre/región mediante `gcloud run services describe SERVICE_NAME --project=PROJECT_ID --region=REGION`.
   Construir audiencia de la tabla y configurar las tres variables del servicio.
   El origen será el de la URL que se abrirá. Ejecutar Uvicorn con
   `--no-proxy-headers`: validación IAP y origen fijo no necesitan esas cabeceras.
5. Comprobar `Iap Enabled: true`. Probar la URL **directa `run.app`** en ventana
   privada: sin sesión debe pedir login/denegar; cuenta no elegida, denegar;
   ambas elegidas, permitir páginas/API/exportaciones y formularios. Probar
   revocación contemplando propagación de IAM/sesiones, cabeceras falsas y
   ausencia de cambios al rechazar. Repetir en cualquier URL alternativa.
   IAP directo cubre los caminos de ingreso; la firma JWT agrega una barrera
   si IAP se desactiva accidentalmente. `/health` solo es excepción dentro del
   contenedor: IAP aún puede interceptarlo externamente.

Permisos de preparación para el operador: Google documenta `roles/run.admin`,
`roles/iap.admin`, lector sobre la imagen de Artifact Registry y
`roles/iam.serviceAccountUser` sobre la identidad del servicio al actualizar la
revisión. Configurar externos requiere además `roles/iap.settingsAdmin` y
`roles/oauthconfig.editor`. Limitar administración al operador/recursos necesarios.
El acceso cotidiano solo necesita el rol IAP del paso 2; el agente, `run.invoker`.
Radar no requiere claves de cuenta de servicio para verificar firmas públicas.

Referencias oficiales consultadas el 11 de noviembre de 2026:

- [IAP directo en Cloud Run: configuración y permisos](https://docs.cloud.google.com/run/docs/securing/identity-aware-proxy-cloud-run).
- [Cabeceras firmadas: algoritmo, emisor, audiencia y vigencia](https://docs.cloud.google.com/iap/docs/signed-headers-howto).
- [OAuth personalizado de IAP](https://docs.cloud.google.com/iap/docs/custom-oauth-configuration).
- [PyJWT y caché PyJWKClient](https://pyjwt.readthedocs.io/en/stable/api.html).

## Pruebas locales

`consola/tests/test_acceso.py` genera claves ES256/JWKS en memoria y sustituye la
descarga en el transporte de pruebas. No existe URL JWKS configurable ni bypass
de pruebas en la aplicación. Los fixtures configuran modo local normal y simulan
conexión loopback y Origin del navegador en TestClient; Chromium usa sockets reales.

Ejecutar las tres suites en procesos separados como explica [V06](V06.md), con
`--basetemp` nuevo en `.tmp/`. Windows puede requerir ejecución fuera del sandbox
por sockets de asyncio/TestClient y Chromium. Todas las bases son sintéticas.
El login auténtico, IAM, revocación, audiencia del servicio real y cobertura de
URLs se comprobarán durante el despliegue autorizado posterior.

### Resultado ejecutado el 11 de noviembre de 2026

| Suite en proceso independiente | Resultado |
| --- | --- |
| Consola, incluyendo Chromium y acceso | 385 aprobadas |
| Catálogo | 247 aprobadas |
| Scraper | 121 aprobadas |
| Total | **753 aprobadas** |

Las 49 pruebas específicas de acceso están incluidas en consola y se repitieron
al finalizar el ajuste de aislamiento: 49 aprobadas. Cubren credenciales ausentes,
manipuladas, expiradas, firma/emisor/audiencia incorrectos, identidad válida,
cabeceras falsificadas, rutas completas antes de dependencias, ausencia de
mutaciones/tareas ante rechazo, configuración incompleta, loopback, health,
Origin, caché, rotación y fallos JWKS. Chromium cubre escritorio, tablet y móvil,
formularios con/sin JavaScript, comentarios fetch, foco, errores, vacíos y ancho.
Se inspeccionaron capturas sintéticas de escritorio y móvil. `git diff --check`,
enlaces locales de la documentación y `pip check` pasaron. Permanece la advertencia
conocida de deprecación BlockingPortal de Starlette/AnyIO.

Las primeras pasadas detectaron la incompatibilidad de `no-referrer` con Origin
en formularios y dos llamadas de preparación API de Playwright sin Origin;
quedaron corregidas antes del resultado completo. Una comprobación GET inicial
de cabeceras podía resolver la base auxiliar operativa; ese adaptador abre las
consultas con `mode=ro` y `query_only`, sin escrituras. Se corrigió el fixture
IAP fijando las cuatro rutas a `.tmp/` y se repitieron sus 49 pruebas aisladas.
No se ejecutaron extracciones reales, llamadas reales a Gemini ni cambios Cloud.

Evidencia temporal: `.tmp/iap-20261111/` (bases y subcarpetas de ejecución);
las capturas históricas de las pruebas v0.6 también usan las rutas `.tmp/v06-*`
que conserva su suite. No se capturó el Word privado. `develop` permanece en
`a9f6992223d3398752303ac306de73bc14d817da`, con índice vacío, sin conflictos y
sin commit, tag, push o merge. Los cambios quedan locales para revisión.

Archivos de esta implementación:

| Área | Archivos |
| --- | --- |
| Barrera y arranque HTTP | `consola/acceso.py`, `scraper/metro/web.py`, `scraper/metro/__main__.py` |
| Formularios y política de referencias | `consola/templates/base.html`, `consola/templates/v04/base.html`, `consola/templates/v06/base06.html` |
| Dependencias y exclusión del Word privado | `scraper/requirements.txt`, `scraper/requirements.lock.txt`, `.dockerignore` |
| Pruebas y preparación sintética | `consola/tests/test_acceso.py`, `consola/tests/acceso_http.py`, `consola/tests/conftest.py`, `catalogo/tests/conftest.py`, `scraper/tests/conftest.py`, `consola/tests/test_v04_browser.py` |
| Documentación vigente | Este documento, `RADAR_PROYECTO_RECTOR.md`, `README.md`, `consola/README.md`, `scraper/README.md`, `consola/docs/V06.md`, `docs/README.md` |
