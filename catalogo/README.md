# Catálogo — modelo común, persistencia y servicio

Este componente usa únicamente la biblioteca estándar de Python 3.12. El modelo
no depende de extracción ni persistencia; el adaptador SQLite abre explícitamente
una base existente en modo de solo lectura. No importa el scraper ni hace HTTP.
Las pruebas aprovechan pytest, ya incluido en el proyecto.

## Identidad y procedencia

Un `Inmueble` representa un anuncio con un `Origen`. No supone que dos anuncios
sean el mismo inmueble físico. El ID interno es UUID5 del par fuente/ID original,
codificado como un arreglo JSON UTF-8 sin espacios. El namespace fijo y esa
codificación son un contrato de persistencia; cambiarlo cambiaría las identidades.

La fuente es una clave técnica ASCII en minúsculas. El ID original es texto: se
recortan espacios exteriores, pero se preservan ceros iniciales y mayúsculas.
El ID interno no depende de URL, precio, atributos, búsquedas ni fechas. En este
paso se calcula sin modificar las claves del scraper. Al persistirlo en otro
almacenamiento debe conservarse exactamente el mismo valor.

`Origen` conserva ID, URL, tipo/operación originales y presencias por búsqueda.
Los IDs de búsqueda son opacos y únicos dentro de una fuente. Su generación y la
normalización de URLs pertenecen a futuros adaptadores específicos de cada fuente.

## Datos desconocidos y ofertas

- `None` significa desconocido. Tuplas vacías significan que no hay elementos
  conocidos; no prueban que el anuncio carezca de fotos, características u ofertas.
- Una operación conocida con precio desconocido es una `Oferta` con precio `None`.
  Una oferta dual tiene una oferta de venta y otra de arriendo, cada una con su
  precio y moneda; no existe un precio único ambiguo para el inmueble.
- Importes y áreas usan `Decimal` finitos. Los importes y áreas conocidos son
  positivos; cero no se utiliza como sustituto de desconocido. Habitaciones,
  baños y parqueaderos sí admiten cero cuando es un dato conocido.
- Moneda es un código de tres letras mayúsculas o `None`. El modelo valida el
  formato, no interpreta símbolos ni convierte divisas. No impone precisión
  monetaria o moneda por país; esas reglas pertenecen a la normalización.
- Áreas publicadas, construidas y privadas se distinguen y están en m². Solo se
  rellenarán si la unidad está confirmada o existe conversión explícita verificable.
  Una unidad desconocida queda pendiente del adaptador; nunca se supone m².
- Tipo desconocido es `None`; `OTRO` significa tipo publicado sin categoría común.
  Los valores originales se conservan en `Origen`.
- Fotos son enlaces y características son textos normalizados. Este paso no
  descarga imágenes ni reproduce todo el documento original de la fuente.

Las fechas son `datetime` con zona horaria o `None`. Primera observación, última
presencia en listado, última extracción y actualización publicada por la fuente
son conceptos diferentes; no se rellenan unos con otros. Se admiten zonas
horarias diferentes; la serialización futura deberá usar UTC. No se infiere una
fecha de actualización del anunciante a partir de una ejecución del scraper.

La disponibilidad se deriva de las búsquedas: una presencia activa prevalece;
después, posiblemente retirado; una presencia desconocida impide confirmar la
retirada global. Sin búsquedas, el estado es desconocido. Retirado significa
ausente de las búsquedas conocidas, nunca vendido o eliminado del portal.
Calidad de ficha y revisión pendiente son independientes de disponibilidad.

## Contrato de filtros v0.1

`FiltrosCatalogo` define una consulta validada, todavía sin ejecutarla:

- Texto libre: coincidencia parcial en título, descripción e ID original.
- Ubicación: ciudad, zonas y barrios. Comparación textual sin distinguir
  mayúsculas ni tildes, sin inferir equivalencias geográficas.
- Tipos, operación, moneda, precio, área, habitaciones, baños, parqueaderos,
  estratos, fuente, búsqueda, disponibilidad y revisión pendiente.
- Entre campos se aplica AND; dentro de zonas, barrios, tipos o estratos se aplica
  OR. Colección vacía o `None` no restringe el campo. Rangos inclusivos.
- Desconocidos no cumplen una restricción sobre ese atributo. Sin restricción
  permanecen en los resultados. No se convierte un desconocido en cero.
- Precio y moneda deben corresponder a la misma oferta que la operación elegida.
  Filtrar u ordenar por precio requiere operación y moneda para no mezclar
  monedas ni venta/arriendo. No hay conversión monetaria.
- El filtro de área selecciona explícitamente publicada/construida/privada; no
  usa otra clase de área como sustituto. Por defecto selecciona publicada.
- Búsqueda requiere fuente. Con búsqueda elegida, disponibilidad se evalúa en
  esa búsqueda; sin ella se usa el estado agregado del inmueble.
- Orden por ID ascendente, precio ascendente/descendente o última verificación
  descendente. Esta última usa la fecha de presencia del origen, o de la búsqueda
  seleccionada. Ausentes al final y desempate por ID interno ascendente siempre.
- Paginación por límite (1–200; predeterminado 30) y desplazamiento desde cero.

Estas reglas se validarán con consultas reales al implementar el paso 4.
Actualmente se verifican la definición de filtros y la compatibilidad con los
parámetros antiguos de la API; no se implementa el motor nuevo de filtrado.

## Adaptador SQLite de solo lectura — paso 2

`catalogo.persistencia.contrato.RepositorioCatalogo` define dos operaciones:
`listar()` devuelve una tupla con todo el catálogo y `obtener(id_interno)`
devuelve un inmueble o `None` si no existe. No expone conexiones ni filas SQL.

`catalogo.persistencia.sqlite.CatalogoSQLite` implementa ese contrato.
Acepta una ruta explícita; por defecto resuelve `scraper/data/metro.sqlite`
desde el repositorio, independientemente del directorio de trabajo.
Su construcción no abre ni crea archivos.

```python
from catalogo.persistencia.sqlite import CatalogoSQLite

repositorio = CatalogoSQLite()
inmuebles = repositorio.listar()
ficha = repositorio.obtener(inmuebles[0].id_interno) if inmuebles else None
```

- Abre la base con URI `mode=ro` y `PRAGMA query_only=ON`. No importa
  `Store`, no crea tablas, no migra, no copia la base y no actualiza registros.
- Una transacción de lectura mantiene ficha y presencias en la misma instantánea.
  Se respeta WAL; no se usa `immutable=1`, que podría omitir datos confirmados.
  SQLite puede necesitar sus archivos auxiliares WAL/SHM para la coordinación
  normal de lectores y escritores.
- Lee `properties` como catálogo global. No toma la última ejecución como catálogo
  ni sustituye la ficha conservada por una captura parcial posterior.
- Agrupa `search_memberships` por anuncio. Reutiliza la URL de búsqueda guardada
  como ID opaco y conserva todos sus estados y fechas.
- Recupera de `jobs` y `runs` únicamente la configuración de una captura
  correcta/parcial cuyo documento coincide con el catálogo. Así puede reconocer
  una moneda configurada para esa captura sin asumir COP ni usar la configuración
  de una revisión posterior fallida.
- La traducción específica de Metrocuadrado queda en `_metrocuadrado.py`;
  modelos e identidad del paso 1 permanecen independientes.
- Si falta la base, lanza `FileNotFoundError` con su ruta sin crear directorios.
  Si el esquema es incompatible, la base es ilegible o hay un documento JSON
  inválido, lanza `ErrorCatalogoSQLite`. Los anuncios con JSON inválido no se omiten
  silenciosamente; un anuncio descubierto aún sin ficha sí es un registro válido
  con atributos desconocidos.

### Límites de esta entrega

La lectura completa carga las fichas en memoria. Para obtener una ficha por UUID5
se recorre la lista de IDs originales (el UUID no es reversible) y se carga solo
el documento elegido. Es deliberado para no añadir un índice o una tabla al scraper;
será necesario medir este coste al crecer el catálogo.

No se ejecutan aún los filtros ni la paginación definidos en el paso 1.
El modelo común contiene las ofertas de la ficha global. La capa opcional de
revisión del paso 3 conserva además el historial y las evidencias técnicas.

Áreas sin unidad confirmada y fechas publicadas sin zona horaria quedan como
`None`. Números ambiguos, no finitos o inválidos no se adivinan. Los precios duales
se separan usando la operación y los importes originales ya guardados, sin volver
a visitar el portal. Características agrupadas se presentan con su título como
prefijo y fotografías se mantienen como URLs, sin descargarlas.

Se requiere el esquema incremental existente (`properties`, `search_memberships`,
`jobs` y `runs`). Una base anterior debe ser preparada por su componente propietario;
este adaptador nunca ejecutará su migración.

## Servicio común y FastAPI — paso 3

`ServicioCatalogo` recibe un `RepositorioCatalogo` y ofrece `listar()` y
`obtener(id_interno)` para consumir el modelo común sin depender de HTTP.
Opcionalmente recibe un `RepositorioRevision` para conservar documentos y
evidencias de la API técnica. Ese contrato adicional no obliga al futuro
almacenamiento de negocio a reproducir todas las tablas del scraper.

`catalogo/api.py` ofrece `crear_router(proveedor_servicio)`: la aplicación
inyecta el servicio, el almacenamiento y la normalización específica de búsquedas.
El router se incluye una sola vez en `metro.web.app`; no hay otro servidor.

Compatibilidad mantenida:

- `GET /api/catalog`: conserva `state`, `search_url`, `limit`, `offset`, el
  orden por ID del portal y el formato `total/items/limit/offset`. Los valores
  originales del resumen no se reemplazan por valores normalizados distintos.
- `GET /api/properties/{property_id}`: acepta el ID original y, adicionalmente,
  el UUID interno. El campo `id` de la respuesta sigue siendo el ID original.
- Ambas respuestas agregan `id_interno` sin eliminar o renombrar campos previos.
- `run_id` conserva la selección de instantáneas. Una captura parcial reciente
  no sustituye la ficha fiable global; al seleccionar esa ejecución se muestra
  su captura parcial y se mantiene `catalog_data` por separado.
- Se conservan trabajo, procedencias, búsquedas, historial de precios y documentos
  originales. Las columnas JSON del trabajo siguen siendo cadenas, como antes.
- `/api/properties` (lista por ejecución), ejecuciones, reportes, exportaciones
  y páginas técnicas mantienen sus rutas. Catálogo HTML, ficha HTML y exportación
  reutilizan el servicio, sin copiar las consultas de la ficha.
- Base ausente o ilegible: HTTP 503, sin inicializar `Store`, crear base o migrar.
  Ficha inexistente: HTTP 404. Parámetros HTTP inválidos: HTTP 422.

`Store.catalog()` queda como entrada compatible que delega al servicio;
se eliminó su consulta SQL anterior. El adaptador es el único propietario de
las consultas de catálogo/ficha; la selección de documento y la proyección de
la respuesta están en el servicio.

Para mantener `python -m metro serve` desde `scraper/` sin instalar otro
paquete, `metro.paths` incorpora la raíz del repositorio a la ruta de importación
solo si existe el componente hermano `catalogo/`. El servicio web debe ejecutarse
con ambos componentes presentes. El Dockerfile actual sigue siendo un Job de
extracción; una futura imagen web deberá incluir también el componente compartido.

Los filtros nuevos y la paginación del contrato v0.1 siguen pendientes del paso 4.
Solo se conserva el comportamiento de los parámetros que ya existían. La lectura
completa sigue cargándose en memoria; no se añadió caché ni índices ni migraciones.

## Verificación

Desde la raíz, con el entorno existente:

```powershell
.\.venv\Scripts\python.exe -m pytest -c catalogo/pytest.ini catalogo/tests
.\.venv\Scripts\python.exe -m pytest -c scraper/pytest.ini scraper/tests
```

Quedan fuera de esta entrega: interfaz de Mónica, adaptador Sheets, migraciones,
historial general de cambios, nuevas fuentes, oportunidades, matching y despliegue.
