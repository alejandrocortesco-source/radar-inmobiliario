# Actualización incremental por precio

El scraper existente sigue recorriendo **todas las páginas de cada búsqueda** en cada invocación diaria. Lo incremental es la apertura de fichas: se evita repetirla cuando el precio es comparable e idéntico al de la última ficha fiable. Se mantiene la extracción completa, el mapa, SQLite, la interfaz y el monitor de recursos.

## Ejecutar

Desde la raíz, usando el entorno existente:

```powershell
# Búsqueda predeterminada, comparación en COP confirmada por el usuario
.\.venv\Scripts\python.exe scraper/run.py scrape

# Varias búsquedas en una misma ejecución; las fichas se deduplican globalmente
.\.venv\Scripts\python.exe scraper/run.py scrape `
  --url 'https://www.metrocuadrado.com/inmuebles/venta/bogota/la-carolina?search=form' `
  --url 'https://www.metrocuadrado.com/inmuebles/venta/bogota/usaquen'

# Si no se puede confirmar la moneda de los importes publicados sin código
.\.venv\Scripts\python.exe scraper/run.py scrape --listing-currency unknown

# Recuperar una ejecución interrumpida
.\.venv\Scripts\python.exe scraper/run.py scrape --resume 2
```

No se instaló una tarea programada: se invoca el mismo comando cada día. Al reanudar se conservan las URLs y la política de moneda de esa ejecución. Para un nuevo día hay que iniciar **una nueva ejecución**, no reanudar una ya terminada. Reanudar el mismo ID no cuenta como una segunda confirmación de ausencia.

`--url` puede repetirse. Las variantes que sólo difieran en `search`, `src_url`, parámetros `utm_*`, orden de parámetros o barra final se reconocen como la misma búsqueda; el resto de filtros se conserva. Los checkpoints y procedencias incluyen URL de búsqueda y número de página. Una misma ficha descubierta en varias búsquedas tiene un solo trabajo de detalle por ejecución.

## Clasificación y actualización

| Clasificación | Acción |
|---|---|
| `new` | ID sin ficha en el catálogo: se abre y extrae toda la información |
| `modified` | Precio comparable diferente: se abre la ficha y se actualiza completa si es fiable |
| `unchanged` | Precio comparable idéntico y catálogo completo: no se abre la ficha; se conserva todo su documento y se actualiza la última verificación del listado |
| `review` | Precio/moneda/operación no comparable, contradicción, ficha previa parcial o fallo pendiente: se abre la ficha de manera conservadora |

`unchanged` es un estado nuevo de trabajo, con cero intentos de detalle. El título, descripción, fotografías, características y mapa anteriores se conservan. Cambios que no afecten al precio del listado no se detectan automáticamente: esa es la limitación deliberada de la política pedida.

La última ficha completa se mantiene si una revisión produce datos parciales o contradice el listado. La nueva captura parcial se conserva como evidencia en el trabajo de esa ejecución, y el catálogo queda con `needs_refresh=1`. El siguiente intento o ejecución volverá a revisarla; nunca se oculta un fallo como si fuera un anuncio sin cambios. Una ejecución con fichas parciales pendientes o precios contradictorios queda incompleta y no confirma ausencias.

## Precio comparable

Se compara con `Decimal`, preservando valores y moneda originales y la fuente. Se admiten importes numéricos y formatos monetarios inequívocos con separadores como `1.000.000`, `1,000,000.00` y `1.000.000,00`. Las monedas soportadas son COP, USD y EUR. No se realiza conversión de divisas ni se interpreta un cambio de moneda como un cambio numérico equivalente.

La inspección real del listado encontró que el JSON publica `mvalorventa` y `mvalorarriendo` y que la tarjeta muestra `$` sin código de moneda. **El usuario confirmó COP para estas búsquedas**; por eso es el valor predeterminado de `--listing-currency`. Una moneda explícita tiene prioridad. Señales monetarias incompatibles fuerzan revisión. Si se usa `unknown`, el símbolo `$` aislado nunca se supone COP.

El adaptador selecciona `mvalorarriendo` para oferta `arriendo` y `mvalorventa` para `venta`. El componente público inspeccionado también muestra venta en las ofertas **«Venta y Arriendo»**; en ese caso se compara ese importe de venta, sin mezclarlo con el arriendo. El precio de arriendo sigue preservado en los datos originales. Las fichas antiguas de oferta dual cuyo precio normalizado faltaba se revisan una vez para reparar su normalización.

No se compara un precio ausente, cero usado como valor vacío, negativo, no finito, con precisión monetaria excesiva, texto como «Desde…» o formato ambiguo. Se abre la ficha. También se revisa cuando un mismo ID aparece con precios contradictorios entre páginas o búsquedas; diferencias meramente de formato no son contradicciones.

Antes de aceptar una ficha actualizada se contrasta su precio con el del listado. Si difieren o dejan de ser comparables, la captura queda parcial, se conserva el catálogo fiable anterior y se registra el incidente. El historial `price_changes` conserva precio anterior, nuevo publicado, moneda, operación, fecha de **detección**, fuente, importe observado en ficha y verificación (`pending`, `confirmed`, `detail_failed` o discrepancia). La fecha de detección no pretende ser la fecha exacta en que el anunciante cambió el precio.

## Ausencias y reapariciones

La disponibilidad se registra **por URL de búsqueda**:

1. Primera ausencia en una ejecución completa y exitosa: `possibly_removed`, contador 1.
2. Segunda ausencia en otra ejecución completa y exitosa: `removed`, contador 2.
3. Una presencia posterior restaura `active` y reinicia el contador.

Las ejecuciones incompletas, limitadas, bloqueadas, fallidas o interrumpidas **no incrementan ausencias ni marcan posiblemente retirados o retirados**. Tampoco las incrementan las ejecuciones con una ficha parcial, un fallo de detalle o precios contradictorios. Si falla una de varias búsquedas, ninguna búsqueda de esa ejecución confirma ausencias. Las presencias sí se conservan: ver un anuncio es evidencia positiva aunque el resto del recorrido falle.

Los recorridos interrumpidos entre dos ejecuciones completas no cuentan como confirmaciones. Reaparecer, incluso durante un recorrido incompleto, sí reinicia las ausencias. La operación es idempotente: terminar o reanudar de nuevo un mismo ID no incrementa dos veces el contador.

`removed` significa retirado **de las búsquedas configuradas**, no que se haya eliminado su ficha del portal o vendido el inmueble. Si cambia de barrio/filtro puede desaparecer de una búsqueda y seguir activo en otra. En el catálogo global basta una búsqueda activa para conservar el estado global `active`. No se borran documentos ni se infiere una venta.

La última página se valida mediante el paginador; si el portal publica un total numérico exacto, se exige además cubrir ese número de IDs principales. Páginas repetidas, discrepancias de cobertura o cambios de IDs/precios al reproducir un checkpoint hacen que el recorrido quede incompleto. Un listado vacío sólo se acepta con `results=[]`, sin destacados y ambos totales públicos iguales a cero.

## Persistencia y revisión

La migración SQLite es automática y transaccional. Antes de migrar una base con catálogo crea una copia SQLite consistente `<nombre>.pre-incremental.sqlite` usando la API de backup, sin sobrescribir una copia existente. Los documentos y trabajos históricos se conservan. No se calculan retirados retroactivamente a partir de ejecuciones antiguas.

Tablas añadidas: `run_searches` (avance de cada URL), `listing_observations` (precios observados y conflictos), `search_memberships` (presencia y contador de ausencias) y `price_changes` (historial). Los trabajos incluyen clasificación, motivo, precio anterior y observado. Las páginas y apariciones incluyen búsqueda en sus claves. `last_verified_at` es la última presencia comprobada en el listado; no vuelve a fechar la extracción de la ficha cuando se omite su apertura.

La página principal muestra los contadores incrementales y permite filtrar `unchanged`. `/catalog` conserva anuncios activos, posiblemente retirados y retirados, con su última verificación. La ficha muestra disponibilidad por búsqueda y el historial de precios. API: `/api/catalog`, `/api/properties/{id}`, `/api/runs/{id}/report` y exportación existente. Se preservan las instantáneas de documentos por ejecución para auditar qué información se reutilizó.

Los respaldos, CSV de recursos, bases y demás salidas siguen excluidos de Git. El monitor de recursos mide toda la invocación incremental, incluyendo los recorridos de listado; sus datos permiten comparar el ahorro real de fichas abiertas.
