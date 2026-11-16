# Validación local de Programación múltiple

16 de noviembre de 2026, America/Bogota. Trabajo exclusivo en el clon CloudRun,
rama `codex/ejecuciones-manuales`, HEAD conservado `7283bc48b52628c4d0695535ae43c2127dae7d66`.
La versión registrada continúa 0.13.1; se recomienda 0.14.0 para una futura entrega.
No hay commits nuevos, push, merge ni tags. El checkout original sigue limpio en
develop/d84f1dd. No hubo cambios productivos, scraping real, llamadas a portales,
SDK cloud operativos, secretos, despliegues ni cambios de Scheduler/bucket.

## Resultado implementado

CRUD de programaciones independientes, frecuencias diaria/semanal/única, selección
por búsqueda, zona fija Bogotá, vista previa de próximas fechas, duplicación pausada,
eliminación lógica, actividad asociada y conservación del historial existente.
Migración compatible del calendario compartido con copia de configuración previa,
identidad heredada para recibos, control de revisiones y recuperación explícita de
sincronizaciones fallidas. Un único Scheduler central, las mismas reservas/Job/lock
y la misma persistencia durable; no se reconstruyen scrapers ni matching.

La UI usa la identidad Radar y patrones Carbon con tabla compacta, detalle de fechas,
formulario contraído, menús secundarios, confirmación de eliminación, selects de
hora/minutos, errores de campo y spinner circular con verificación del backend.
El ciclo completo funciona con teclado y la creación/vista previa también sin JS.

## Pruebas realmente ejecutadas

| Ejecución | Aprobadas | Fallos/errores | Tiempo XML | Evidencia |
| --- | ---: | ---: | ---: | --- |
| Fase 1, previa a la UI | 144 | 0 | 14.276 s | phase1.xml |
| Consola completa | 599 | 0 | 428.525 s | consola-entrega.xml |
| Catálogo completo | 249 | 0 | 13.121 s | full-catalogo.xml |
| Scraper completo | 183 | 0 | 195.988 s | full-scraper.xml |
| Regresión final de programación/ejecución/persistencia | 167 | 0 | 52.148 s | aislamiento-final.xml |

Las evidencias están en `.tmp/multiple-20261116/`. No sumar las repeticiones como
casos distintos. La suite completa de consola fue recopilada antes del último caso
adicional de aislamiento. Después del ajuste final del gate del trabajador se
repitieron 167 pruebas del módulo y sus dependencias, incluyendo ese caso nuevo.
La fase 1 se aprobó antes de avanzar a la interfaz. La única advertencia de las
suites aprobadas es la deprecación existente de BlockingPortal en Starlette/AnyIO.

Se verificaron además compileall de ejecuciones/rutas/lanzador, git diff --check,
GET de la demostración local con HTTP 200 y aviso sintético, y working trees/HEAD.

### Cobertura relevante

- Varias programaciones, edición aislada, activación, pausa, duplicación, borrado con confirmación e historial conservado.
- Selección de distintas búsquedas, incluidas claves de las tres fuentes; configuradores originales de los tres portales en regresión.
- Horas/minutos/fechas inválidas, cambio de semana/mes/año, año bisiesto, UTC/Bogotá y fechas únicas consumidas.
- Concurrencia de entregas, coincidencias, conflicto manual, lock ocupado, recibos tras retención y ausencia de relanzamiento.
- Cursor y reservas durables, reconstrucción del servicio, respuesta de lanzamiento perdida, reconciliación y trabajador tardío/duplicado.
- Fallos de escritura inicial y confirmación final, reintentos CAS/precondiciones y preservación de escrituras concurrentes en los tests existentes de generaciones.
- Migración repetida, configuración lunes 09:00 con tres búsquedas, lectura sin escritura, recibos anteriores, datos históricos y rechazo de esquema futuro.
- Recuperación de pending anterior y nuevo; la operación de otro horario no cancela un trabajador ya reservado; pausa propia antes del claim sí lo impide.
- Búsquedas eliminadas/inactivas revalidadas por el trabajador; omisión sin tocar portales.
- HTTP, Origin, contrato OIDC/cabeceras, nombres canónicos, revisión obsoleta y errores saneados.
- Chromium 1440×900, 768×1024 y 390×844, flujo de acciones, foco, labels, formulario cerrado, scroll interno y ausencia de desbordamiento de página.
- Spinner para actividad confirmada, retirada al pasar a completada y movimiento reducido; no se simulan porcentajes.

### Intentos que no se cuentan como aprobados

El primer comando de backend no había creado el padre del basetemp: errores de
preparación corregidos antes de repetir. Los primeros casos nuevos también
corrigieron construcción de fixtures y el escenario temporal de atrasos. Chromium
identificó nombres accesibles variables por mensajes dentro de labels; se fijaron
nombres estables. La primera suite completa de consola terminó con 593 aprobadas
y dos fallos de foco en el test adaptado. Las repeticiones focalizadas mostraron
la carrera de navegación: focus podía dirigirse al formulario todavía oculto de
la página anterior. Se esperó visibilidad y se comprobó foco con expect; también
se protegió el foco de un campo ya elegido frente a un toggle tardío. El resultado
completo posterior es el de la tabla. Hubo ejecuciones interrumpidas para aislar
o incorporar protecciones; no se presentan como aprobadas. Se conservan sus logs.

## Capturas y revisión local

Capturas sintéticas en `.tmp/multiple-20261116/screenshots/`:
`multiple-1440.png`, `multiple-768.png`, `multiple-390.png`,
`formulario-1440.png`, `formulario-768.png`, `formulario-390.png` y estados del
calendario migrado. Se inspeccionaron visualmente escritorio, formulario y móvil.

Desde el clon CloudRun:

```powershell
.\.venv\Scripts\python.exe consola/tools/revisar_programaciones.py --port 8770
```

Abrir `http://127.0.0.1:8770/v0.6/ejecuciones/programaciones`. Usa datos nuevos
en `.tmp/programaciones-demo-UUID`, GCS/Scheduler/Cloud Run simulados y red externa
bloqueada. No reconfigurar ese lanzador con recursos de producción.

## Archivos creados y modificados

- `RADAR_PROYECTO_RECTOR.md`
- `consola/docs/PROGRAMACION.md`
- `consola/durable.py`
- `consola/ejecuciones.py`
- `consola/static/ejecuciones.css`
- `consola/templates/v06/_ejecucion06.html`
- `consola/templates/v06/_ejecuciones_historial06.html`
- `consola/templates/v06/_programacion06.html`
- `consola/tests/test_programacion.py`
- `docs/README.md`
- `ejecuciones/control.py`
- `ejecuciones/disparador.py`
- `ejecuciones/programacion.py`
- `ejecuciones/worker.py`
- `consola/docs/PROGRAMACION_MULTIPLE.md`
- `consola/docs/VALIDACION_PROGRAMACION_MULTIPLE.md`
- `consola/static/programaciones.js`
- `consola/templates/v06/_actividad_programaciones.html`
- `consola/templates/v06/_estado_ejecucion.html`
- `consola/templates/v06/programaciones06.html`
- `consola/tests/test_calendarios.py`
- `consola/tools/revisar_programaciones.py`
- `ejecuciones/calendarios.py`

## Riesgos y pendientes operativos

La entrega está implementada y validada localmente. No está desplegada ni validada
contra servicios cloud reales, conforme a la restricción del usuario. La estrategia
de corte necesita evitar escritores de programación 0.13.1 tras la conversión:
primero lectores compatibles en disparador/trabajador y después las revisiones web
que editan horarios, con respaldo y verificación autorizados. No basta con cambiar
una etiqueta web. La revisión privada comparte datos con producción.

El pulso cada minuto supone 43.200 peticiones en 30 días aunque no haya capturas;
no crea un Scheduler por horario, pero consume disparador, lecturas y logs. El costo
total y el objetivo inferior a USD 10/mes no están medidos. Una única consumida puede
dejar el pulso central activo hasta una gestión explícita que lo pause. Las capturas
adicionales son otro consumo. No se promete costo cero ni una cadencia cloud probada.

Se mantienen los límites de historial (30 días/100 terminales/2 MB) y hay un máximo
de 100 programaciones incluyendo eliminadas. Las omisiones por coincidencia se
registran; no se encolan ni se recuperan con capturas tardías. Las señales procesan
un lote acotado de ocurrencias y conservan el cursor para continuar auditoría tras
un reinicio prolongado. Revisar estas políticas si crece el volumen.

Diseño, migración idempotente, compatibilidad, reversión, costos y comandos de prueba:
[Programación múltiple](PROGRAMACION_MULTIPLE.md).
