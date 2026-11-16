# Wasi: anuncios ProductFruits recurrentes y revisión privada

15/11/2026, America/Bogota. Solo clon independiente autorizado, rama
`codex/ejecuciones-manuales`, base `6d60b0a` limpia. Se conserva `aa260cc`, corrección
de Metrocuadrado que el usuario reporta probada en operación. No se repite scraping
real para esta entrega. Sin Gemini, Scheduler, cambios IAP/OAuth/IAM, push, merge o
tags Git. No se modifica el checkout original.

## Causa y solución

Los informes visuales privados previos confirmaron que el host externo puede
medir 1366x0 mientras el diálogo y su cierre siguen visibles. El selector antiguo
partía del host :visible y descartaba el anuncio. El DOM observado muestra también
una raíz `.productfruits--container-root` en la cadena del diálogo, hermana del
host vacío. No se deduce el contenido por el nombre del proveedor.

`wasi/overlays.py` reconoce solamente las raíces exactas observadas, el contenedor
`.pfruits-announcement-popup-container`, su diálogo descendiente
`.pfruits-announcement-popup-v3[role="dialog"]` y un único botón visible/habilitado
`button.modern-close-btn` con rol button y nombre accesible exacto `Close dialog`.
No exige caja visible al host. No depende del título, imagen o texto del anuncio.
Nunca pulsa Renovar con promoción, otros CTA, X arbitrarias ni cambia el DOM/CSS
para quitar la ventana. Los cambios JavaScript son observadores de clic/mutación.

Después del clic normal exige que desaparezca el diálogo anterior y que no quede
su fondo bloqueante. Después ensaya la accesibilidad del control de destino;
si hay un nuevo anuncio reconocido puede cerrarlo dentro del presupuesto. Un
diálogo que reutiliza el mismo nodo y no desaparece se considera persistente;
no se presume que sea otra promoción ni se clica indefinidamente.

Integración al terminar login, sesión reutilizada, acceso a la red, preparación de
filtros/Buscar, renovación y lectura del listado, Siguiente e interacciones de
fichas/galería/contactos. Los cierres de recuperación de fichas quedan limitados
a los paneles de lectura identificados, no a cualquier modal con una X.
Los controles de credenciales, destino, sesión, OTP/CAPTCHA y acceso permanecen.

## Límites y acciones sin duplicados

| Alcance | Límite |
| --- | --- |
| Anuncios consecutivos por intervención | 3 cierres / 6000 ms |
| Acumulado por pestaña del navegador (incluye su paginación y navegaciones) | 12 cierres / 30000 ms de manejo |
| Cada cierre y espera de desaparición | Hasta 1500 ms, recortado por el tiempo restante |
| Ensayo de interacción sin despacho | Hasta 1000 ms por intento |
| Intentos de interacción normal | 3, dentro del timeout existente |

Son constantes explícitas ajustables en el módulo. El presupuesto solo se consume
cuando hay anuncio/fondo reconocido; no introduce polling continuo, hilos o tareas
persistentes en navegador. No elimina límites de seguridad ni añade límites de
páginas/anuncios inmobiliarios. Los timeouts de carga/verificación existentes
siguen vigentes, aparte del presupuesto de cierre.

El observador de mutación del tbody se instala antes de la interacción, como antes.
Para el clic real se fija el mismo ElementHandle observado. Si el clic fue
despachado, no se repite por un timeout posterior: se continúa a comprobar renovación,
filtros, resumen, página, rango y total. Si la captura del despacho se pierde por
navegación/contexto destruido, falla de forma conservadora. Solo reintenta cuando
no se despachó y se cerró un anuncio reconocido, reevaluando el estado renovado.
Incluso un clic que la API da por terminado pero no llegó al botón se comprueba.

Se mantienen deduplicación, cobertura, checkpoints y las guardas de ausencias y
retiros. Una interacción no confirmada no se presenta como listado vacío válido.
Los máximos acotan anuncios recurrentes; no garantizan completar toda variante
futura ni autorizan eludir verificación de seguridad.

## Diagnóstico de variantes futuras

| Código | Significado / comportamiento |
| --- | --- |
| wasi_overlay_ambiguous | No hay un único cierre visible reconocido o hay varios diálogos; no se elige uno arbitrariamente |
| wasi_overlay_unclosable | Cierre deshabilitado/inaccesible, diálogo persistente o fondo residual; no se fuerza |
| wasi_overlay_limit | Se agotaron cierres o tiempo; no se continúa en bucle |
| wasi_interaction_blocked | Ventana desconocida o control no disponible; no se atribuye una causa sin evidencia |
| wasi_interaction_uncertain | No se puede confirmar el despacho; no se repite una acción que pudo completarse |

Los códigos/mensajes son fijos y saneados; no contienen texto comercial, datos de
cuenta, cookies, tokens, HTML o trazas Playwright. Los fallos del listado se
registran como listing_incomplete y se muestran usando el mecanismo existente.
No hay actualizaciones ni logs adicionales por anuncio inmobiliario. Un fallo de
anuncio en autenticación también conserva un diagnóstico fijo de listado antes
de detenerse. No se reescribe el historial existente.

## Pruebas aisladas

Toda la red interceptada, credenciales sintéticas y SQLite en `.tmp/`/tmp_path.
Archivo nuevo `test_wasi_announcements.py`: 27 pruebas, incluidas altura cero,
dos textos, raíz hermana, ausencia, oculto, deshabilitado, ambiguo, ventana ajena,
diálogo/fondo persistentes, tres anuncios consecutivos y límite al cuarto (también con transición diferida y fondo compartido),
presupuesto de página/tiempo, CAPTCHA sin cierre, aparición tardía antes del clic,
entre pointerdown/click y error posterior al despacho para Buscar y Siguiente.
Verifica que ambas acciones se ejecutan una sola vez. También prueba anuncios
nuevos tras login, al entrar a red y durante renovación/paginación, y dos capturas
incompletas del simulador sin tocar ausencias existentes (antes del primer
listado y tras guardar una página). El fixture anterior de Wasi se adapta a la
estructura confirmada; conserva sus escenarios de filtros y vacío.

Resultados nuevos de esta tarea (no se suman las repeticiones específicas):

| Comprobación | Resultado |
| --- | --- |
| Nueva suite de anuncios Wasi | 27 aprobadas, incluidas en la suite completa final |
| Suite completa final scraper, con Metrocuadrado y Fincaraíz | 171 aprobadas, 136,61 s |
| Suite completa consola y ejecuciones compartidas | 457 aprobadas, 277,21 s |
| Suite completa catálogo | 249 aprobadas, 9,90 s |
| Regresión final de ejecuciones y generaciones | 54 aprobadas, 20,33 s (subconjunto de consola) |
| pip check, compileall wasi/ejecuciones y git diff --check | Correctos |

La comprobación adicional de transición diferida detectó dos fallos de la primera
implementación: interpretaba como residual el fondo que estaba cargando otro
anuncio. Se añadió una espera acotada por desaparición del fondo **o** nuevo diálogo
reconocido y se volvió a ejecutar todo scraper y la regresión compartida de
ejecuciones/generaciones. Ambas pasan; el cierre persistentemente bloqueado sigue
fallando de forma segura. La consola completa y catálogo se ejecutaron antes de
este último ajuste local del manejador; no se presentan como repeticiones finales.
La primera imagen de esta tarea no se ejecutó y fue sustituida por la imagen final.

Única advertencia: deprecación conocida de BlockingPortal en Starlette/AnyIO.
La consola incluye Chromium sintético en escritorio, tablet y móvil. No cambió
presentación ni se abrió un portal real. Bases y resultados excluidos en
`.tmp/wasi-recurrent-20261115/` y `.tmp/wasi-recurrent-regression-*-20261115/`.
Comando por suite con PYTHONPATH raíz/scraper/consola/tests:
`.venv/Scripts/python.exe -m pytest --rootdir=. -o pythonpath= COMPONENTE/tests -q --basetemp=.tmp/wasi-recurrent-regression-COMPONENTE-20261115`.

El diff de `scraper/metro/` respecto al commit `aa260cc` es vacío: se conserva
literalmente la corrección de rutas y sus verificaciones de cobertura. Sus pruebas
de ambas rutas, JSON inválido, ausencia de avance, destacados repetidos y ausencias
se ejecutaron de nuevo dentro de la regresión. No se modifica Fincaraíz.

## Imagen final y componentes verificados

Runtime final: `48b22a05bfd869168839e124d9a43ceed91384c8`, posterior al commit
inicial de esta tarea `12543d2`. Ambos conservan `aa260cc` y el código de Metrocuadrado.
Build final `f733b2da-4194-488f-9feb-949fb28d4621`, SUCCESS, 15/11/2026
20:13:50–20:15:31 America/Bogota. Imagen construida:
`us-central1-docker.pkg.dev/radar-inmobiliario-co/radar/jobs:48b22a05bfd8`.

Imagen **efectiva final** de `radar-manual-review`:
`us-central1-docker.pkg.dev/radar-inmobiliario-co/radar/jobs@sha256:f70659597246158745994c6fe5efd8a33c459166c546b11f837b570e4c28519d`.

Digest idéntico en resultados Cloud Build, Artifact Registry y spec del Job,
Ready=True y observedGeneration igual a generation. Fijado por digest inmutable.
No se lanzó una nueva ejecución; no se infiere validación operativa por Ready.
El build usa el commit completo mediante RADAR_SOURCE_SHA y etiqueta OCI. La
etiqueta histórica source-sha del recurso Job se conserva y no identifica el
runtime actual; usar digest y el commit fuente acreditados por este informe.

Se construyó una imagen intermedia (`12543d2`, build
`bf5b9f60-230c-4818-a621-00c051023075`, digest
`sha256:5a758eece685637bc4724c25dbfcfb47b5a2ec58172f0ab323962b873888f19b`).
Fue configurada y sustituida sin ejecutarla. No es la imagen final para repetir.
Las dos actualizaciones afectaron solo a la imagen del mismo Job y su nonce
interno generado por Cloud Run, sin crear Jobs adicionales.

Comparación final contra el estado original de la tarea:

- Spec del Job idéntico salvo imagen/nonce. Se conservan cuenta de servicio,
  referencias de secretos, argumentos, entorno, una tarea/paralelismo 1,
  1 CPU/2 GiB, cero reintentos automáticos y timeout 10800 s.
- Web no reconstruida ni desplegada: spec, anotaciones de acceso y tráfico iguales.
  Producción permanece 100% en radar-verify-20261111. Tag privado conserva
  radar-wasi-overlay-20261113 sin porcentaje de tráfico de producción.
- Todos los demás Jobs tienen la misma spec. Lista de ejecuciones idéntica,
  todas cerradas: ninguna captura ni sesión diagnóstica nueva.
- Snapshot/control conservan exactamente las generaciones y MD5 del estado previo.
  El lock operativo continúa ausente (404). No se sustituyó ni restauró ningún dato.
- No se añadieron recursos permanentes, identidades, secretos o permisos. Único
  impacto adicional: dos builds/imágenes y sus fuentes/logs en recursos existentes.
  No se cambia Scheduler, Gemini ni autenticación.

Evidencia local excluida: `.tmp/wasi-recurrent-20261115/verification.json`,
`build.json`, `registry-image.json`, descripciones antes/después, logs de pruebas
y archivos `*-intermediate.json`. No se publican datos de control ni secretos.

**Wasi queda preparado para revisión, sin validación operativa nueva.** Solo la
captura real manual posterior con cobertura y guardado durable confirmados
permitirá acreditarla.

## Repetición manual autorizada al usuario

Abrir por IAP:
https://ejecuciones-review---radar-dvhqhy5u3q-uc.a.run.app/v0.6/ejecuciones

Comparte catálogo, snapshot, bloqueo, secretos e identidades con producción. No
se ha ejecutado esta prueba automáticamente.

1. Seleccionar únicamente Wasi · La Carolina (título), Bogotá · apartamentos en venta.
2. Iniciar una vez y conservar el enlace al seguimiento. Confirmar que obtiene
   listado y puede paginar; anuncios reconocidos deben cerrarse por su propio control.
3. Comprobar informe de cobertura, incidencias de listado/anuncios, contadores,
   cierre del Job y guardado durable confirmado. Si es parcial, conservar ID y
   código para diagnóstico; no repetir en bucle ni liberar bloqueos manualmente.
4. Solo la nueva captura real con cobertura completa y persistencia remota permite
   declarar Wasi validado en operación. Esta entrega no lo declara.

## Estado remoto previo

Consultas por `../cloud.ps1`, proyecto `radar-inmobiliario-co`, región `us-central1`.
Job revisión existente: jobs@sha256:890356e5be7562dab9bb9c510cab4f1883fbee6441ba781f1c91e0b15bd8025d.
Producción: radar-verify-20261111 al 100%; revisión privada radar-wasi-overlay-20261113
con tag ejecuciones-review, sin porcentaje de tráfico. Todos los Jobs cerrados,
control con siete ejecuciones terminales y lock operativo ausente (404).
Snapshot actual: generación 1794789630945131, MD5 xFW/MprN8CldA12yG9vt9Q==.
Control actual: generación 1794789646863528, MD5 BhjbskrPQSz8LQOX/9RqKw==.
No se restaura la generación histórica de ninguna entrega anterior.

## Reversión compatible

Sin procesos activos, devolver solo radar-manual-review al digest previo de esta
tarea. Esa imagen conserva Metrocuadrado; no volver a las imágenes anteriores a
su corrección. Reintroduce la limitación de cierre de Wasi, por lo que no acredita
operación desatendida. No restaurar bases/snapshot/control, retirar locks, cambiar
tráfico o web. No hay migración de datos.

```powershell
& ../cloud.ps1 run jobs update radar-manual-review --project=radar-inmobiliario-co --region=us-central1 --image=us-central1-docker.pkg.dev/radar-inmobiliario-co/radar/jobs@sha256:890356e5be7562dab9bb9c510cab4f1883fbee6441ba781f1c91e0b15bd8025d --quiet
& ../cloud.ps1 run jobs describe radar-manual-review --project=radar-inmobiliario-co --region=us-central1 --format="value(spec.template.spec.template.spec.containers[0].image)"
```


## Git y archivos

Commit local de runtime reproducible y un commit documental posterior al despliegue;
no hay publicación Git ni cambios en el proyecto original. Archivos de esta tarea:

- `scraper/wasi/overlays.py`: reconocimiento, presupuestos y clic observado.
- `scraper/wasi/auth.py`: puntos posteriores a acceso/login, conservando validaciones.
- `scraper/wasi/browser.py`: integración con Buscar, renovación, paginación y lectura.
- `scraper/wasi/scraper.py`: acceso/red, diagnóstico inicial y recuperación de paneles conocidos.
- `scraper/wasi/diagnostico.py`: códigos y mensajes fijos.
- `scraper/tests/test_wasi_announcements.py` y `fixtures/wasi_announcement.js`: pruebas nuevas.
- `scraper/tests/test_wasi.py`: fixture previo ajustado a la estructura observada.
- `scraper/docs/WASI.md`, `consola/docs/EJECUCIONES.md`, informe histórico de
  superposiciones y este informe: contratos, límites, pruebas y reversión.
- `CHANGELOG.md` y `docs/README.md`: registro e índice.


Cierre de Git: rama conservada, sin conflictos. El último commit documental solo
registra este despliegue y no cambia el runtime de la imagen. Se comprueba árbol
limpio; no hay push, merge ni tags Git. Los artefactos de `.tmp/` quedan excluidos.
