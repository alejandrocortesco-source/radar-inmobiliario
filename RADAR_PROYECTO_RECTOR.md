# Radar Inmobiliario — documento rector v0.8

La especificación funcional del usuario de 3 de noviembre de 2026 gobierna esta entrega. El producto acompaña el trabajo de Mónica con unos 30 clientes activos. Debe permanecer sencillo y de bajo mantenimiento; el objetivo de operación inferior a US$10/mes está **pendiente de validación de consumo y alojamiento**, no es una garantía.

## Ampliación vigente v0.8 — Wasi (8 de noviembre de 2026)

La entrega funcional v0.8 corresponde a `4781daeb9adefc310028d40dcec88795657530eb`, identificada mediante el tag anotado `v0.8.0`. El desarrollo y los commits nuevos se realizan en `develop`, según la política única [GIT_WORKFLOW.md](GIT_WORKFLOW.md). La rama remota `v0.6` queda histórica, sin nuevos commits; las rutas `/v0.6/`, `/v0.4/` y `/consola/` permanecen. El commit documental de organización no incrementa la versión funcional ni integra la entrega en `main`.

La revisión funcional y sus pruebas constan en `scraper/docs/VALIDACION_WASI.md`. La autorización inicial del 9 de noviembre limitó esa revisión al commit local; una solicitud posterior autorizó y completó su push a `origin/v0.6`. La solicitud de organización posterior autoriza publicar exclusivamente `develop` y `v0.8.0`, sin merge a main, despliegue ni GitHub Release. Estas acciones y autorizaciones son distintas.

La solicitud de esta fecha amplía el alcance a la red inmobiliaria de Wasi y al login automático normal con secretos externos. Se desarrolló en el checkout entonces llamado `v0.6`, base funcional comprobada `9db935a` (anunciantes v0.7), conservando cambios locales. Aquella solicitud no autorizaba merge, push, despliegue ni publicación. Las autorizaciones de sincronización descritas en hitos históricos no se trasladan a esta entrega.

El catálogo de negocio permanece único, con los campos actuales. Se añade almacenamiento técnico `wasi.sqlite` reutilizando el motor incremental; el adaptador integrado presenta ambas fuentes a las vistas, API, filtros, CSV, anunciantes, contadores y matching existentes. La identidad UUID5 por fuente/código original permanece intacta. No se fusionan anuncios entre portales. Enlaces y decisiones usan UUID; un código compartido necesita fuente explícita en la API.

«Agregar fuente» conserva la URL filtrada de Metrocuadrado y añade configuración de controles Wasi dependientes. Se exige ciudad y localidad o zona/barrio, con IDs/etiquetas reales del portal. La URL general no identifica la búsqueda. Cada conjunto de filtros tiene una identidad canónica y configuración versionada en la base auxiliar; editar conserva revisiones y procedencias anteriores y no provoca ausencias masivas. Guardar/editar no captura; el dashboard conserva exactamente cuatro secciones.

Wasi recorre todas las páginas sin límites de resultados, deduplica entre búsquedas y reutiliza las decisiones incrementales, historial y checkpoints. Mismo precio con ficha fiable no abre detalle; nuevos, cambios, conflictos o incertidumbre requieren revisión conservadora. No hay refrescos por fecha. COP sigue siendo la única moneda. Las ausencias se aíslan por fuente/búsqueda y solo se aplican después de dos ejecuciones completas y exitosas. Capturas fallidas no sustituyen la última ficha fiable. Desconocidos permanecen desconocidos con estados de campo `absent/error` separados.

Las credenciales entran por entorno o archivos protegidos externos; Cloud Run utilizará Secret Manager y la identidad del Job. No se persiste sesión: cada Job puede iniciar sesión y reutiliza el contexto durante la ejecución, sin depender de una sesión manual. CAPTCHA, rechazo, OTP o bloqueo detienen la ejecución sin confirmar ausencias. No se capturan datos de la cuenta ni mensajes de WhatsApp que incluyan identidad de Mónica; solo contactos publicados con procedencia.

`scraper/job.py` y `Dockerfile.jobs` preparan extracción sin FastAPI. El adaptador de snapshots Cloud Storage conserva bases/checkpoints/configuración y excluye secretos; utiliza precondiciones de generación y lock remoto, con restauración en disco local y guardados periódicos. No se monta SQLite sobre FUSE. Horario propuesto a las 00:00 `America/Bogota`, dos días configurables; no se activó Scheduler. Sheets continúa como adaptación futura, sin migración ni segundo modelo de negocio.

El 9 de noviembre se comprobó el login automático local con archivos privados externos y el flujo normal «Usar aquí» autorizado por el usuario. Se corrigieron esperas de controles, contadores, fichas, contactos y galerías contra el comportamiento real; las regresiones usan exclusivamente bases sintéticas. La búsqueda autorizada de La Carolina usa el control textual de título junto con Bogotá / Usaquén, apartamento y venta: no equivale a un barrio inventado ni garantiza cubrir todos sus anuncios. El resultado operativo se registra en el [informe de verificación](scraper/docs/VALIDACION_WASI.md). La operación desatendida queda pendiente hasta probar login real y una ejecución posterior desde Google Cloud sin intervención, en otra etapa autorizada. Consumo y presupuesto siguen pendientes de medición. Configuración, comandos, recuperación y límites: [guía Wasi](scraper/docs/WASI.md).

## Ampliación v0.7 — anunciantes

El hito anterior v0.7 se desarrolló sobre la rama v0.6 (base `a2eae95`) y quedó cerrado en `9db935a`. Conservó las rutas `/v0.6/` y `/v0.4/`, el dashboard, los formularios, las búsquedas y las reglas/caché de matching y Gemini. Su autorización histórica de sincronización no autoriza publicar la entrega v0.8.

El catálogo completo añade Anunciante; la ficha del inmueble, la ficha del cliente y los resultados históricos de matching acceden al mismo panel adaptable. La agrupación usa igualdad literal del nombre capturado, incluyendo espacios, tildes y mayúsculas; nombres vacíos no forman un grupo. Los originales públicos `companyName` tienen prioridad sobre el nombre normalizado para conservar diferencias. No se crean identidades persistentes ni se deducen equivalencias.

Los contactos se presentan por combinación publicada con procedencia hacia sus anuncios; un contacto no se atribuye a todos los inmuebles. Solo se generan enlaces validados, sin completar indicativos. Abrir el panel no llama ni envía mensajes. Los enlaces explícitos de WhatsApp son parte de esta consulta; no se incorpora mensajería automática. Otros inmuebles consulta todo el catálogo, excluye el anuncio de origen y pagina de 12 en 12. CSV añade cinco columnas conservando filtros, orden, COP y protección contra fórmulas. Ver `consola/docs/V07.md` para datos disponibles, arquitectura y validación.

## Experiencia implementada

La entrada de la consola es `/v0.6/`. Tiene exactamente cuatro secciones:

1. **Oportunidades recientes**: resumen por cliente, necesidad, pendientes y última actividad. Prioriza clientes con pendientes, luego actividad más reciente; muestra hasta seis clientes activos. La actividad se integra aquí.
2. **Estado del catálogo**: total, última actualización exitosa global en hora de Colombia, nuevos, actualizados (clasificación de cambios de precio existente) y ausentes de al menos una búsqueda. Nuevos y actualizados usan la última ejecución completada por búsqueda de v0.5. La actividad de actualización se integra aquí. Una ausencia no confirma retiro ni venta; el inmueble puede seguir activo en otra búsqueda.
3. **Agregar fuente**: URL de búsqueda de Metrocuadrado o controles dependientes de Wasi y nombre, con identidad canónica, validación y deduplicación. Permite revisar las búsquedas registradas, editar filtros Wasi y eliminarlas con confirmación. Eliminar quita únicamente su selección auxiliar para futuras ejecuciones; conserva inmuebles, procedencias e historial y no cambia las fuentes de ejecuciones en curso o reanudadas. No extrae al guardar ni al eliminar. Metrocuadrado las incorpora con `scrape --fuentes-registradas`; Wasi usa `wasi_run.py scrape` y el Job puede procesar ambas fuentes.
4. **Nuevo cliente**: acceso al formulario independiente de cliente y necesidades; permite seleccionar uno existente. Confirmar guarda una oportunidad y abre la ficha del cliente mientras se evalúan candidatos.

**No hay quinta sección.** Las referencias históricas a interfaces anteriores no añaden secciones al dashboard.

La lista `/v0.6/clientes` usa un Content Switcher Activos/Inactivos. Cada ficha `/v0.6/clientes/{id}` agrupa datos, oportunidades, edición, recálculo, tabla ordenable y decisiones. Una oportunidad abierta es el caso habitual; se conservan varias para excepciones e historial. Inactivar un cliente no borra ni cierra sus oportunidades. Cerrar una oportunidad conserva su información y suspende sus cálculos automáticos.

El catálogo completo permanece en `/v0.4/` y la interfaz histórica en `/consola/`. Se conservan fichas, filtros rápidos, historial, comentarios, geografía y CSV. Desde v0.6 se recuerda en sessionStorage la última URL del catálogo, incluidos filtros y página. La interfaz técnica del scraper continúa en `/` por compatibilidad.

## Reglas de necesidades y matching

**Decisión definitiva de moneda:** el sistema solo utiliza pesos colombianos (COP), ahora y a futuro. Todos los precios y presupuestos se interpretan en COP. La moneda no se solicita, verifica ni usa como condición de comparación, incluso en registros históricos con el campo vacío o con otra etiqueta. No hay conversiones ni soporte multimoneda. Los campos históricos se conservan como metadatos de origen para evitar migraciones y cambios de esquema innecesarios; no determinan el significado del importe.

El presupuesto se comprueba directamente sobre el precio numérico de la operación solicitada: mínimo incluido cuando se especifica y máximo incluido. Para 770.000.000–880.000.000 COP, 770.000.000, 800.000.000 y 880.000.000 pasan; 769.000.000, 881.000.000, 7.500.000.000 y 8.000.000.000 se excluyen aunque falte moneda u otro dato. Un precio ausente, no numérico, no finito o no positivo permanece desconocido y pendiente de verificar, sin convertirse en cero; cualquier incumplimiento estricto conocido sigue excluyendo el anuncio.

Compra/arriendo, tipo, ciudad, barrios múltiples y presupuesto máximo son requeridos en las nuevas oportunidades v0.6. El mínimo de presupuesto es opcional. Habitaciones acepta mínimo/máximo opcionales; ambos límites especificados son estrictos. Área es un rango opcional flexible; no sustituir entre construida, privada y publicada. Baños, parqueaderos y antigüedad son preferencias opcionales. Observaciones no son requisitos estrictos.

Se conserva el JSON de oportunidades históricas, incluyendo zonas y el antiguo campo `preferencias`. Las zonas históricas siguen siendo editables y alternativas de ubicación. Su existencia no obliga a reescribir datos. El significado vigente del motor aplica a todas las oportunidades: los límites de habitaciones son estrictos aunque una oportunidad histórica los marcara como preferencia; las características secundarias son flexibles aunque antes fueran indispensables.

El motor determinista es la primera capa. Un incumplimiento estricto conocido descarta; un dato necesario desconocido conserva el candidato como **Pendiente de verificar**. Los barrios son alternativas, no condiciones simultáneas. Gemini no amplía barrios ni presupuesto ni convierte pendientes en confirmaciones.

La segunda capa usa el adaptador REST real `oportunidades/gemini.py`, JSON Schema, Pydantic, comprobación de IDs y evidencias contra los hechos enviados. Solo recibe necesidades y hechos de candidatos, sin identidad/contacto del cliente. La explicación es orientativa y requiere revisión humana; la validación estructural no garantiza que toda redacción de un modelo sea correcta. La puntuación solo ordena.

Las instrucciones de Gemini establecen COP como única moneda y prohíben solicitar o verificar moneda y convertir importes. La versión de instrucciones y la huella del candidato incorporan esta política para no reutilizar evaluaciones anteriores incompatibles. Esta decisión no activa ni configura Gemini.

Cada evaluación se reutiliza por hash de necesidades, datos relevantes del candidato, modelo y versión de instrucciones. Por defecto se evalúan hasta 20 candidatos deterministas por oportunidad, en una única llamada para los no almacenados en caché. El máximo configurable es 30. El resto sigue visible sin evaluación de IA. Error, timeout, respuesta bloqueada/incompleta o configuración ausente conservan los candidatos deterministas y muestran la limitación. No hay reintentos de red automáticos; Mónica puede recalcular para reintentar fallos, conservando las evaluaciones válidas intactas.

Disparadores: guardar/modificar oportunidad mediante los formularios y API; terminar una ejecución exitosa del scraper; recálculo manual desde la ficha. Las tareas HTTP se ejecutan después de enviar la respuesta mediante BackgroundTasks. Un lease en SQLite evita duplicados concurrentes; los cambios recibidos durante una evaluación dejan una solicitud pendiente para procesar al terminar. El progreso se consulta desde la ficha. No hay cola externa ni servicio adicional.

Las decisiones por oportunidad/inmueble son **Pendiente, Preseleccionado y Descartado**. Se almacenan aparte del matching y se conservan al recalcular o desaparecer un candidato. La ficha permite cambiar también las decisiones históricas. Preseleccionar no comunica ni envía nada.

## Arquitectura

La distribución de código, documentación, archivos privados, datos y temporales se mantiene según [el mapa de archivos](docs/ESTRUCTURA.md). El [índice documental](docs/README.md) separa guías vigentes e informes históricos sin mover los módulos ni sus rutas operativas.

Playwright propio, FastAPI/Jinja2, JavaScript nativo, SQLite. `consola/v06.py` adapta HTTP; `consola/inicio.py` proyecta resúmenes; `oportunidades/matching.py` contiene reglas puras; `automatizacion.py` coordina; `seguimiento.py` define un contrato y adaptador SQLite; `gemini.py` encapsula el proveedor. La base auxiliar predeterminada es `metro-consola.sqlite` junto al catálogo; `RADAR_CRM_DB` permite elegir otra base, siempre distinta de `METRO_DB`.

Las tablas nuevas `radar_clientes_estado`, `radar_decisiones`, `radar_matching`, `radar_matching_pendiente` y `radar_gemini_cache` se crean de forma aditiva en la primera escritura. No se cambia la migración 1 de clientes/oportunidades ni el user_version ni el catálogo. Los adaptadores permiten una implementación futura en Sheets; esta entrega no migra datos. v0.8 prepara Cloud Run Jobs y snapshots durables; despliegue, operación desatendida real y medición de costos permanecen pendientes.

La presentación sigue patrones oficiales de Carbon: cuadrícula de hasta 16 columnas, espaciado de 8 px y subdivisiones, tiles sin sombras, tablas compactas, labels visibles, contraste, foco y controles nativos. Conserva tonos tierra y reserva el botón principal para confirmar o recalcular. No instala Carbon ni un framework.

## Configuración y límites

Ver `consola/docs/V06.md`. La clave de Gemini no está configurada en el entorno de validación; el transporte, esquema, caché y errores se prueban con un servidor HTTP simulado, sin llamadas facturables. La evaluación contra el proveedor real y el presupuesto mensual quedan pendientes de credenciales y medición.

Las tareas BackgroundTasks viven en el proceso web. Si se interrumpe, pueden no terminar; la ficha mantiene el fallback determinista y permite reintentar. El lease caduca a los 10 minutos. No se introduce una cola distribuida para el volumen actual. La pasada posterior al scraper procesa oportunidades secuencialmente para contener llamadas.

## Propósito y conceptos de negocio

La herramienta es privada y acompaña principalmente a personas que buscan vivienda para sí mismas. Mónica necesita ahorrar tiempo al registrar necesidades, actualizar el catálogo, comparar inmuebles y revisar opciones para compartir personalmente. La escala prevista es de cientos o algunos miles de anuncios; prevalecen simplicidad y mantenimiento frente a una escalabilidad hipotética. No convertirla en marketplace, portal público ni CRM corporativo.

Cliente es la persona atendida; oportunidad es una necesidad concreta, con varios barrios como alternativas. Búsqueda de origen es la URL del portal que amplía la cobertura del catálogo y no equivale a los filtros de una oportunidad. Inmueble es un anuncio con identidad, procedencia y trazabilidad. Coincidencia es su evaluación para una oportunidad; la decisión comercial de Mónica se almacena de forma independiente. El catálogo completo es secundario a la revisión de clientes y sus coincidencias.

## Historia, ramas y referencias

- El cierre funcional de v0.5 corresponde a `291ce82b6ee83884d5501630b5da9d5e47dd8c61`, originado en la rama histórica `v0.4` y conservado en `release/v0.5`.
- `main` conserva su función prevista de referencia estable y su contenido actual; esta tarea no integra v0.8 allí. Todo nuevo desarrollo se realiza en `develop`; si se está en una rama histórica, detenerse e informar según [GIT_WORKFLOW.md](GIT_WORKFLOW.md). `master` local no equivale a `main`. `v0.4`, `release/v0.5`, `feat/consola-v0.3` y respaldos conservan su historia.
- La referencia remota histórica `v0.6` conserva la entrega funcional `4781dae`, sin nuevos commits. El tag local histórico `v0.5.0` apunta a `a52159c`, distinto del cierre funcional `291ce82`; no se mueve ni se publica por esta organización. La integración con el commit remoto `069fc89` conserva su historia de documentación, actualizada según la implementación comprobada, las cuatro secciones aprobadas y el objetivo menor a 10 USD/mes.
- Los reportes de pruebas o de actualizaciones anteriores describen esas ejecuciones; no son verificaciones nuevas ni valores fijos del dashboard. Antes de cada cambio contrastar instrucciones, código, datos y pruebas pertinentes.
- El sistema de archivos efímero de Cloud Run no será el almacenamiento definitivo cuando se aborde el despliegue futuro. Sheets sigue siendo el objetivo previsto, sin migración integral en esta entrega.

Referencias técnicas: `scraper/README.md`, `scraper/docs/INCREMENTAL.md`, `catalogo/README.md`, `oportunidades/README.md`, `consola/README.md` y `consola/docs/V06.md`. Este documento es la referencia de decisiones; los README explican la implementación real. Actualizarlo por decisiones aprobadas o hitos verificados, sin confundir rama y versión funcional.
