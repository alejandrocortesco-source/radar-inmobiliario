# Correcciones funcionales y visuales de Consola v0.3

26 de octubre de 2026. Rama `feat/consola-v0.3`; sin commits ni push.

## Ciudad: causa y corrección

El control anterior era `<input list="crm_ciudades">` con un `datalist`, no un
selector cerrado. Admitía texto libre y no deshabilitaba el autocompletado del
navegador. La flecha de sugerencias no garantizaba elegir una ciudad del catálogo.

Ahora las ciudades se obtienen exclusivamente de `ServicioCatalogo.listar()` y
se agrupan usando `normalizar_ciudad`, la misma clave del matching. Con una sola
ciudad, el campo es de solo lectura y se envía automáticamente el valor real del
catálogo. En los 427 anuncios actuales es **Bogotá D.C.** Si hay varias ciudades,
se usa un `<select>` real. No se usa historial del navegador ni `datalist`.

Un registro histórico de una ciudad que ya no está en el catálogo se identifica
como guardado sin anuncios. No se cambia ni borra al consultarlo.

## Barrios y zonas

El selector múltiple permite buscar fragmentos, marcar varias opciones sin cerrar,
consultar etiquetas y eliminar cada una con ×. Se normalizan tildes, mayúsculas
y espacios para buscar, deduplicar y guardar. No se agrupan barrios parecidos por
inferencia. Las opciones se construyen con valores reales y su ciudad; los
valores seleccionados se transmiten como `barrio:<valor>` o `zona:<valor>` al
adaptador existente, y se guardan separados en `Necesidades.barrios` / `zonas`.

Al cambiar ciudad se conservan selecciones compartidas y se retiran las ajenas,
mostrando un aviso. Las ubicaciones históricas fuera del catálogo permanecen como
etiquetas identificadas; no se ofrecen como opciones nuevas. Se conserva la
captura manual adicional que ya existía, separada de las opciones del catálogo.

Sin JavaScript se ofrece el `<select multiple>` y un botón «Actualizar barrios»
que conserva el borrador, actualiza las opciones y notifica retiros sin guardar.
Si se intenta guardar una ciudad cambiada con selecciones ajenas, el servidor
también las revisa y exige al menos una ubicación válida si no queda ninguna.

No se agrega una biblioteca de UI ni otro servicio. El control usa HTML nativo,
checkboxes, búsqueda local y mejora progresiva; el valor enviado sigue siendo el
selector nativo. La normalización compartida se extrajo a
`oportunidades/normalizacion.py`, sin cambiar los límites del matching.

## Verificación secuencial del ciclo real

Antes de modificar el layout de resultados se comprobó desde Chrome:

1. Ciudad fija Bogotá D.C., sin desplegable ni texto libre.
2. Búsqueda «carolína» y selección del barrio real **LA CAROLINA**.
3. Cliente de prueba nuevo en un CRM aislado; operación arriendo, apartamento,
   presupuesto máximo **6.200.000 COP**, mínimo **180 m² construidos** y **3
   habitaciones**.
4. «Guardar y buscar coincidencias» devolvió **1 compatible y 0 pendientes**.
5. El resultado fue el anuncio real **3241-M2426122**, ID
   `fdc4dcdf-49f5-5cf8-a36e-961ab9351b1b`, con 180 m², 3 habitaciones, 4 baños y
   2 parqueaderos. Se verificó de nuevo después del cambio a tabla.

Se usaron los datos consolidados, sin consultar de nuevo el portal. No se cambió
ningún filtro para forzar el resultado. La herramienta
`consola/tools/validar_matching_real.py` comprobó también el caso por API y las
huellas de las bases originales; guardó sus datos en un CRM nuevo bajo `.tmp/`.
El catálogo y el CRM existentes no se borraron ni reemplazaron.

## Tabla empresarial

Las tarjetas se sustituyeron por una tabla con diez columnas: coincidencia,
ubicación, tipo, precio, área, habitaciones, baños, parqueaderos, fuente y
publicación. Reutiliza los estilos de `.catalog-table`, la región desplazable,
los formatos numéricos, el enlace a ficha, los iconos de publicación y `paginar`
del catálogo. Un indicador discreto distingue confirmada / por verificar, con
evidencia desplegable dentro de la fila.

Todos los encabezados ordenan ascendente/descendente antes de paginar. Los
importes COP se comparan numéricamente; los desconocidos permanecen al final
en ambas direcciones. El orden de área coincide con la superficie mostrada por
el catálogo; los requisitos conservan el tipo de área elegido en la oportunidad.
Los precios sin moneda no se convierten ni se presentan como COP confirmado.

Páginas de 12/24/48 filas, 24 por defecto. Los indicadores y el diagnóstico se
calculan sobre todo el catálogo, sin depender de la página. Los enlaces conservan
la oportunidad, los filtros, el orden y la página al consultar la ficha. En móvil
se mantiene la tabla con desplazamiento horizontal dentro de su propia región.
Se redujeron márgenes, sombras, tamaños de indicadores y elementos decorativos.

## Validación y límites

**455 pruebas aprobadas:** 155 de Consola, 210 de catálogo y 90 del scraper.
Se mantuvieron las pruebas existentes y se adaptaron los selectores y aserciones
del layout. La cobertura nueva incluye búsqueda normalizada, etiquetas,
selecciones históricas, ciudad única/múltiple, cambio sin JavaScript, guardado,
orden por columnas, decimales, nulos, paginación y regreso desde ficha. Se
comprobaron escritorio, móvil y el ciclo sin JavaScript.

Se conserva el alcance local, la arquitectura FastAPI/Jinja/SQLite y las APIs
existentes. El scraper y el esquema del catálogo no se modifican. El matching
sigue en memoria; la lista administrativa de clientes/oportunidades aún no tiene
paginación. El buscador con etiquetas necesita JavaScript; existe alternativa
nativa sin JavaScript. Moneda, antigüedad o disponibilidad desconocidas siguen
requiriendo verificación. Permanece la advertencia de deprecación de AnyIO en
Starlette. No hay Gemini, WhatsApp, Google Sheets ni nuevas integraciones.
