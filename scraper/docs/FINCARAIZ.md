# Fincaraíz — Radar Inmobiliario v0.9

Ampliación compatible en `develop`, sin cambiar las rutas heredadas ni crear otro catálogo de negocio. El usuario autorizó posteriormente el commit local de v0.9; no se crea tag, push ni despliegue. [Decisiones vigentes](../../RADAR_PROYECTO_RECTOR.md).

## Configurar desde la app

Desde la raíz:

```powershell
.\.venv\Scripts\python.exe scraper/run.py serve
```

Abrir [Inicio](http://127.0.0.1:8000/v0.6/), sección **Agregar fuente**, elegir **Fincaraíz**. Si el servidor estaba abierto antes del cambio, reiniciarlo para cargar el código nuevo.

- **URL filtrada:** pegar la primera página de resultados, por ejemplo `https://www.fincaraiz.com.co/venta/casas-y-apartamentos/la-carolina/zona-norte/bogota`. Se valida dominio, ruta, respuesta estructurada y página inicial. Las fichas, credenciales en URL y dominios parecidos se rechazan. Se conservan parámetros, URL original, URL efectiva y filtros que realmente entrega el portal.
- **Criterios verificados:** elegir operación, ciudad, barrio/zona y un tipo o una combinación de tipos disponible. La app resuelve una URL previamente comprobada y verifica nuevamente sus filtros. No fabrica slugs ni IDs. Las opciones iniciales corresponden a enlaces inspeccionados de La Carolina / Bogotá: venta de casas, apartamentos, ambos, apartaestudios y lotes; arriendo de casas o apartamentos. Las opciones de otros lugares se incorporan al registrar URLs verificadas. Una combinación sin correspondencia muestra una explicación y permite usar URL filtrada. Las búsquedas con filtros adicionales no se reutilizan silenciosamente como una búsqueda de criterios básicos.

Guardar/editar consulta **una página para verificar filtros**, pero no guarda anuncios ni inicia extracción. Las revisiones y la configuración viven en la base auxiliar del CRM. La lista de búsquedas permite editar, activar, desactivar y eliminar. Editar filtros conserva la configuración histórica y los snapshots de ejecuciones anteriores; desactivar/eliminar no borra inmuebles, relaciones, comentarios ni decisiones. Sin JavaScript, seleccionar la fuente y pulsar «Actualizar formulario»; los dos modos se procesan también en el servidor.

## Ejecutar explícitamente

```powershell
# Todas las búsquedas activas de Fincaraíz, sin límites de cobertura
.\.venv\Scripts\python.exe scraper/fincaraiz_run.py scrape

# Una búsqueda concreta: usar la URL canónica guardada como ID
.\.venv\Scripts\python.exe scraper/fincaraiz_run.py scrape --search 'https://www.fincaraiz.com.co/venta/casas-y-apartamentos/la-carolina/zona-norte/bogota'

# Recuperar la ejecución 1 con su selección original, aunque luego se desactive
.\.venv\Scripts\python.exe scraper/fincaraiz_run.py scrape --resume 1
.\.venv\Scripts\python.exe scraper/fincaraiz_run.py status 1

# Registrar sin extraer, verificando únicamente la página de resultados
.\.venv\Scripts\python.exe scraper/fincaraiz_run.py register --name 'La Carolina, casas y apartamentos' --url 'https://www.fincaraiz.com.co/venta/casas-y-apartamentos/la-carolina/zona-norte/bogota'
```

No combinar `--search` con `--resume`. `--headed` abre Chromium visible. `--max-pages` y `--max-details` son límites de diagnóstico: dejan la ejecución incompleta y **nunca confirman ausencias**. No se deben usar bases operativas para validaciones. Código de salida 0 solo para una ejecución completa; 2 para incompleta/bloqueada. No se programa ninguna tarea nocturna.

Variables compartidas por servidor y CLI:

| Variable | Uso |
| --- | --- |
| `METRO_DB` | Base existente de Metrocuadrado |
| `WASI_DB` | Base existente de Wasi |
| `FINCARAIZ_DB` | Almacenamiento técnico Fincaraíz; predeterminado `fincaraiz.sqlite` junto a `METRO_DB` |
| `RADAR_CRM_DB` | Base auxiliar de nombres, configuración, clientes y decisiones; predeterminado `metro-consola.sqlite` junto a Metro |

Todas las rutas deben ser distintas. La consola no escribe en bases técnicas. No hacen falta login, sesión manual, Gemini ni servicio de pago para Fincaraíz. No se carga `.env` automáticamente.

## Captura, identidad y recuperación

`catalogo/fuentes/fincaraiz.py` define identidad/validación/resolución; `scraper/fincaraiz/` adapta navegador y normalización. `FincaraizScraper` y `FincaraizStore` reutilizan cola incremental, clasificación, historial de precios, presencias, reintentos, checkpoints y monitor del motor común. El adaptador `CatalogoIntegrado` compone las tres fuentes para filtros, dashboard, fichas, CSV y matching. La identidad interna sigue siendo UUID5 de fuente + ID original: anuncios de portales distintos nunca se fusionan.

El portal inspeccionado publica `__NEXT_DATA__.props.pageProps.params.filters` y `fetchResult.searchFast.data/paginatorInfo`. La ficha usa `pageProps.data` y `technicalSheet`. No se llama ningún endpoint construido. Las páginas siguientes se obtienen de enlaces reales `/paginaN`, conservando el alcance y todos los parámetros. Se exige página esperada, filtros de negocio idénticos, total estable, progreso por IDs y cobertura final del total anunciado. `filters.page` se comprueba como estado de navegación y se separa de los criterios. No hay constante de 21 anuncios ni de 267 resultados.

Los listados incluyen en los casos observados descripción, ficha técnica, imágenes y anunciante; se usan directamente. Cuando faltan esos datos se abre el enlace publicado de la ficha y se verifica su ID. Precios iguales con ficha fiable reutilizan el documento, de acuerdo con la política incremental existente: no se promete detectar automáticamente cambios de descripción/contactos sin cambio de precio. Los registros técnicos `details_opened` cuentan trabajos de captura del motor; en Fincaraíz pueden resolverse desde el listado y no equivalen al número de navegaciones a fichas.

Pausa global mínima de 1,5 s más variación, concurrencia predeterminada 1, timeout 45 s y hasta dos reintentos adicionales con espera creciente. Recursos de imagen, fuentes y multimedia no se descargan. Bloqueo, CAPTCHA visible, error HTTP, datos incompletos, filtro cambiado o repetición detienen la confirmación de cobertura. No hay evasión. Al reanudar se comprueban las páginas guardadas y sus precios; si cambiaron, se pide iniciar otra ejecución. Una ejecución reanudada no suma una segunda ausencia.

Una captura fallida/parcial, precio contradictorio o pérdida de un valor conocido conserva la ficha fiable anterior y marca revisión. Las ausencias son por búsqueda, solo tras ejecuciones completamente exitosas y dos confirmaciones para retiro; la pertenencia a otra búsqueda se conserva. Activar/desactivar no cambia presencias ni decisiones.

## Campos y límites

- Precio COP y administración son campos independientes; precio ausente/inválido permanece desconocido. Ceros publicados en baños, parqueaderos o administración permanecen cero. Los estados `present/absent/error` no se confunden y se muestran en ficha. No se compara ni convierte moneda.
- La ubicación principal explícita `locations.location_main` alimenta barrio/zona; las listas asociadas se conservan en `extra.associated_locations` y se muestran sin convertirlas en coincidencias. Si la principal no es suficiente o no tiene equivalencia controlada, el matching mantiene **Pendiente de verificar**. No se usa el barrio de la búsqueda como barrio del inmueble.
- `m2`, `m2Built` y `m2apto` se conservan como área publicada, construida y privada. **Prioridad:** usar exactamente el tipo elegido en filtro/necesidad; el catálogo predetermina área publicada y las necesidades predeterminan construida. No sustituir una por otra. Ausencia del tipo seleccionado permanece desconocida. Se registra `area_discrepancy` y se muestran las cifras sin conciliarlas. El caso real inspeccionado entrega 78 m² publicados y 72,12 m² construidos/privados.
- Piso, estrato, habitaciones, baños, parqueaderos, fotos por URL, descripción y título se conservan. Fechas del portal sin hora se muestran como fechas originales, sin inventar zona horaria. Las fechas de captura mantienen UTC y su presentación existente en Colombia.
- La antigüedad usa la etiqueta de `technicalSheet.constructionYear` (p. ej., «9 a 15 años»); `antiquity=3` se conserva como código original, nunca como tres años. El matching actual no transforma intervalos de antigüedad en años comparables: conserva esa preferencia pendiente.
- Se agrupa anunciante por igualdad literal del nombre, sin aproximación; se integra su perfil publicado y otros inmuebles ya capturados. Solo números completos en datos públicos del anunciante se muestran como contactos. `masked_phone`, `has_whatsapp` y el teléfono general de configuración del portal nunca producen un número inferido. No se envían formularios ni mensajes. Sin contacto, permanecen anunciante y publicación original.

## Job y snapshots

`python scraper/job.py --source fincaraiz` procesa las búsquedas activas; `--source all` incorpora las tres fuentes y `--resume-fincaraiz ID` restaura la ejecución seleccionada. `Dockerfile.jobs` incluye el adaptador y el snapshot de Cloud Storage incluye `fincaraiz.sqlite` y configuración auxiliar, reutilizando exclusión mutua y precondiciones de generación. No se desplegó, programó ni probó una ejecución desatendida real en Cloud Run; esa validación es posterior. No se promete presupuesto mensual sin medirlo.

## Comprobaciones

[Informe de validación de esta tarea](VALIDACION_FINCARAIZ.md). Las regresiones usan portales interceptados y bases sintéticas; las consultas reales autorizadas usan exclusivamente `.tmp/fincaraiz-v09/`, sin bases operativas. La prueba inicial fue acotada. Posteriormente, por instrucción explícita del usuario, la ejecución operativa local 1 terminó con 13 páginas y 267 anuncios correctos, sin errores ni duplicados; se comprobaron en la API de la app. Cloud Run sigue pendiente.

## Identidad física supervisada vigente

La publicación Fincaraíz conserva su UUID y ficha íntegra. La capa compartida posterior a la captura propone coincidencias con Metrocuadrado y Wasi; solo la revisión humana agrupa catálogo y recomendaciones. Un fallo queda reintentable sin perder la captura. [Reglas, reversión y operación](../../docs/IDENTIFICACION.md).
