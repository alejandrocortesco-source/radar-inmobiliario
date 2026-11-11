# Identificación supervisada de inmuebles

Implementado localmente el 10 de noviembre de 2026, sin commit ni despliegue por esta tarea. No se encontró un informe de viabilidad entre la documentación y los diagnósticos locales disponibles; no se atribuyen métricas a experimentos ausentes.

## Publicación e inmueble

Una publicación conserva su UUID5 por fuente/ID original, ficha completa, anunciante, precios, procedencias e historial. El nombre Python histórico `Inmueble` sigue representando esa publicación para mantener compatibilidad. Un inmueble físico confirmado tiene un UUID independiente en `radar_inmueble_publicaciones` y reúne publicaciones; `inmueble_id` identifica ese grupo y `publicaciones` expone sus fichas originales. Publicaciones independientes carecen de `inmueble_id`. No se reescribe ningún UUID ni dato del scraper.

Se propone cualquier par entre Metrocuadrado, Wasi y Fincaraíz, sin exigir las tres fuentes. Ninguna puntuación crea asociaciones. Solo una decisión humana explícita permite agrupar.

## Motor y limitaciones

`catalogo/identificacion.py`, versión `identificacion-1`, es una capa común posterior a la captura/normalización. No descarga fotos, no llama a Gemini ni usa servicios externos. La puntuación es similitud sobre 100, nunca probabilidad ni certeza de identidad.

Los bloques exigen ciudad, tipo y una operación compartidos, más barrio, edificio, dirección o un intervalo vecino de área del mismo tipo. Las áreas usan intervalos de 10 m² con vecinos; los pares se deduplican. Los registros sin esos atributos suficientes no generan candidatos nuevos; esto favorece precisión y puede perder coincidencias. No se realiza un producto cartesiano global. Un barrio con muchos anuncios similares puede producir muchos pares dentro de ese bloque; medir antes de ampliar escala.

| Señal | Puntos por coincidencia conocida |
| --- | ---: |
| Ciudad, operación, tipo | 5 cada una |
| Barrio | 10 |
| Dirección | 10 |
| Edificio | 5 |
| Identificación explícita de unidad en dirección | 15 |
| Coordenadas explícitamente no aproximadas | 5 |
| Áreas comparables | 15 |
| Habitaciones | 7 |
| Baños, parqueaderos | 5 cada uno |
| Estrato | 3 |
| Precio de la misma operación | 3 |
| Nombre del anunciante | 2 |

El umbral de propuesta es 35. Una ausencia suma cero y aparece como faltante. Las contradicciones suman cero, se enumeran y nunca se ocultan por una puntuación alta. Las reglas, pesos y tolerancias están centralizadas. Los textos se comparan sin tildes/caso y con espacios normalizados; no se infieren sinónimos de direcciones ni equivalencias geográficas. Áreas solo de igual clase (construida/privada/publicada); todas las clases comparables deben diferir como máximo 3% respecto del mayor valor para sumar el peso único de área. No se comparan privada y construida entre sí. Precios COP: diferencia máxima 5% en cada operación compartida comparable. Coordenadas: diferencias máximas de 0,0005 grados en cada eje; es una señal de proximidad, no distancia geodésica ni unidad específica. Se extrae unidad únicamente tras marcadores explícitos de apartamento/apto/unidad/interior; no prueba identidad por sí sola.

Dirección y coordenadas pueden corresponder solo al edificio. Apartamentos similares requieren comprobar la unidad con las fuentes. Precio y anunciante son complementarios y juntos no alcanzan el umbral. No se utilizan identificadores externos, teléfonos ni códigos iguales entre portales como evidencia de identidad: no hay una procedencia cruzada comprobada. Datos originales, versión y SHA-256 se conservan en cada evidencia; las fechas de presencia no invalidan por sí solas la similitud.

Wasi: la localidad publicada se acepta como calificador solamente cuando coincide exactamente con la localidad del barrio explícito resuelto en el catálogo controlado. Se conserva el texto original y la regla como evidencia. No se toma el barrio de títulos, búsquedas, zonas relacionadas ni deducciones. La corrección se aplica al leer fichas existentes, sin exigir un nuevo scrape ni modificar bases del scraper.

## Uso para Mónica

Abrir **Revisar publicaciones** en la navegación (`/v0.6/identificacion`). El dashboard mantiene sus cuatro secciones. **Analizar catálogo existente / reintentar** reprocesa las fichas locales, sin capturar. Pendientes se ordena por evidencia cambiada, revisión no aplazada y similitud; hay doce relaciones por página. Cada propuesta muestra fichas completas en paralelo, enlaces, anunciante, precios, coincidencias, diferencias y faltantes.

**Confirmar mismo inmueble** requiere marcar que se revisaron todas las relaciones y se trata de la misma unidad física. Al ampliar dos grupos se presentan todos sus miembros y todos los pares, incluidas contradicciones; la confirmación explícita abarca esas relaciones. Una relación previamente descartada bloquea la unión hasta devolverla a revisión. A–B no incorpora C por semejanza con B. Una huella del conjunto, su pertenencia y los datos evita guardar una revisión obsoleta o una unión concurrente no revisada.

**Son inmuebles distintos** conserva el descarte en nuevas ejecuciones. **Revisar después / devolver a revisión** conserva el caso pendiente y lo coloca después de los no revisados. Los diferidos también se consultan en una vista propia. **Asociaciones confirmadas** permite **Deshacer agrupación**: separa explícitamente *todo el grupo* (no solo el par mostrado), mantiene las publicaciones y devuelve sus relaciones a pendientes. No se borran decisiones comerciales ni historial.

La app local no tiene autenticación de personas: la auditoría dice `operadora local (sin autenticación)` y registra fecha UTC. No se atribuye una identidad de Mónica verificada. Confirmaciones/descartes y evidencia original quedan en el historial. Nuevos datos actualizan evidencia, conservan decisiones y señalan cambios para revisión; nunca deshacen automáticamente una decisión humana. Si una fuente del grupo no está disponible, restaurarla antes de cambiar el grupo.

## Catálogo y matching

El filtro completo se evalúa sobre cada publicación y después se agrupan las elegibles. El representante del catálogo es el menor UUID entre publicaciones que satisfacen todos los filtros, antes del orden y paginación; se muestran sus datos coherentes. Al cambiar filtros puede cambiar el representante. No se combina precio de un anuncio con atributos de otro, ni se muestra un precio «desde». Los conteos de categorías y páginas cuentan inmuebles visibles; el detalle expone todas las publicaciones, precios por operación, contactos, disponibilidad y última extracción. El CSV conserva una fila por publicación/oferta filtrada para mantener su contrato y procedencia; es una exportación de publicaciones, no del contador de inmuebles.

Matching aplica sus reglas estrictas a cada publicación por separado. Después agrupa por inmueble confirmado: primero una publicación que cumple criterios conocidos, luego menor UUID; las alternativas elegibles se conservan en `Coincidencia.alternativas`. Las vistas muestran una recomendación con sus datos y acceso a las alternativas. Desconocidos siguen pendientes. La ficha del cliente presenta decisiones por cada publicación, incluso cuando difieren dentro del grupo, y permite editarlas sin sobrescribir a las demás. Los históricos y la caché mantienen UUID de publicación. Deshacer devuelve las recomendaciones individuales sin perder decisiones.

## Persistencia, migración y operación

`RepositorioAsociaciones` define el contrato; `AsociacionesSQLite` usa la misma base auxiliar `RADAR_CRM_DB` que clientes/seguimiento. Sus tablas `radar_identificacion_datos`, `radar_identificacion_pares`, `radar_identificacion_historial`, `radar_identificacion_ejecuciones` y `radar_inmueble_publicaciones` se crean con `CREATE TABLE IF NOT EXISTS` en la primera escritura, en transacción `BEGIN IMMEDIATE`. No se modifica `user_version`, migración 1 ni tablas previas. Consultar una base auxiliar ausente no la crea.

No hay comando de migración obligatorio. Reiniciar el servidor local para cargar el código y usar el botón de análisis. La reversión funcional se realiza con **Deshacer agrupación**; volver al código anterior deja las tablas aditivas sin utilizar, sin borrarlas ni perder la auditoría. Una recuperación de base requiere el respaldo operativo habitual y revisión específica; no hay una migración destructiva automática.

Tras una actualización exitosa, `despues_scraper` analiza antes de recalcular oportunidades activas. Compara huellas de datos y versión, genera pares principalmente para publicaciones nuevas/cambiadas, reutiliza resultados anteriores y refresca pares persistidos aunque ya no compartan bloque. Repetir no duplica pares ni miembros. Los fallos registran ejecución fallida y log; la captura ya completada se conserva y el botón permite reintentar. Si la propia base auxiliar no admite escritura, solo puede quedar el log del proceso. No hay cola durable adicional ni reintento automático independiente.

SQLite local, snapshots existentes y repositorios sustituibles siguen siendo la arquitectura implementada. El contenedor Jobs ya incluye catálogo y oportunidades y su snapshot conserva la base auxiliar; no se añade otra fuente de verdad. Cloud Run y Sheets siguen planificados: esta tarea no despliega, no crea integración con Sheets ni activa Scheduler. No hay periodicidad automática nueva; el horario de dos días a medianoche de Bogotá es una propuesta de configuración, no evidencia de activación. Autenticación pública y operación desatendida en nube, consumo mensual y presupuesto inferior a US$10 están pendientes de verificar. Gemini continúa opcional solo para oportunidades; no participa en identidad y no se configura en esta entrega.

Pruebas: `catalogo/tests/test_identificacion.py` y `consola/tests/test_identificacion_ui.py`, además de las suites existentes. Usan solo bases sintéticas. Los resultados de esta ejecución se registran en el informe de entrega, separadamente de validaciones históricas.
