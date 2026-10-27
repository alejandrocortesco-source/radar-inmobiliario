# Corrección de Consola v0.3 — 26 de octubre de 2026

Este informe conserva el diagnóstico inicial. Los selectores y la presentación
actual en tabla con paginación se describen en [Usabilidad v0.3](USABILIDAD_V03.md).

Trabajo realizado sobre `feat/consola-v0.3`, conservando los cambios anteriores,
sin nuevas ramas ni commits, sin modificar el scraper ni el modelo del catálogo.

## Diagnóstico y causa raíz

Se reprodujo en Chrome la búsqueda de la oportunidad guardada
`587d8df3-ea7b-4807-94e4-0d0726b17045`. La API devolvía HTTP 200 y una lista vacía;
no se observaron errores JavaScript al reproducirla. El catálogo de la Consola,
`/api/catalog` y el servicio de matching coincidían en **427 inmuebles**.

Rutas resueltas desde la raíz de este repositorio:

- Catálogo: `scraper/data/metro.sqlite` (lectura mediante `CatalogoSQLite`).
- Clientes y oportunidades: `scraper/data/metro-consola.sqlite`.

La necesidad guardaba **«Bogotá, D.C.»**, mientras los 427 anuncios tenían
**«Bogotá D.C.»**. La normalización anterior producía `bogota, d.c.` frente a
`bogota d.c.`; la comparación de igualdad descartaba la ciudad por la coma.

Antes de modificar la lógica se cambió solo la grafía en una copia del modelo
en memoria. El resultado pasó de **0 a 147 candidatos**, con **21 requisitos
confirmados** y **126 pendientes**. Los demás criterios quedaron idénticos.
Esto aisló el problema de normalización; no se encontraron rutas distintas ni
un catálogo vacío. La oportunidad original no se editó.

La corrección elimina diferencias de puntuación de ciudad y reconoce
explícitamente las grafías Bogotá, Bogotá D.C. y Bogotá, D.C. No se cambian
presupuestos, mínimos, ubicación solicitada ni tipos para producir resultados.
No se agrupan barrios por similitud de nombre ni se infiere información ausente.

## Evidencia del diagnóstico después de corregir

Para la misma oportunidad existente, sin editar sus registros:

| Filtro acumulativo | Antes | Descartados | Restantes |
| --- | ---: | ---: | ---: |
| Operación | 427 | 0 | 427 |
| Tipo de inmueble | 427 | 42 | 385 |
| Ciudad | 385 | 0 | 385 |
| Barrio o zona | 385 | 0 | 385 |
| Presupuesto | 385 | 35 | 350 |
| Área mínima 200 m² construidos | 350 | 203 | 147 |

Los 147 resultados se separan en 21 compatibles confirmados por datos y 126
pendientes de verificar. Hay 307 ofertas de venta sin moneda estructurada en
el catálogo; no se presume COP ni se confirman presupuestos en esos casos.

La nueva API `/api/oportunidades/{id}/diagnostico` incluye las rutas SQLite,
etapas acumulativas, incompatibilidades por anuncio y motivos agregados. Los
motivos agregados pueden solaparse, por lo que se distinguen de los descartes
únicos de las etapas. Datos desconocidos conservan candidatos pendientes;
un incumplimiento indispensable conocido los excluye.

## Prueba fundamental con inmueble real

Se creó una oportunidad en un **CRM de validación nuevo**, usando el catálogo
real en lectura. Se repitió la captura completa desde Chrome con el botón
«Guardar y buscar coincidencias».

| Dato | Valor publicado y solicitado |
| --- | --- |
| Anuncio | `3241-M2426122` |
| ID interno | `fdc4dcdf-49f5-5cf8-a36e-961ab9351b1b` |
| Operación | Arriendo (anuncio con venta y arriendo) |
| Tipo | Apartamento |
| Ciudad publicada / ingresada | Bogotá D.C. / Bogotá, D.C. |
| Barrio | LA CAROLINA |
| Presupuesto máximo | 6.200.000 COP |
| Área mínima construida | 180 m² |
| Habitaciones / baños / parqueaderos mínimos | 3 / 4 / 2 |
| Resultado | **1 compatible confirmado: el mismo anuncio; 0 pendientes** |

Publicación almacenada: [3241-M2426122](https://www.metrocuadrado.com/inmueble/venta-apartamento-bogota-la-carolina-3-habitaciones-4-banos-2-garajes/3241-M2426122).
No se volvió a consultar el portal; la prueba usa sus datos ya consolidados.

El diagnóstico real dio 427 → 3 por operación → 1 por tipo → 1 tras ciudad,
ubicación, presupuesto, habitaciones, baños, parqueaderos y área. No se relajó
ninguna condición respecto del anuncio seleccionado.

También se probó una ciudad de validación ausente del catálogo: **0 resultados**,
con explicación visible de los incumplimientos y ciudad identificada en 427
anuncios. En las pruebas sintéticas se verificó el cero por habitaciones mínimas
100, manteniendo los demás criterios, con explicación del filtro de habitaciones.

La herramienta `consola/tools/validar_matching_real.py` reproduce el caso desde
la API y genera un CRM y evidencia JSON en una carpeta UUID de `.tmp/`. Las
huellas SHA-256 de `metro.sqlite` y `metro-consola.sqlite` se conservaron:

```text
metro.sqlite:         89f561386617e9bf4523e26dee469ba43f706f8fb79881dcc0bbe7ab93ada5fe
metro-consola.sqlite: 9b67e1ef1e82fd4832ef6398c38128a96797563f5622ffa27f5fb6f8320d7e32
```

## Interfaz y pruebas

Se conservó la paleta y la arquitectura Jinja/FastAPI, con tres áreas numeradas,
campos agrupados, nombre visible, acción principal destacada, indicadores reales,
diagnóstico expandible, tarjetas con precio, estado, características y enlaces.
El catálogo conserva filtros, exportación, fichas y navegación. Los resultados
aparecen en la misma página tras guardar; también sigue disponible su ruta propia.

**432 pruebas aprobadas:** 132 de Consola, 210 de catálogo y 90 de scraper.
Se probaron los nuevos flujos a 1440, 768 y 390 px, incluido JavaScript desactivado,
y las regresiones existentes de navegación, persistencia y scraper. Se revisó
visualmente el caso real en Chrome de escritorio y móvil a 390 px, sin
desbordamiento horizontal ni errores capturados en consola. Se comprobó
también el mensaje real sin coincidencias y `git diff --check`.

## Límites conservados

- Cumplimiento según los datos del catálogo no garantiza disponibilidad comercial.
- Moneda ausente, antigüedad no estructurada y otros datos faltantes siguen
  pendientes; no se inventan valores.
- Observaciones libres requieren revisión manual.
- La lista de resultados y el diagnóstico se calculan en memoria, sin paginación.
- No se añaden equivalencias geográficas aproximadas ni nombres de barrios
  alternativos sin evidencia; futuras ciudades pueden requerir alias explícitos.
- Permanece una advertencia de deprecación de AnyIO en Starlette, sin fallos.
- No se implementan Gemini, WhatsApp ni integraciones nuevas.
