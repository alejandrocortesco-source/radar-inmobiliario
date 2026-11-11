# Matching manual y novedades

> Estado actual: validación auténtica completada con esquema estructural inline y validación Pydantic completa local. Ver [aislamiento, cuatro solicitudes y consumo reportado](GEMINI_AISLAMIENTO.md). Los bloqueos e informes anteriores se conservan como historia.

Implementación local del 11 de noviembre de 2026, sobre `develop`, base `91802de`. Conserva rutas, reglas deterministas, evaluación individual antes de agrupar, identidades v0.10, áreas separadas, COP y decisiones comerciales. No cambia el dashboard de cuatro secciones ni la infraestructura.

## Acciones por oportunidad abierta de un cliente activo

- **Buscar coincidencias** vuelve a consultar todo el catálogo aunque no cambien las necesidades. Actualiza la fecha de búsqueda y conserva decisiones. No llama a Gemini.
- **Evaluar con Gemini** refresca primero el matching. La vista previa informa total, selección determinista (20 por defecto, máximo 30), resultados en caché, candidatos que necesitan evaluación y posible consumo. El clic constituye la solicitud; no hay otro diálogo. Un cambio desde la vista previa devuelve 409 sin llamar a Google: hay que revisar los conteos actuales.
- La evaluación realiza como máximo una generación con los candidatos seleccionados que no tienen caché vigente. La selección no cambia al ordenar la tabla. Si todo está vigente, se informa reutilización y cero solicitudes. Sin configuración o candidatos se explica el motivo sin llamar.
- La puntuación solo ordena preferencias; no es probabilidad ni prueba de cumplimiento. Los requisitos desconocidos siguen pendientes. Un error de Gemini conserva los resultados deterministas.

Guardar clientes u oportunidades (HTML actual, histórico o API), reactivar, recalcular, terminar cualquiera de los tres scrapers, consultar progreso y abrir/ordenar páginas nunca invocan el proveedor. Tener `GEMINI_API_KEY` no cambia esa separación. `recalcular` y `recalcular_seguro` son exclusivamente deterministas; `solicitar_gemini` reserva la evaluación manual y devuelve una tarea sobre su versión de datos.

## Persistencia y concurrencia

`SeguimientoSQLite` conserva la caché y añade `radar_novedad_base`, `radar_novedades`, `radar_novedad_alias`, `radar_novedad_eventos` y `radar_gemini_ejecuciones` en la base auxiliar. No cambia las tablas del scraper ni la migración de clientes/oportunidades. El protocolo documenta los métodos para sustituir el adaptador.

La primera búsqueda registrada establece una línea base, tanto para oportunidades existentes como nuevas; no etiqueta todos los resultados. En la primera consulta posterior a actualizar la app también se inicializa esa línea base si faltaba. Después, una incorporación elegible genera **Nuevo**, contador y fecha de detección persistentes. La relación conserva primera detección, última aparición, número de apariciones, tipo (`inicial`, `nueva`, `reaparicion`), presencia y fecha de visto. Una tabla de eventos conserva cada detección, desaparición, reaparición y marcado, sin borrar el historial.

Las identidades de grupo y sus publicaciones existentes son alias de seguimiento, sin establecer asociaciones nuevas. Cambiar representante, añadir una publicación a un grupo confirmado, ordenar o puntuar no crea una novedad. **Marcar novedades como vistas** envía únicamente los tokens de las novedades mostradas de esa oportunidad. Una reaparición posterior no se borra con un formulario anterior. Recargar no marca como visto.

Cada clic lleva un UUID idempotente. La reserva transaccional impone una sola ejecución activa por oportunidad y evita repetir ese UUID incluso tras un fallo. La caché se consulta antes de enviar; una segunda solicitud con datos intactos no genera consumo adicional. Los cambios durante una ejecución no se encolan: se guarda el resultado asociado a su huella original, se ocultan evaluaciones que ya no están vigentes y se avisa que hace falta otro clic. Las tareas pendientes heredadas se descartan para matching, nunca autorizan llamadas.

Una tarea vive en el proceso HTTP. Si se interrumpe, no se recupera automáticamente. A los diez minutos se muestra como interrumpida y una nueva solicitud explícita puede reservar otra ejecución. El consumo de una tarea interrumpida o con timeout puede ser desconocido.

## Privacidad y observabilidad

Gemini recibe hechos estructurados y necesidades, sin nombre, teléfono, anunciante, dirección, contactos ni enlaces. Observaciones, descripciones y características en texto libre se conservan localmente y se omiten del envío, porque pueden contener datos personales. Esto limita la evaluación a preferencias estructuradas (baños, áreas por tipo, parqueaderos y demás datos disponibles). La versión de instrucciones `v06-4-manual-estructurado` invalida caché de instrucciones anteriores; no se borra su historial.

Cada ejecución persiste fecha UTC, oportunidad, UUID, huellas, total de coincidencias, seleccionadas, reutilizadas, enviadas, solicitudes intentadas, duración, resultado, HTTP, modelo solicitado y versión devuelta cuando Google los informa. No registra claves, prompts ni respuestas crudas. Conserva evaluaciones ya validadas para su versión. La ausencia de métricas significa que Google no las reportó, no cero consumo.

Se distinguen configuración, ausencia de candidatos, timeout, límite de uso HTTP 429, error HTTP del proveedor, conexión y respuesta inválida/incompleta. No hay reintentos de red. `usageMetadata` guarda los contadores de entrada, salida, razonamiento, caché, herramientas y total que estén disponibles. `totalTokenCount` ya incluye razonamiento; no se le vuelven a sumar sus componentes. Los tokens de caché ya están incluidos en entrada. La caché local evita generaciones completas y es distinta de la caché de Google.

Estos datos permiten medir consumo; no garantizan el objetivo global inferior a US$10/mes ni incluyen una estimación de precios.

## API explícita

| Método y ruta | Comportamiento |
| --- | --- |
| POST `/api/oportunidades/{id}/buscar` | Actualiza solo matching |
| GET `/api/oportunidades/{id}/gemini` | Vista previa sin red: `huella`, total, límite, seleccionados, reutilizadas, necesitan_evaluacion y aviso |
| POST `/api/oportunidades/{id}/gemini` | Cuerpo `{"solicitud":"UUID-NUEVO","huella":"HUELLA-DE-LA-VISTA-PREVIA"}`; 202, con `aceptada=false` si ya está reservada/duplicada; 409 si cambió la versión o no está activa |

Las rutas HTML `/v0.6/oportunidades/{id}/recalcular`, `/gemini` y `/novedades/vistas` usan las mismas reglas. La ruta histórica de recálculo se conserva. El GET de progreso no inicia tareas.

## VALIDACIÓN REAL CON GEMINI

Es optativa, aislada, fuera de pytest y desactivada en CI. La documentación oficial se verificó el 11 de noviembre de 2026: [modelos disponibles](https://ai.google.dev/gemini-api/docs/models), [Gemini 3.8 Flash](https://ai.google.dev/gemini-api/docs/whats-new-gemini-3.8), [GenerateContent, configuración y métricas](https://ai.google.dev/api/generate-content) y [respuestas estructuradas](https://ai.google.dev/gemini-api/docs/structured-output). El modelo predeterminado `gemini-3.8-flash` continúa listado como estable; la disponibilidad para una cuenta concreta solo queda probada al obtener respuesta. Se conserva REST `v1beta/models/{model}:generateContent`, `maxOutputTokens=12000`, `thinkingConfig.thinkingLevel=LOW` para Gemini 3, timeout de 25 segundos por operación de red y 5 segundos para conexión, sin muestreo adicional ni reintentos. La declaración actual usa `responseMimeType=application/json` y `responseJsonSchema=esquema_proveedor()`: esquema estructural inline, manteniendo íntegra la validación local. Fue aceptada por el proveedor y completó el recorrido aislado; [evidencia y límites](GEMINI_AISLAMIENTO.md). Consultar de nuevo esas fuentes antes de ejecutar en otra fecha/modelo. No se incorporan tarifas al código.

Con una credencial autorizada inyectada como `GEMINI_API_KEY` en el entorno protegido del proceso (sin pegarla en chat, argumentos, archivos versionados ni capturas), ejecutar desde la raíz:

```powershell
.\.venv\Scripts\python.exe consola/tools/validar_gemini_real.py --ejecutar
```

Sin `--ejecutar` solo informa que no se ejecutó. Sin clave o con `CI` definido termina sin red. El programa crea una carpeta única `.tmp/gemini-real-UUID/`, ignora todas las rutas de bases operativas y usa una oportunidad y tres publicaciones sintéticas: dos elegibles (una sin habitaciones) y otra con presupuesto excedido. Hace exactamente una generación como máximo, con dos candidatos y sin scraper. Ante error guarda evidencia saneada y termina sin reintentar.

Si obtiene respuesta válida, verifica persistencia, requisitos pendientes, exclusión por presupuesto, repetición desde caché con cero solicitudes adicionales y la presentación FastAPI/Jinja real. Guarda `crm.sqlite`, `ficha.html` y `evidencia.json` localmente. La evidencia incluye métricas reportadas, modelo/versión, resultado y verificaciones, sin clave ni prompt. Una salida no exitosa no acredita validación real completa; un timeout puede haber consumido aunque no tenga métricas. No repetirlo automáticamente.

El 11 de noviembre de 2026 no se realizó generación real: `GEMINI_API_KEY` no estaba disponible en el proceso. Se comprobó el bloqueo sin bandera y sin credencial. El recorrido con respuesta auténtica y su consumo permanecen pendientes. Las pruebas simuladas de regresión no sustituyen esa validación.

## Regresión

Las suites completas de consola, catálogo y scraper se ejecutan en procesos separados con bases sintéticas según [V06](V06.md#pruebas). `consola/tests/test_gemini_manual.py` cubre cero llamadas automáticas con clave, búsqueda sin editar necesidades, migración y persistencia de novedades, agrupaciones existentes, reapariciones, idempotencia/concurrencia, caché/invalidez, privacidad, fallos y navegación en 1440×900, 768×1024 y 390×844. Las capturas de esta tarea quedan en `.tmp/gemini-manual-20261111-browser/`.

Los conteos de V06 son históricos. No se usaron bases operativas, extracciones reales, push, merge, tag ni despliegue.

### Resultado de esta entrega, 11 de noviembre de 2026

| Verificación ejecutada | Resultado |
| --- | --- |
| Suite completa de consola, incluido Chromium | 322 aprobadas (194,48 s) |
| Suite completa de catálogo | 247 aprobadas (8,49 s) |
| Suite completa de scraper, sin extracciones reales | 121 aprobadas (67,21 s) |
| Total de casos de las tres suites | **690 aprobadas** |
| Repetición específica sobre los últimos ajustes de Gemini/novedades y v0.6 | 49 aprobadas (35,62 s); no se suman de nuevo al total |
| Compilación de módulos modificados y validador | Correcta |
| Enlaces locales de documentación y `git diff --check` | Correctos |
| Generación auténtica de Gemini | No ejecutada: falta credencial en el proceso; consumo real no medido |

Las ejecuciones con sockets y Chromium se realizaron fuera del sandbox usando los mismos directorios sintéticos `.tmp/gemini-20261111-*`. El primer intento dentro del sandbox quedó bloqueado y se interrumpió, sin contabilizarlo como aprobado. La primera pasada de consola tuvo tres expectativas antiguas del mensaje automático de Gemini, que se adaptaron a la nueva vista previa, y un fallo aislado del editor histórico; el editor pasó en la repetición dirigida y en la suite completa final, sin modificar su implementación. Permanece una advertencia de deprecación de `BlockingPortal` de Starlette/AnyIO.

Se inspeccionaron capturas de escritorio, tablet y móvil. Chromium comprueba foco, labels, estados, etiquetas persistentes tras recarga/orden, marcado como visto y ausencia de desbordamiento de página. La tabla conserva desplazamiento en su contenedor. Las respuestas simuladas prueban validación y métricas; no acreditan una respuesta auténtica de Google.

Archivos modificados/añadidos:

| Alcance | Archivos |
| --- | --- |
| Coordinación, persistencia y proveedor | `oportunidades/automatizacion.py`, `seguimiento.py`, `gemini.py`, `api.py` |
| HTTP y presentación | `consola/v06.py`, `consola/templates/v06/cliente06.html`, `_captura06.html`, `consola/static/v06.js`, `v06.css` |
| Pruebas y validador optativo | `consola/tests/test_v06.py`, `test_gemini_manual.py`, `consola/tools/validar_gemini_real.py` |
| Documentación | `RADAR_PROYECTO_RECTOR.md`, `README.md`, `consola/README.md`, `consola/docs/V06.md`, esta guía, `docs/README.md`, `oportunidades/README.md` |

Trabajo local en `develop`, sin conflictos; HEAD permanece en `91802debf6eb808b8360b917a0dd4c9ed1dbefef`. No se creó commit, tag ni publicación. Pendiente únicamente la prueba real optativa y su medición de consumo, siguiendo el comando anterior. El límite de gasto global no está garantizado. Las tareas manuales dependen del proceso web y los textos libres no forman parte de la evaluación remota.
