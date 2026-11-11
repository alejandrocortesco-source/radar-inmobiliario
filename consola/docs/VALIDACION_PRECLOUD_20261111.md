# Validación local previa a Google Cloud — 11 de noviembre de 2026

> Hallazgo posterior del usuario: el registro rechazaba URLs Metrocuadrado por
> tipos, como `/apartamento-casa/arriendo/bogota/la-carolina`. La cobertura
> inicial no incluía ese formato. Véase la [corrección y regresión posterior](CORRECCION_URL_METRO_20261111.md).
> Los resultados siguientes describen la ejecución inicial y no incluyen esa corrección.

Evaluación sobre `develop`, versión/tag `v0.11.0`, commit
`fe29bb0cb071ca0bbb489b090495c7acdf88b19b`. El árbol y el índice estaban limpios
al comenzar. Se conservaron las bases, procesos ajenos, archivos privados e historial.
Esta validación no incluye despliegue, extracción auténtica, generación auténtica de
Gemini, autenticación contra Google ni cambios de configuración externos.

El resultado es favorable para revisión local. No acredita preparación operativa
completa para Cloud Run: persistencia del servicio web, imagen web, IAP/IAM reales,
operación desatendida y costes siguen pendientes de una etapa autorizada.

## Matriz de funcionalidades y riesgos

| Funcionalidad / riesgo | Verificación ejecutada | Alcance y resultado |
| --- | --- | --- |
| Clientes y oportunidades | `test_v03`, `test_v06`, `test_revision_local` | Alta, consulta, edición, validaciones, migración aditiva, rollback, separación de entidades, inactivos/cerradas y reinicio de proceso. Aprobado. |
| Búsquedas / extracción accidental | `test_origen_busquedas`, `test_fuentes_eliminar`, `test_wasi`, `test_fincaraiz`, `test_v06`, ensayo nuevo | URLs y criterios por fuente, duplicados, nombres, revisiones, eliminación e historial. Guardar no captura. Edición Wasi y Fincaraíz; activación/desactivación en la UI actual únicamente para Fincaraíz. Aprobado. |
| Metrocuadrado | `scraper/tests/test_extraction`, `test_prices`, `test_incremental`, `test_runner_guards` | Parsing de fixtures, precios dudosos, paginación simulada, deduplicación entre búsquedas, cambios, dos ausencias exitosas, fallos parciales y checkpoints. Aprobado; sin portal real. |
| Wasi | `scraper/tests/test_wasi` y `consola/tests/test_wasi` | Controles dependientes, login/OTP/bloqueos simulados, paginación Chromium contra fixtures, incrementales, recuperación, datos ausentes/error, identidad por fuente. Aprobado; sin cuenta real. |
| Fincaraíz | `scraper/tests/test_fincaraiz` y `consola/tests/test_fincaraiz` | NEXT_DATA, filtros/página efectivos, enlaces de paginación, totales, duplicados, interrupciones, fichas parciales, ubicación principal, áreas separadas y contactos. Aprobado; respuestas representativas simuladas. |
| Catálogo | Suite `catalogo`, `test_v02`, `test_v04`, `test_categorias`, ensayo nuevo | Rangos inclusivos, orden global, desconocidos al final, paginación, detalle, CSV completo por oferta y catálogo inalterado por escrituras auxiliares. Aprobado. |
| Anunciantes | `test_anunciantes`, integración de tres fuentes | Igualdad literal del nombre, diferencias de mayúsculas/espacios, contactos disponibles, enlaces seguros, perfil y propiedades asociadas. Aprobado; nunca se llama ni se envía un mensaje. |
| Matching | `test_v03`, `test_matching_diagnostico`, `test_presupuesto_cop`, `test_gemini_manual`, ensayo nuevo | Operación/tipo/ciudad/barrio/presupuesto/habitaciones estrictos; preferencias flexibles; faltantes pendientes; diagnóstico de descartes; vacío; decisiones comerciales independientes. Aprobado. |
| Moneda | `test_presupuesto_cop`, `test_v02`, filtros/modelos y pruebas Gemini | Importes numéricos interpretados como COP, sin conversión ni condición por metadatos históricos. Ausente/inválido no se transforma en cero. Aprobado. |
| Gemini / consumo accidental | `test_gemini_manual`, `test_v06` | Cero llamadas automáticas con clave configurada, solicitud explícita, privacidad del payload, vista previa obsoleta 409, caché, límite, doble clic/concurrencia y novedades. Aprobado mediante mocks. |
| Gemini / respuesta no fiable | `test_gemini_diagnostico`, `test_gemini_manual`, `test_v06`, ensayo nuevo | IDs, evidencias, puntuación entera 0–100, campos extra, respuesta incompleta/bloqueada/JSON inválido, timeout, conexión, HTTP 400/429/503. Fallo conserva determinista y no reintenta automáticamente. Aprobado con transporte falso y validación real del adaptador. |
| Acceso | 49 casos de `test_acceso` incluidos en consola | ES256/JWKS sintéticos, firma/emisor/audiencia/identidad/tiempos, rotación y fallo cerrado, rutas antiguas/API/estáticos/exportación antes de dependencias, health exacto, Origin duplicado/ausente/hostil, loopback, rechazo de modo local en Cloud Run y ausencia de mutaciones/tareas ante rechazo. Aprobado; no login IAP auténtico. |
| Entradas maliciosas y secretos | `test_acceso`, `test_v02`, `test_v03`, `test_storage_web`, pruebas de Gemini/fuentes | XSS escapado, SQL en parámetros, CSV con fórmulas neutralizadas, URLs hostiles rechazadas y diagnósticos/logs saneados con secretos señuelo. Aprobado; no equivale a una auditoría de penetración. |
| Identificación supervisada | `catalogo/tests/test_identificacion`, `consola/tests/test_identificacion_ui` | Propuestas, revisión, confirmación explícita, reversión, agrupación tras filtros, metadatos y decisiones por publicación. Aprobado. |
| Persistencia/concurrencia | SQLite sintético, suites incremental/Gemini/asociaciones; ensayo nuevo | Transacciones y rollback, reservas idempotentes, cambios durante evaluación, caché/novedades, snapshots y lock/generaciones GCS simulados. Reinicio real conserva cliente, teléfono, búsqueda y caché. Aprobado localmente; almacenamiento cloud real pendiente. |
| Interfaz | Chromium 140, suites existentes y ensayo nuevo | Flujos con/sin JS existentes, navegación, formularios, labels, foco, errores, vacíos, enlaces y scroll interno de tablas. Escritorio 1440×900, tablet 768×1024 y móvil 390×844. Aprobado; no prueba de Safari ni iPad físico. |

## Ejecuciones y evidencia

Todas las bases nuevas están en `.tmp/precloud-20261111/` o `tmp_path`.
Las tres suites se ejecutaron en procesos independientes conforme a V06.

| Ejecución nueva | Resultado |
| --- | --- |
| Consola inicial completa, con Chromium | 385 aprobadas, 221,53 s |
| Catálogo completo | 247 aprobadas, 10,25 s |
| Scraper completo | 121 aprobadas, 48,63 s |
| Ensayo nuevo de entrega aislado | 1 aprobado, 8,36 s; no sumar las repeticiones |
| Consola de cierre, incluyendo ensayo | 386 aprobadas, 228,06 s |
| Total final (sin sumar repeticiones) | **754 aprobadas**, sin fallos ni omisiones |
| Dependencias | `pip check`: sin conflictos |
| Formato Git | `git diff --check`: correcto |

El primer intento de consola tuvo 240 errores de preparación porque faltaba la
carpeta padre de `--basetemp`; no se cuenta como validación aprobada. Se creó el
directorio y se repitió completa. Durante la preparación del nuevo ensayo se
corrigieron expectativas de fixtures (CSV de siete filas, texto real de contacto
ausente y barrio controlado para construir un caso realmente vacío). No fueron
defectos de la aplicación. Las evidencias de esos intentos se conservan.

Permanece la advertencia de deprecación de `BlockingPortal` de Starlette/AnyIO.
No se instalaron dependencias ni se corrigió código productivo: no se detectó
un defecto reproducible nuevo de la aplicación dentro de esta cobertura.

Evidencias locales:

- JUnit y logs: `catalogo.xml`, `scraper.xml`, `consola-final.xml`,
  `consola-cierre.xml` y logs correspondientes.
- `revision-test-4/`: recorrido completo Chromium, reinicio y capturas. El ensayo
  verifica hashes de las tres bases técnicas antes/después y conserva el CRM aparte.
- `interfaz-final.json` y `final-*.png`: doce pantallas sobre la instancia final,
  sin errores JS/consola, peticiones fallidas, respuestas HTTP de error ni red externa.
  Se inspeccionaron visualmente escritorio, tablet y móvil.
- `rendimiento.json`, `rendimiento.log`, `medir.py`: muestras y medición reproducible.
- `demo-final/manifest.json`: IDs y configuración sintéticos de los cuatro clientes.
  `simulaciones.jsonl` se crea al solicitar Gemini: solo HTTP simulado y cantidad,
  sin clave, prompt ni contactos. Su ausencia inicial confirma cero evaluaciones.

Para repetir suites desde PowerShell en la raíz, crear un directorio de evidencia
nuevo (no reutilizar un `--basetemp` previo: pytest lo limpia):

```powershell
$radarEvidencia = '.tmp/precloud-' + (Get-Date -Format 'yyyyMMdd-HHmmss')
New-Item -ItemType Directory -Path $radarEvidencia | Out-Null
foreach ($radarSuite in @('consola', 'catalogo', 'scraper')) {
    .\.venv\Scripts\python.exe -c "import sys,pathlib; r=pathlib.Path.cwd(); sys.path[:0]=[str(r),str(r/'scraper'),str(r/'consola/tests')]; import pytest; raise SystemExit(pytest.main(['--rootdir=.','-o','pythonpath=',sys.argv[1]+'/tests','-q','--basetemp='+sys.argv[2]+'/'+sys.argv[1],'--junitxml='+sys.argv[2]+'/'+sys.argv[1]+'.xml']))" $radarSuite $radarEvidencia
    if ($LASTEXITCODE -ne 0) { throw "Falló $radarSuite" }
}
```

## Respuesta local con muestra representativa

600 publicaciones en tres SQLite de fuente y 30 clientes activos en otro CRM.
Diez mediciones por ruta después de una petición de calentamiento, concurrencia 1,
60 muestras medidas (66 peticiones incluidas las de calentamiento). Se verificaron
los totales de catálogo y las 600 filas CSV; los comportamientos de negocio se
comprueban además en las suites, no solo mediante HTTP 200.

| Ruta | Mediana ms | p95 observado / máximo ms |
| --- | ---: | ---: |
| Inicio | 597 | 806 |
| Clientes | 615 | 811 |
| Catálogo HTML | 288 | 345 |
| Catálogo API | 178 | 228 |
| Buscar coincidencias (POST determinista) | 386 | 491 |
| Exportar 600 ofertas CSV | 355 | 472 |

Con solo diez muestras, el percentil por rango más próximo coincide con el máximo.
Medición local Windows, con regresión ejecutándose simultáneamente; no es un
benchmark de máquina exclusiva ni una prueba de carga concurrente. No incluye
latencia del proveedor, IAP, red cloud, arranque en frío ni escalado a cero. El
catálogo completo se recorre en memoria y las tareas manuales viven en el proceso
web; la muestra no demuestra escalabilidad ilimitada, disponibilidad ni coste.

## Instancia para revisión y aislamiento

URL: **http://127.0.0.1:8765/v0.6/**. Acceso local existente `RADAR_AUTH_MODE=local`,
solo loopback, `proxy_headers=False`, sin contraseña. No hay bypass añadido al
middleware productivo. El proceso está activo al cierre y se sirve mediante la
misma aplicación FastAPI/Jinja y los adaptadores SQLite reales.

El lanzador separado `consola/tools/revision_local.py` exige una subcarpeta de
`.tmp/`, rechaza Cloud Run, fija las cuatro bases, descarta credenciales externas,
inyecta solo una clave ficticia y usa `httpx.MockTransport` para el adaptador real
de Gemini. Simula la verificación Fincaraíz solo para URLs de fixtures conocidas.
Sincronización de opciones Wasi, conexiones externas y subprocesos están
deshabilitados. Un banner y una cabecera identifican el entorno. No se importa
este lanzador desde la aplicación ni se modifica la protección de producción.

En esta demostración, `banos_min=9` produce HTTP 429 simulado; el resto produce
JSON válido, puntuación 85 y explicación marcada SIMULADO. Los contadores de
«solicitudes a Google» de la UI se refieren aquí a intentos del transporte falso:
no son llamadas ni tokens auténticos. Los perfiles/publicaciones usan el dominio
reservado `example.test`; no corresponden a anuncios ni contactos reales.

La instancia final contiene 36 publicaciones, tres búsquedas y cuatro clientes.
Sus dos casos Gemini se dejan sin evaluar para la prueba manual. Reiniciar con
el mismo directorio conserva los datos; no vuelve a sembrar al existir manifest.

Comando verificado de inicio, desde la raíz (si ya está activa, el puerto estará ocupado):

```powershell
.\.venv\Scripts\python.exe consola/tools/revision_local.py --datos .tmp/precloud-20261111/demo-final --port 8765
```

Para revisar/detener exclusivamente esta instancia, su PID de lanzamiento está en
`.tmp/precloud-20261111/demo-final.pid`; Windows puede ejecutar el intérprete real
en un proceso hijo. Comprobar `CommandLine`/`ParentProcessId` con CIM antes de
detenerlos. No detener la instancia operativa que pudiera existir en el puerto 8000.

## Cuatro casos manuales reproducibles

1. **Crear y editar un cliente.** Desde Inicio, pulsar **Registrar cliente y necesidad**.
   Introducir nombre `Lucía Prueba Local`, teléfono `TEST-001`, operación **Compra**,
   tipo **Apartamento**, ciudad **Bogotá**, presupuesto mínimo `350000000`, máximo
   `450000000`, habitaciones mínimas `2`, máximas `3`. Abrir **Seleccionar barrios**,
   marcar **La Carolina** y pulsar **Listo**. Dejar preferencias vacías. Pulsar
   **Confirmar y guardar oportunidad**. Se abre su ficha y aparecen cinco candidatos.
   Abrir **Editar cliente**, cambiar nombre a `Lucía Prueba Editada` y teléfono a
   `TEST-002`, mantener Activo y pulsar **Guardar cliente**. Volver a Clientes,
   reabrir y recargar: ambos datos deben conservarse. El ensayo automatizado comprueba
   también esos datos después de terminar el proceso y arrancar otro con las mismas bases.

2. **Administrar búsqueda, catálogo y anunciante.** En Inicio abrir **Búsquedas
   registradas**, localizar **Demo Fincaraíz**, pulsar **Editar búsqueda** y cambiar
   el nombre descriptivo a `Prueba Fincaraíz revisada`. Conservar la URL
   `https://www.fincaraiz.com.co/venta/casas-y-apartamentos/la-carolina/zona-norte/bogota`
   y pulsar **Guardar fuente**. Debe informar que no inició extracción. Desactivar
   la búsqueda, reabrir Búsquedas registradas para comprobar Inactiva y activar de
   nuevo. El catálogo debe seguir con 36 publicaciones en todo momento.
   Abrir el [catálogo filtrado](http://127.0.0.1:8765/v0.4/?ciudad=Bogot%C3%A1&operacion=venta&precio_min=350000000&precio_max=450000000&orden=precio_desc&limit=12).
   Debe mostrar **7** ofertas de Bogotá entre 350 y 450 millones COP, mayor precio
   primero (incluye casas y apartamentos, sin filtro de habitaciones). Abrir la
   primera zona La Carolina: su ficha es **Demo A - límite superior**, 450 millones.
   Abrir **Agencia Demo**: debe mostrar **35 otros inmuebles**, paginados, perfil
   público y **No hay datos de contacto disponibles**. No abrir enlaces externos.
   En el catálogo, **Exportar → Descargar CSV** debe descargar siete filas en COP.

3. **Matching y descartes verificables.** En Clientes abrir **Demo Matching** y
   pulsar **Buscar coincidencias**. Sus criterios son compra, apartamento, Bogotá,
   La Carolina, 350–450 millones COP inclusivos, 2–3 habitaciones; preferencias:
   área construida mínima 80 m² y dos baños. Deben quedar **cinco** publicaciones:
   A y J cumplen los límites exactos; B permanece aunque tiene 65 m² y un baño;
   C queda pendiente por habitaciones y L por precio. Deben existir **tres**
   resultados con requisitos conocidos cumplidos y **dos** pendientes técnicos.
   El contador comercial «pendientes» es independiente y comienza en cinco.
   El [diagnóstico JSON existente](http://127.0.0.1:8765/api/oportunidades/0fb8dc87-1666-45a8-b802-eeb5805ecb0d/diagnostico)
   muestra 36 evaluados y **31 descartes**: D por 450000001, E por una habitación,
   F por La Calleja, G por Medellín, H por casa, I por arriendo y K por 349999999.
   Elegir Preseleccionado en la decisión de A y pulsar su **Guardar**; volver a
   Buscar coincidencias y comprobar que la decisión permanece. No debe aparecer
   puntuación Gemini ni iniciarse una evaluación.

4. **Gemini válido y error controlado, sin consumo.** En Clientes abrir **Demo
   Gemini correcto** y pulsar **Evaluar con Gemini**. Esperar a finalizar: las cinco
   publicaciones deben mostrar **85 / 100**, explicación **SIMULADO** y evidencias;
   C y L siguen pendientes. Pulsar otra vez: debe reutilizar la caché y no añadir
   intentos en `simulaciones.jsonl`. Abrir **Demo Gemini error** (mismos criterios,
   preferencia de baños `9`) y pulsar **Evaluar con Gemini**. Debe indicar límite
   de uso, conservar cinco candidatos deterministas y no mostrar puntuaciones
   ficticias ni reintentar automáticamente. Recargar no hace otra llamada.
   El archivo de transporte tendrá dos líneas iniciales: HTTP simulado 200 y 429.

## Pendientes y riesgos antes de Google Cloud

- Falta preparar/validar imagen y arranque del servicio web y persistencia durable
  de sus cuatro bases. El filesystem efímero de Cloud Run no sustituye esta
  persistencia; el adaptador de snapshots de Jobs no demuestra por sí solo un
  protocolo seguro de coordinación entre web y Jobs.
- Validar IAP real: audiencia del servicio, login con las cuentas autorizadas,
  cuenta no autorizada, revocación IAM, Origin de la URL definitiva y todas las
  entradas directas/alternativas. Las firmas y JWKS usados aquí son sintéticos.
- Validar posteriormente snapshots/locks/permisos Cloud Storage y recuperación en
  Cloud Run, operación Wasi sin intervención, cambios reales en los tres portales,
  bloqueos/OTP y Scheduler. Todo ello quedó sin ejecutar en esta tarea.
- Modelo, disponibilidad, facturación y una respuesta auténtica de Gemini no se
  verificaron ahora. Los informes históricos contienen evidencia anterior; no se
  presenta como una ejecución nueva ni como garantía del proveedor actual.
- Medir tokens, almacenamiento, alojamiento y frecuencia: objetivo menor de
  US$10/mes aún no acreditado. Timeout/interrupción real puede tener consumo
  desconocido. BackgroundTasks depende de la vida del proceso y del lease de diez minutos.
- La semilla geográfica es limitada: barrio no reconocido queda pendiente, no
  se descarta por inferencia. Las preferencias de antigüedad siguen pendientes
  cuando no hay años comparables. Son limitaciones vigentes, no regresiones.

## Archivos y Git

Se añaden el lanzador aislado `consola/tools/revision_local.py`, el ensayo
`consola/tests/test_revision_local.py` y este informe; se enlaza desde `docs/README.md`.
Los datos y capturas permanecen ignorados en `.tmp/`. No cambian reglas de
negocio, arquitectura, rutas operativas ni datos reales. Sin conflictos, commit,
tag, merge, push o despliegue. HEAD y versión permanecen en la base evaluada.
