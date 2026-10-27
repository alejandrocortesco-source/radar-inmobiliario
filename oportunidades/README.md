# Clientes, oportunidades y matching v0.3

Este módulo reutiliza `catalogo.modelos.Inmueble` y `ServicioCatalogo.listar()`.
No importa `metro`, no ejecuta scraping y no invoca servicios externos.

- `modelos.py`: contratos Pydantic de entrada y registros con UUID y fechas UTC.
  `Cliente` y `Oportunidad` se guardan separados, con relación uno a muchos.
- `servicio.py`: casos de uso de captura, consulta, edición y búsqueda.
- `persistencia.py`: protocolo de repositorio y adaptador SQLite; permite añadir
  posteriormente otro almacenamiento conservando contratos y motor.
- `matching.py`: función pura `buscar(necesidades, catalogo, orden)` sobre los
  datos realmente disponibles. No depende del formulario ni de SQLite.
- `normalizacion.py`: reexporta las claves comunes de `catalogo.geografia` para
  ciudades, selección y deduplicación de necesidades por tildes, caso y espacios.
  La resolución del barrio canónico y su evidencia pertenecen al catálogo.
- `api.py`: API JSON sobre el FastAPI existente; el adaptador HTML está en
  `consola/oportunidades.py`. Ambos se registran desde el router de la Consola,
  sin cambiar el punto de entrada del scraper.

## API local

Consultar `/docs` para ver el esquema y probar los endpoints:

| Método | Ruta | Acción |
| --- | --- | --- |
| GET / POST | `/api/clientes` | Consultar / crear clientes |
| GET / PUT | `/api/clientes/{id}` | Consultar / editar cliente completo |
| GET / POST | `/api/oportunidades` | Consultar / crear oportunidades |
| GET / PUT | `/api/oportunidades/{id}` | Consultar / editar oportunidad completa |
| GET | `/api/oportunidades/{id}/coincidencias?orden=coincidencia` | Buscar en catálogo global |
| GET | `/api/oportunidades/{id}/diagnostico?orden=coincidencia` | Conteos, filtros, descartes y rutas SQLite |

Primero crea un cliente con `{"nombre": "Ana", "telefono": "3001234567"}`.
Usa su `id` en una oportunidad:

```json
{
  "cliente_id": "ID_DEVUELTO_POR_LA_API",
  "estado": "abierta",
  "necesidades": {
    "operacion": "compra",
    "tipo": "apartamento",
    "ciudad": "Bogotá",
    "barrios": ["La Carolina"],
    "zonas": [],
    "presupuesto_max": "450000000",
    "habitaciones_min": 2,
    "banos_min": 2,
    "parqueaderos_min": 1,
    "area_min_m2": "70",
    "area_max_m2": "120",
    "tipo_area": "construida",
    "antiguedad_max": 20,
    "preferencias": ["antiguedad_max", "parqueaderos_min"],
    "observaciones": "Prefiere balcón; revisar manualmente."
  }
}
```

`compra` se mapea a `Operacion.VENTA`. Se conservan todos los tipos existentes
del catálogo, incluidos apartamento, casa y otro, sin agruparlos por inferencia.
PUT reemplaza los datos editables y conserva `id` y `creado_en`. La API valida
el mismo contrato que la captura manual: campos obligatorios, números finitos,
áreas positivas, mínimos enteros no negativos, al menos habitaciones o área
mínima y ubicaciones no vacías. Las entradas inválidas devuelven 422; IDs
inexistentes, 404; almacenamiento no disponible, 503. La captura conjunta de
cliente y oportunidad es atómica; un fallo revierte ambas escrituras.

Las respuestas de matching incluyen inmueble, oferta de la operación elegida,
`cumple`, `pendientes`, `preferencias_cumplidas`, `preferencias_pendientes` y
`preferencias_no_cumplidas`. `pendientes=[]` significa requisitos confirmados
por los datos del catálogo, sin garantizar disponibilidad comercial. El orden
`coincidencia` usa requisitos confirmados, menos pendientes, más preferencias
cumplidas e ID; `precio` usa únicamente importes COP conocidos, desconocidos al
final. No se usan puntuaciones ni modelos de IA.

La API es una entrada estructurada reutilizable para futuros capturadores; esta
entrega no implementa webhooks, WhatsApp, Gemini ni Google Sheets.

El diagnóstico utiliza la misma evaluación que las coincidencias. Devuelve
`total_catalogo`, `compatibles` (requisitos confirmados), `pendientes`,
`total_resultados`, `incompatibles`, `etapas`, `motivos`, `datos_faltantes`,
`descartes` por inmueble, `resultados` y rutas resueltas en `almacenamiento`.
Las etapas acumulan descartes en orden fijo: operación, tipo, ciudad, ubicación,
presupuesto y mínimos/máximos. `sin_dato` cuenta candidatos que sobreviven a esa
etapa sin el dato correspondiente. Las preferencias no descartan. Los motivos
generales y datos faltantes se cuentan sobre todo el catálogo, pueden solaparse
y no deben sumarse como anuncios únicos. Siempre se cumple:
`compatibles + pendientes + incompatibles = total_catalogo`.

La comparación de ciudad normaliza puntuación y tiene una equivalencia explícita
para Bogotá / Bogotá D.C. / Bogotá, D.C. Los nombres originales se conservan en
SQLite. El matching de barrio utiliza la identidad canónica de
`catalogo.geografia`, compartida con los filtros y el selector de la Consola.
Las zonas se comparan por igualdad normalizada; barrio y zona son alternativas
explícitas de ubicación, no requisitos acumulativos.

## Normalización geográfica y limitación aceptada

La implementación y evidencia de referencia están en
[Normalización geográfica v0.3](../consola/docs/GEOGRAFIA_V03.md).
El catálogo controlado versionado `catalogo/geografia/barrios.json` contiene una
semilla revisada de nombres por ciudad, con identificadores de sector catastral
y referencias de Catastro Bogotá. No es un listado completo de barrios
comerciales ni una certificación de coordenadas o linderos.

El adaptador contrasta `neighborhood` y `common_neighborhood`, conserva sus
originales y mantiene ciudad, zona, sector y edificio como conceptos separados.
Solo separa EDIF, EDIF. o EDIFICIO si el prefijo corresponde a un nombre
controlado completo. Admite calificadores estructurados de localidad y de
sector publicado; no usa similitud difusa ni toma la URL de búsqueda como
prueba de barrio. Por ejemplo, `LA CAROLINA EDIF CRIXTAL` y `LA CAROLINA` pueden
resolver la misma identidad; el edificio CAROLINA no convierte Rincón del Chicó
en La Carolina.

`Inmueble.geografia` conserva originales, identidad canónica, estado, motivos,
evidencias y versión; `Inmueble.edificio` contiene el edificio separado y
`Inmueble.barrio` el nombre confirmado, o `None` si no se puede resolver.
Un barrio confirmado diferente incumple el requisito. Una ubicación ambigua o
una solicitud histórica sin equivalencia controlada permanece pendiente, sin
confirmar ni inventar una correspondencia. Los nombres históricos resolubles
se interpretan en memoria sin reescribir las necesidades guardadas.

**Limitación conocida y aceptada para el cierre de v0.3:** en la instantánea
auditada de 427 inmuebles, 333 tienen barrio confirmado y **94 registros
conservan ubicación pendiente de verificar**. Incluyen nombres fuera de la
semilla y contradicciones entre barrio, barrio común o zona. Se preservan
íntegros, no se les asignan barrios artificialmente y no confirman el requisito
de barrio mientras exista ambigüedad. Resolverlos requiere revisión de fuentes
o ampliación documentada del catálogo controlado en un trabajo posterior.
La aceptación de esta limitación no equivale a validar sus ubicaciones.

En esa instantánea, el único barrio con anuncios sin contradicciones es La
Carolina; el selector no ofrece como opciones nuevas los textos ambiguos ni
todos los nombres del nomenclátor sin anuncios confirmados. Conserva búsqueda,
selección múltiple y etiquetas históricas. Los otros requisitos del matching
(precio y moneda, operación, tipo, habitaciones y área) siguen vigentes;
confirmar la geografía no confirma por sí solo una oportunidad completa.

La API de coincidencias y diagnóstico conserva su contrato completo. La tabla
HTML ordena y pagina mediante `consola/resultados.py`, usando el paginador del
catálogo; su paginación no limita el cálculo de indicadores o diagnóstico.

## Almacenamiento y migraciones

Se utiliza una base independiente `metro-consola.sqlite`, junto a `METRO_DB`.
`RADAR_CRM_DB` permite definir otra ruta. Las lecturas usan `mode=ro` y no crean
archivos; la primera escritura abre una transacción `BEGIN IMMEDIATE`, activa
claves foráneas y aplica la migración 1. Las tablas propias son
`consola_migraciones`, `consola_clientes` y `consola_oportunidades`, con índice
por cliente. Las necesidades se almacenan en JSON validado, con decimales como
texto para preservar importes. No hay DROP, reconstrucciones ni cambios a
`PRAGMA user_version`. Una versión de migración desconocida se rechaza para
evitar escribir sobre esquemas futuros. Los registros existentes se conservan.

La base original del scraper `metro.sqlite` sigue siendo de solo lectura.
La normalización histórica se persiste en la proyección auxiliar independiente
`metro-geografia.sqlite`, mediante una migración aditiva, transaccional e
idempotente. Sus tablas `migraciones` y `ubicaciones` conservan ID original e
interno, huellas del documento y reglas, originales, resultado y fecha.
No se borran inmuebles ni se ejecuta nuevamente scraping.

Las lecturas no crean ni migran la proyección. Solo aprovechan filas cuya huella
de documento y versión coincidan; si faltan o están obsoletas, recalculan en
memoria. Por ello una captura nueva no exige reprocesar inmediatamente la base.
El comando explícito `python -m catalogo.geografia` reprocesa el catálogo;
repetirlo sin cambios actualiza cero filas. La herramienta
`consola/tools/auditar_geografia.py` también invoca ese reprocesamiento y puede
escribir en la base auxiliar: no debe usarse como una consulta de solo lectura.

Las pruebas usan bases sintéticas y las validaciones reales crean CRM aislados.
Se verifican las huellas de las bases originales para detectar modificaciones.
Las bases SQLite y las evidencias locales están excluidas de Git.
