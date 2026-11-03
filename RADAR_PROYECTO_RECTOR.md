# Radar Inmobiliario — documento rector v0.6

La especificación funcional del usuario de 3 de noviembre de 2026 gobierna esta entrega. El producto acompaña el trabajo de Mónica con unos 30 clientes activos. Debe permanecer sencillo y de bajo mantenimiento; el objetivo de operación inferior a US$10/mes está **pendiente de validación de consumo y alojamiento**, no es una garantía.

## Experiencia implementada

La entrada de la consola es `/v0.6/`. Tiene exactamente cuatro secciones:

1. **Oportunidades recientes**: resumen por cliente, necesidad, pendientes y última actividad. Prioriza clientes con pendientes, luego actividad más reciente; muestra hasta seis clientes activos. La actividad se integra aquí.
2. **Estado del catálogo**: total, última actualización exitosa global en hora de Colombia, nuevos, actualizados (clasificación de cambios de precio existente) y ausentes de al menos una búsqueda. Nuevos y actualizados usan la última ejecución completada por búsqueda de v0.5. La actividad de actualización se integra aquí. Una ausencia no confirma retiro ni venta; el inmueble puede seguir activo en otra búsqueda.
3. **Agregar fuente**: URL de búsqueda de Metrocuadrado y nombre, normalización mediante la identidad existente, validación y deduplicación. No extrae al guardar. Las futuras ejecuciones pueden incluirlas con `scrape --fuentes-registradas`.
4. **Nuevo cliente**: acceso al formulario independiente de cliente y necesidades; permite seleccionar uno existente. Confirmar guarda una oportunidad y abre la ficha del cliente mientras se evalúan candidatos.

**No hay quinta sección.** Las referencias históricas a interfaces anteriores no añaden secciones al dashboard.

La lista `/v0.6/clientes` usa un Content Switcher Activos/Inactivos. Cada ficha `/v0.6/clientes/{id}` agrupa datos, oportunidades, edición, recálculo, tabla ordenable y decisiones. Una oportunidad abierta es el caso habitual; se conservan varias para excepciones e historial. Inactivar un cliente no borra ni cierra sus oportunidades. Cerrar una oportunidad conserva su información y suspende sus cálculos automáticos.

El catálogo completo permanece en `/v0.4/` y la interfaz histórica en `/consola/`. Se conservan fichas, filtros rápidos, historial, comentarios, geografía y CSV. Desde v0.6 se recuerda en sessionStorage la última URL del catálogo, incluidos filtros y página. La interfaz técnica del scraper continúa en `/` por compatibilidad.

## Reglas de necesidades y matching

Compra/arriendo, tipo, ciudad, barrios múltiples y presupuesto máximo son requeridos en las nuevas oportunidades v0.6. El mínimo de presupuesto es opcional. Habitaciones acepta mínimo/máximo opcionales; ambos límites especificados son estrictos. Área es un rango opcional flexible; no sustituir entre construida, privada y publicada. Baños, parqueaderos y antigüedad son preferencias opcionales. Observaciones no son requisitos estrictos.

Se conserva el JSON de oportunidades históricas, incluyendo zonas y el antiguo campo `preferencias`. Las zonas históricas siguen siendo editables y alternativas de ubicación. Su existencia no obliga a reescribir datos. El significado vigente del motor aplica a todas las oportunidades: los límites de habitaciones son estrictos aunque una oportunidad histórica los marcara como preferencia; las características secundarias son flexibles aunque antes fueran indispensables.

El motor determinista es la primera capa. Un incumplimiento estricto conocido descarta; un dato necesario desconocido conserva el candidato como **Pendiente de verificar**. Los barrios son alternativas, no condiciones simultáneas. Gemini no amplía barrios ni presupuesto ni convierte pendientes en confirmaciones.

La segunda capa usa el adaptador REST real `oportunidades/gemini.py`, JSON Schema, Pydantic, comprobación de IDs y evidencias contra los hechos enviados. Solo recibe necesidades y hechos de candidatos, sin identidad/contacto del cliente. La explicación es orientativa y requiere revisión humana; la validación estructural no garantiza que toda redacción de un modelo sea correcta. La puntuación solo ordena.

Cada evaluación se reutiliza por hash de necesidades, datos relevantes del candidato, modelo y versión de instrucciones. Por defecto se evalúan hasta 20 candidatos deterministas por oportunidad, en una única llamada para los no almacenados en caché. El máximo configurable es 30. El resto sigue visible sin evaluación de IA. Error, timeout, respuesta bloqueada/incompleta o configuración ausente conservan los candidatos deterministas y muestran la limitación. No hay reintentos de red automáticos; Mónica puede recalcular para reintentar fallos, conservando las evaluaciones válidas intactas.

Disparadores: guardar/modificar oportunidad mediante los formularios y API; terminar una ejecución exitosa del scraper; recálculo manual desde la ficha. Las tareas HTTP se ejecutan después de enviar la respuesta mediante BackgroundTasks. Un lease en SQLite evita duplicados concurrentes; los cambios recibidos durante una evaluación dejan una solicitud pendiente para procesar al terminar. El progreso se consulta desde la ficha. No hay cola externa ni servicio adicional.

Las decisiones por oportunidad/inmueble son **Pendiente, Preseleccionado y Descartado**. Se almacenan aparte del matching y se conservan al recalcular o desaparecer un candidato. La ficha permite cambiar también las decisiones históricas. Preseleccionar no comunica ni envía nada.

## Arquitectura

Playwright propio, FastAPI/Jinja2, JavaScript nativo, SQLite. `consola/v06.py` adapta HTTP; `consola/inicio.py` proyecta resúmenes; `oportunidades/matching.py` contiene reglas puras; `automatizacion.py` coordina; `seguimiento.py` define un contrato y adaptador SQLite; `gemini.py` encapsula el proveedor. La base auxiliar predeterminada es `metro-consola.sqlite` junto al catálogo; `RADAR_CRM_DB` permite elegir otra base, siempre distinta de `METRO_DB`.

Las tablas nuevas `radar_clientes_estado`, `radar_decisiones`, `radar_matching`, `radar_matching_pendiente` y `radar_gemini_cache` se crean de forma aditiva en la primera escritura. No se cambia la migración 1 de clientes/oportunidades ni el user_version ni el catálogo. Los adaptadores permiten una implementación futura en Sheets; esta entrega no migra datos. Cloud Run es un destino futuro, sin despliegue ni cambios de infraestructura.

La presentación sigue patrones oficiales de Carbon: cuadrícula de hasta 16 columnas, espaciado de 8 px y subdivisiones, tiles sin sombras, tablas compactas, labels visibles, contraste, foco y controles nativos. Conserva tonos tierra y reserva el botón principal para confirmar o recalcular. No instala Carbon ni un framework.

## Configuración y límites

Ver `consola/docs/V06.md`. La clave de Gemini no está configurada en el entorno de validación; el transporte, esquema, caché y errores se prueban con un servidor HTTP simulado, sin llamadas facturables. La evaluación contra el proveedor real y el presupuesto mensual quedan pendientes de credenciales y medición.

Las tareas BackgroundTasks viven en el proceso web. Si se interrumpe, pueden no terminar; la ficha mantiene el fallback determinista y permite reintentar. El lease caduca a los 10 minutos. No se introduce una cola distribuida para el volumen actual. La pasada posterior al scraper procesa oportunidades secuencialmente para contener llamadas.
