# Normalización geográfica de Consola v0.3

Validación local: 26 de octubre de 2026, rama `feat/consola-v0.3`. Sin commit/push.

## Causa y evidencia

`scraper/metro/extraction.py::normalize_detail` traslada por separado
`neighborhood`, `commonNeighborhood`, `city.nombre`, `zone.nombre` y
`sector.nombre`. Guarda la evidencia en `fields`, `extra` y
`sources.flight_property`; no concatena barrio y edificio.

Se inspeccionaron los **427 documentos globales** de `scraper/data/metro.sqlite`.
En los 427 el `normalized.neighborhood` coincide exactamente con el original
del portal. Por tanto, los nombres compuestos ya estaban publicados en el
campo `neighborhood`. El problema de interpretación estaba en
`catalogo/persistencia/_metrocuadrado.py`: priorizaba ese texto como barrio sin
validar su semántica ni contrastarlo con `common_neighborhood`. Selector y
matching heredaban ese texto; la comparación exacta rechazaba un edificio de
La Carolina frente a una solicitud de La Carolina.

También hay contradicciones independientes del edificio: PLENITUD/La Carolina,
LAGUNETA/La Carolina con zona Sur, Country Club/La Carolina, y una publicación
de La Carolina con zona Occidental. No se puede resolver todo quitando EDIF ni
priorizando siempre el segundo campo. La URL de búsqueda no es evidencia de barrio.

## Reglas y datos controlados

`catalogo/geografia/` es independiente de la captura, HTTP y del scraper.
`barrios.json` contiene una semilla revisada, con IDs de sector, ciudad,
localidad y referencia de
[Catastro Bogotá, listado 2021–2022, páginas 23–25 y 28](https://www.catastrobogota.gov.co/sites/default/files/Aviso%20cierre%202021-2022%20f.pdf).
La Carolina (008403), Country Club (008402), Rincón del Chicó (008411) y La
Carolina de Suba (009236) son entradas diferentes. El Chicó no se convierte
en Rincón del Chicó. La zonificación Norte de esta semilla se usa como
restricción de consistencia con las zonas comerciales del portal; no se
presenta como una división oficial definida por ese PDF.

La semilla no es un catálogo completo de barrios comerciales, ni certifica
coordenadas o linderos. El concepto de sector catastral puede diferir del
barrio comercial: [alcance oficial de IDECA](https://www.ideca.gov.co/recursos/mapas/sector-catastral).
No se equiparan automáticamente nombres comerciales con sectores catastrales.
Para ampliar ciudades o equivalencias debe revisarse una fuente y añadirse la
entrada controlada; no basta con observar un texto en un anuncio.

- Compara claves sin tildes, con espacios y signos normalizados; Bogotá D.C.
  tiene la misma clave de ciudad que Bogotá. Las identidades son por ciudad.
- Admite prefijo estructural BARRIO y calificadores exactos de localidad.
  Un sufijo de sector solo se admite si coincide exactamente con el sector
  publicado en esa ficha; queda registrado como evidencia de esa regla.
- Separa EDIF, EDIF. y EDIFICIO por límites de palabra, exclusivamente cuando
  la parte anterior resuelve un nombre controlado completo. No busca nombres
  de barrios dentro del nombre de un edificio ni usa similitud difusa.
- Contrasta ambos campos de barrio. Nombres distintos, nombres desconocidos
  no vacíos, zonas contradictorias o edificios contradictorios impiden confirmar.
  NA, otros y campos ausentes se tratan como desconocidos, no como otro barrio.
- Conserva ciudad, barrio, barrio común, zona y sector originales, edificio
  separado, estado, razones, evidencias y huella de reglas. No corrige
  automáticamente errores como FOLEDO, PELODO DEL CONTRY o LAS ACASIAS USAQUEN.
- «Confirmada» significa consistencia de los campos publicados con las reglas;
  sigue siendo necesaria la comprobación comercial de la publicación.

## Persistencia e integración

Se agrega `geografia` y `edificio` al modelo común. `barrio` solo contiene un
nombre canónico confirmado; si hay ambigüedad es `None`. El documento original,
los ID de origen y UUID internos permanecen intactos.

La proyección se guarda en **`scraper/data/metro-geografia.sqlite`**, separada
del scraper y del CRM `metro-consola.sqlite`. La migración es aditiva y
transaccional. Cada fila incluye ID original/interno, huella del documento y
ciudad, huella de reglas, originales, resultado y fecha. Repetirla sin cambios
actualiza cero filas. Las lecturas no crean archivos ni migran bases.

El catálogo lee la proyección solo si coinciden documento y versión. Si falta,
está obsoleta o no es legible, recalcula en memoria; una captura futura no
depende de ejecutar inmediatamente la migración. El reprocesamiento toma filas
y modelos desde la misma transacción de lectura del catálogo. No se ejecuta scraping.

Filtros del catálogo, API y selector utilizan la misma normalización. La API
agrega `neighborhood`, `zone`, `building` y `geografia` sin retirar campos
previos; las fichas técnicas mantienen el documento bruto. La ficha de Consola
permite consultar estado, originales, motivos y edificio en «Más datos».

El selector ofrece únicamente nombres canónicos respaldados por anuncios de
esa ciudad, deduplicados, con su búsqueda y selección múltiple existentes.
No muestra todas las entradas del nomenclátor si no tienen anuncios confirmados.
Los valores históricos fuera del catálogo se conservan como etiquetas, sin
convertirse en nuevas opciones. Los nombres históricos con edificio que puedan
resolverse se comparan por ID canónico en memoria, sin reescribir el CRM.

El matching compara IDs de barrio; una ubicación no resuelta produce un
pendiente, no una coincidencia confirmada. Un barrio confirmado diferente es
incompatible. Se conservan presupuesto, moneda, operación, habitaciones, áreas
y demás requisitos. Barrio y zona siguen siendo alternativas explícitas de
ubicación según el contrato existente: pedir solo una zona no exige un barrio.

## Resultado con datos reales

| Medición | Resultado |
|---|---:|
| Inmuebles preservados | 427 |
| Textos originales distintos en neighborhood | 29 |
| Registros con EDIF/EDIFICIO antes, en cualquiera de los dos campos | 10 |
| De esos registros, barrio confirmado y edificio separado | 8 |
| De esos registros, pendientes por conflicto | 2 |
| Nombres de edificios como barrios del selector después | 0 |
| Barrio normalizado confirmado en el catálogo completo | 333 |
| Ubicación pendiente de revisión en el catálogo completo | 94 |

**Limitación conocida y aceptada para el cierre de v0.3:** estos 94 registros
se conservan como pendientes de verificar, sin asignarles barrios artificiales.
Su aceptación permite cerrar la versión con esta cobertura geográfica limitada;
no confirma las ubicaciones. La revisión de fuentes y la ampliación controlada
del nomenclátor quedan para un trabajo posterior.

En esta instantánea el único barrio respaldado por anuncios sin contradicción
es La Carolina. Los otros nombres originales **no se han fusionado con él**:
permanecen en la evidencia pendiente. Las categorías de motivos se solapan:
55 registros con neighborhood no reconocido, 31 con common_neighborhood no
reconocido, 15 con dos barrios controlados diferentes, 7 con zona contradictoria
y 8 sin ningún barrio identificable. No deben sumarse como inmuebles distintos.

| ID real | Original | Resultado |
|---|---|---|
| 3147-M5621082 | LA CAROLINA EDIF CRIXTAL / LA CAROLINA | La Carolina; edificio CRIXTAL |
| 3774-M5119663 | LA CAROLINA EDIF TORRE DE ALCALA / LA CAROLINA | La Carolina; edificio TORRE DE ALCALA |
| 3553-M4858301 | LA CAROLINA EDIF GUADAL POLO / LAS ACASIAS USAQUEN | Pendiente: segundo nombre no reconocido; edificio separado |
| 16040-M6071182 | RINCON DEL CHICO EDIF CAROLINA / Chico | Pendiente: no se asume equivalencia Rincón del Chicó/Chicó; no se asigna a La Carolina |

La oportunidad real de comprobación solicita compra de apartamento en La
Carolina, presupuesto **$1.650.000.000 COP**, mínimo **3 habitaciones**, **270 m²
construidos**, **4 baños** y **2 parqueaderos**. Devuelve **5 confirmados y 70
pendientes**, incluyendo CRIXTAL **3147-M5621082** como confirmado. Los pendientes
no se presentan como aprobados: parte del catálogo carece de moneda u otros
datos y la normalización no los inventa. El diagnóstico detalla cada requisito.

Se comprobó por API y mediante captura/guardado real en Chromium a 1440 y 390 px,
con CRM aislado: búsqueda del selector, resultado CRIXTAL, detalle con originales,
edición a 999 habitaciones y explicación sin resultados. Sin errores JS ni
desbordamiento de página. Se revisaron las capturas generadas.

## Reproducir

Desde la raíz y usando el entorno Python existente:

```powershell
.\.venv\Scripts\python.exe -m catalogo.geografia
.\.venv\Scripts\python.exe consola/tools/auditar_geografia.py
.\.venv\Scripts\python.exe consola/tools/validar_matching_real.py
.\.venv\Scripts\python.exe consola/tools/validar_geografia_navegador.py
```

El primer comando admite otra ruta SQLite como argumento. Las herramientas
respetan `METRO_DB`; la auditoría genera `.tmp/geografia/auditoria.json`, con el
inventario completo de los 94 pendientes. Las validaciones crean un CRM nuevo
en `.tmp/validacion-matching-<UUID>/`, evidencia JSON y capturas; no agregan
clientes ni oportunidades de prueba al CRM de Mónica. Comparan SHA-256 del
catálogo y CRM originales antes/después.

La Consola se prueba en `http://127.0.0.1:8000/consola/`: elegir La Carolina,
ingresar los requisitos anteriores y guardar/buscar. Abrir la ficha de CRIXTAL
para consultar el edificio y los campos originales. No se cambió el layout.

Pruebas de regresión y nuevas: **158 Consola, 230 catálogo y 90 scraper**.
Incluyen reglas de nombres, otras ciudades, conflictos, falsos positivos por
edificio Carolina, filtros/selector/matching consistentes, backfill idempotente,
rollback y caché obsoleta, conservación de registros y documentos originales.
La advertencia existente de deprecación de BlockingPortal en Starlette sigue
pendiente; no se agregaron dependencias ni servicios externos.
