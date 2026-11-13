# Wasi: superposición al buscar — v0.12.3

Clon independiente Radar-CloudRun-20261111/repo, rama codex/ejecuciones-manuales.
Se conserva el trabajo previo. Autorización: corrección y despliegue de componentes
de revisión, sin ejecutar scraping real ni cambiar producción, IAP/OAuth o permisos.

## Causa y evidencia histórica

Ejecución 84cfe6b4-dc15-4f9d-bfb1-6b2e033e8040, Job radar-manual-review-45jxf,
Wasi run técnico 3. Autenticación confirmada 08:46:31 America/Bogota, 13/11/2026.
El diagnóstico SQLite registró que productfruits--container interceptaba el clic
normal en #advanced_search durante 45 segundos. No se conoce el contenido de esa
capa: no se presupone qué aviso, tutorial o formulario mostraba.
Resultado incomplete/Parcial, sin páginas, trabajos ni observaciones de listado.
La captura confirmó snapshot 1794577683941500 y terminó con exit(0), sin lock residual.
La comparación de snapshots anterior y posterior conservó exactamente las 68 filas
de properties y search_memberships, sin aplicar ausencias ni cambios de precio.

## Cambio implementado

Antes del clic en Buscar se comprueba la accesibilidad con un clic de prueba que
no envía la búsqueda. Si está interceptado, solo se reconoce ProductFruits y solo
se admite un único botón visible cuyo nombre accesible sea Close o Cerrar, con
sufijos dialog/window/ventana/diálogo opcionales. Nombres y rol se consultan en el
DOM real del momento; no se inventan clases de botones ni textos de la ventana.
Hay como máximo un clic de cierre normal y una comprobación posterior. Esperas de
preparación/cierre de hasta 2 segundos; clic de búsqueda de hasta 5 segundos. No
hay force, remoción de nodos, aceptación de avisos, cookies ni renovación de sesión.
La toma de sesión Wasi conserva exactamente su autorización operativa previa.

Si no hay cierre inequívoco o no despeja el botón, la búsqueda queda incompleta.
Los errores de esta etapa son códigos y mensajes fijos; no se copia el contenido
de la ventana ni la traza Playwright. Se mantiene la comprobación de cambio del
tbody después de pulsar Buscar, carga terminada, filtros efectivos, resumen y
cobertura/paginador. Una tabla vacía renovada y verificada es válida; una tabla no
obtenida no equivale a cero resultados. Se conservan las guardas de ausencias.

Radar recibe incidencias de listado separadas de incidencias de anuncios, páginas
verificadas, cobertura y un código técnico fijo. El informe muestra Listado no
obtenido: una ventana del portal bloqueó el botón Buscar cuando corresponde.
Las trazas SQLite no se vuelcan a la web. No se modifican informes históricos:
los nuevos campos aparecen en futuras ejecuciones con la imagen actualizada.
Sin cambios de esquema, migraciones, identidad, filtros o catálogo inmobiliario.

## Validación y límites

Wasi: 32 pruebas aprobadas. Ejecuciones: 43 aprobadas, incluida persistencia del
resultado parcial y renderizado con incidencias de listado=1 y anuncios=0, sin
filtrar texto crudo. Catálogo: 249 aprobadas. Suites completas: consola 457 aprobadas (311,54 s), catálogo 249 y scraper 132
(94,85 s). Las repeticiones específicas no se suman como pruebas distintas.
Pip check, compilación y git diff --check correctos; persiste la advertencia
conocida de BlockingPortal en Starlette/AnyIO.
Chromium sintético verifica escritorio, tablet y móvil, foco y overflow. La tabla
ancha conserva scroll propio. Se revisó la captura de error de listado en móvil.
El simulador de tabla vacía ahora representa la fila normal Sin resultados: así
hay renovación observable y se distingue de una tabla que nunca se actualizó.
Los primeros fallos de pruebas provenían de ese simulador y de pausas/timeouts de
prueba inferiores a los mínimos existentes; no se relajaron validaciones reales.

No se ha confirmado cómo es el control de cierre de la capa real de Wasi. Una
ventana sin botón inequívoco se conserva y se diagnostica: corresponde verificar
manualmente la siguiente captura. No se afirma que toda variante ProductFruits
se cierre. No se abrió Wasi ni se ejecutó scraping real, Gemini o Scheduler.

## Componentes, datos y reversión

Se requieren ambas imágenes, web y jobs. Antes de esta tarea radar-manual-review
usaba jobs@sha256:c41811d3c16e6cf71e374a4cad9e4f5d6b6c89b1c2bd3682406b92db791832e8.
Actualizar solo la web no cambia su scraper. Se actualiza únicamente ese Job de
revisión, conservando sus secretos, identidad, argumentos y límites operativos;
los Jobs Metrocuadrado, Wasi y Fincaraíz históricos permanecen sin cambios.
La imagen también incorpora la corrección de generaciones GCS ya validada en la
web: no se vuelve a depender de un Blob fijado a una versión histórica.

La revisión privada comparte snapshot, catálogo, bloqueo, secretos e identidades
con producción. Su URL no significa aislamiento. Producción permanece al 100% en
radar-verify-20261111. No se ejecuta el Job durante esta tarea.

Reversión: sin procesos activos, devolver radar-manual-review al digest anterior
y reasignar solo el tag privado a radar-central-reconcile-20261113-b. Conservar
los registros y snapshots actuales: no restaurar datos ni editar locks. El rollback
reintroduce la limitación del cierre y el adaptador anterior de Job; usar solo como
reversión operativa explícita. Los campos de control son aditivos y compatibles.

## Prueba manual posterior a la entrega

1. Entrar por IAP a Radar Central; comprobar v0.12.3 y las búsquedas actuales.
2. Seleccionar solo Wasi · La Carolina (título), Bogotá · apartamentos en venta e
   iniciar una ejecución. Esto opera sobre el catálogo compartido con producción.
3. Seguir el informe: si hay cierre reconocido, debe continuar a listado y fichas.
   Si la capa no es reconocible, debe quedar Parcial con diagnóstico de listado,
   sin aparentar un vacío válido ni marcar retiros.
4. Comprobar cierre, confirmación durable, referencia del nuevo Job y contadores.
   El resultado histórico anterior no cambia al desplegar la corrección.

## Imágenes construidas

Runtime: c70cce66951ec74717b7a5be068df4fdbefb9e78.
Ambos builds terminaron SUCCESS, sin ejecutar captura:

| Componente | Build | Imagen |
| --- | --- | --- |
| Web | 510c3151-7b7b-419c-b90a-a98d1c00c708 | web@sha256:00c9864c0ec2bbaa0de3188fffb70df083057b57cc4f39750a5a06a49575ce16 |
| Job manual de revisión | d4ba1b13-3222-4c09-ae8a-8cf7aa1ce05e | jobs@sha256:096dd89ccf155ad93d411ad91594cf8987db88f2b75fc01c6884f90f471a4c4e |

Prefijo de ambas imágenes: us-central1-docker.pkg.dev/radar-inmobiliario-co/radar/.
Confirmación final: radar-manual-review describe devuelve exactamente el digest Jobs
anterior de esta tabla. Se comparó toda la especificación antes/después: solo cambió
la imagen y client.knative.dev/nonce, identificador automático de Cloud Run. Todo
lo demás coincide, incluidos secretos, identidad, argumentos, variables, recursos,
paralelismo y timeout. El nonce hizo detener la comprobación estricta inicial;
se verificó la diferencia antes de continuar, sin ampliar el alcance del cambio.

Web privada: radar-wasi-overlay-20261113, 0% de tráfico de producción. Producción
conserva el 100% en radar-verify-20261111. La imagen del servicio se desplegó por
su digest exacto, con el tag privado existente ejecuciones-review. No se cambió
IAP/OAuth, IAM, secretos, Scheduler, recursos o programación de los otros Jobs.

URL privada verificada con sesión IAP (cabecera v0.12.3):
https://ejecuciones-review---radar-dvhqhy5u3q-uc.a.run.app/v0.6/ejecuciones
Sin sesión: 302 a accounts.google.com. No se comprobó otra cuenta.
La comprobación solo abrió Radar Central; no se seleccionó ni inició una captura.

Auditoría final: siguen las cuatro ejecuciones históricas del Job, todas cerradas;
no se lanzó ninguna nueva. El snapshot conserva generación 1794577683941500,
MD5 knEzP+PG1gvU3VjQ0zo+cA== y 51101388 bytes, idénticos a los anteriores a esta
tarea. El objeto de lock devuelve 404. No se restauraron ni sustituyeron bases.
La próxima captura real corresponde al usuario desde la revisión privada.

Git: runtime c70cce6, rama conservada codex/ejecuciones-manuales, sin conflictos,
push, merge o tags Git. El commit documental posterior solo completa esta evidencia;
no modifica las imágenes. Se conserva intacto el trabajo anterior.

Archivos de ejecución: scraper/wasi/browser.py, diagnostico.py y scraper.py;
scraper/metro/scraper.py (código fijo en evento de listado), ejecuciones/worker.py.
Presentación: consola/templates/v06/_ejecucion06.html y base06.html. Pruebas:
scraper/tests/test_wasi.py, fixtures/wasi_network.html y consola/tests/test_ejecuciones.py.
Versión/documentación: scraper/metro/__init__.py, README.md, CHANGELOG.md,
consola/docs/EJECUCIONES.md, docs/README.md y este informe.
