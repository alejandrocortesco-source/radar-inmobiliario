> Actualización del candidato: versión local 0.14.0 y barrera control.version=2. El procedimiento vigente está en [RELEASE_014](../../deployment/RELEASE_014.md). La evidencia inicial siguiente es histórica, sin despliegue.

# Programación múltiple — implementación local, versión propuesta 0.14.0

16 de noviembre de 2026. Base: `7283bc4`, rama `codex/ejecuciones-manuales`, exclusivamente en `Radar-CloudRun-20261111/repo`. No se cambió la versión registrada 0.13.1 ni se publicó la entrega. No se modificó el repositorio original.

## Resultado

Se extiende el calendario compartido existente hacia programaciones con identidad estable, nombre, selección por fuente/ID de búsqueda, frecuencia diaria/semanal/única, días, hora, zona America/Bogota, estado, fechas de creación/modificación, próxima ejecución y referencia al último resultado. Permite reutilizar una búsqueda en varios horarios. Crear/editar/activar/pausar/duplicar/eliminar no solicita un Job.

La nueva página es `/v0.6/ejecuciones/programaciones`, accesible desde Radar Central. Tiene resumen operativo, tabla compacta con detalle de fechas, formulario inicialmente contraído y actividad manual/automática. La selección de hora/minutos usa desplegables. La vista previa es calculada por el backend y no escribe datos. Las búsquedas se agrupan por portal. Hay confirmación de eliminación y campos con validación específica. La actividad conserva enlaces a los informes existentes.

La presentación usa los tokens, tipografía y colores actuales con referencias de [tablas Carbon](https://www.carbondesignsystem.com/building-blocks/core/components/data-table/guidelines) e [indicadores accesibles](https://www.carbondesignsystem.com/building-blocks/core/components/inline-loading/accessibility), sin instalar Carbon. El spinner compartido solo aparece para running/saving con verificación activa del backend; desaparece con el estado terminal. Respeta movimiento reducido y no presenta porcentajes. Una consulta fallida de la actividad marca el estado por verificar.

## Arquitectura conservada

OIDC -> disparador privado -> control GCS/CAS -> reservas existentes -> mismo Cloud Run Job -> mismo trabajador secuencial y lock compartido -> snapshots confirmados.

Se reutilizan `Programacion.submit`, `reserve`, `ControlGCS`, `ServicioEjecuciones`, reconciliación, `run_manual` y `EstadoGCS`. No hay otra base, otro Job de captura ni otro sistema de procesamiento. No se cambian los scrapers ni matching.

Un único recurso Scheduler existente actúa como señal cada minuto (`* * * * *`) en modo múltiple. Cuando no vence ninguna programación, el disparador solo lee control; no restaura snapshots, no reconcilia Jobs ni inicia scrapers. Se eligió esta cadencia para admitir cualquier minuto y ejecuciones únicas sin crear un Scheduler por programación. El modo anterior conserva su cron hasta una modificación explícita que confirme la conversión.

Cada señal selecciona ocurrencias posteriores al cursor/effective_after. Las ordena por hora e ID estable. En una coincidencia la primera reserva elegible inicia un lote; las restantes se registran Omitidas por ocupación. Una captura manual incompatible tiene el mismo efecto. No se introduce una cola ni un relanzamiento completo. Esta política conserva el comportamiento operativo anterior.

La clave durable incluye programación, revisión y hora UTC. La programación migrada conserva la fórmula de identidad anterior para reconocer recibos preexistentes. Reserva, recibo, cursor y referencia última se escriben en una sola mutación CAS. Dos instancias/reintentos no pueden reclamar la misma ocurrencia. Un trabajador duplicado o tardío no puede volver a iniciarla. La pausa o edición de otra programación no afecta a un trabajador ya iniciado.

Las entregas con más de 15 minutos de retraso se registran omitidas. Un reinicio procesa el cursor persistido: no inventa capturas exitosas ni recupera atrasos mediante scraping. Se procesan como máximo 100 ocurrencias por señal; el resto permanece pendiente del cursor para la siguiente señal, dentro de los límites de auditoría existentes. La frecuencia única se consume también si fue omitida y no se reactiva por reiniciar; para programarla de nuevo se exige editar su fecha a una futura.

## Esquema, migración y recuperación

Se lee `control.version=1`; la primera escritura múltiple exige `control.version=2` y se añade un espacio aditivo `schedules_version=1` con `schedules`, indexado por ID inmutable. `schedule` sigue siendo el coordinador y contiene el gate de sincronización. `schedule_legacy` conserva íntegra la configuración original. Se conservan runs, recibos, auditoría, búsquedas y campos ajenos. No se modifica SQLite ni un snapshot histórico.

`plans()` proyecta controles anteriores en memoria sin escribir. `migrate()` es idempotente y asigna un ID determinista a Programación general, conservando selección, estado, días, HH:MM y revisión anteriores. La fecha histórica de creación se deriva de effective_after, porque el esquema anterior no tenía otro dato. La configuración lunes 09:00 con tres búsquedas se convierte en una programación semanal equivalente. Se toma un cursor de corte para no recuperar ejecuciones anteriores a la migración. La lectura sola no cambia Scheduler ni ejecuta la migración productiva.

La primera operación explícita reserva pending por CAS, guardando configuración anterior y propuesta completa. Sincroniza/verifica el mismo Scheduler y solo entonces confirma colección y coordinador. Si falla la sincronización o el CAS final, queda pending durable, sin nuevas reservas automáticas autorizadas. Después de 90 segundos se permite recuperar mediante otro Guardar/Pausar explícito; ninguna visita activa por su cuenta. Las revisiones obsoletas reciben conflicto. Los tokens de una ocurrencia antigua no pueden consumir ni actualizar una programación editada.

Eliminar crea una marca de borrado: no elimina runs, recibos ni referencias históricas. Los límites originales del registro siguen vigentes: 30 días/100 terminales/2 MB; no se promete retención ilimitada. Las referencias pueden apuntar a informes fuera de retención. La colección está limitada a 100 programaciones, incluidas las eliminadas, para acotar crecimiento; alcanzar ese límite requiere revisar conservación, no borrar silenciosamente historial.

### Compatibilidad y corte futuro

El código nuevo lee controles antiguos y acepta el contrato de disparo anterior mientras no se haya confirmado modo múltiple. El endpoint anterior de guardado sigue operativo para un calendario antiguo y rechaza modificar un coordinador múltiple. Se guarda una copia para reversión explícita sin borrar datos nuevos.

**No desplegar solo la web ni volver sin más a una imagen antigua.** Un binario 0.13.1 no entiende la nueva colección y podría sobrescribir el coordinador si se deja como escritor de programación. Un futuro corte autorizado debe actualizar primero trabajador y disparador con lectores de ambos formatos y después las revisiones web que permitan editar programación, evitando escritores antiguos durante la conversión. Se debe verificar su configuración efectiva, respaldar control y conservar digests para reversión. El tráfico general y la revisión privada comparten datos: 0% de tráfico no significa aislamiento.

La reversión operativa exige deshabilitar y confirmar el gate/Scheduler, comprobar trabajadores y seleccionar explícitamente qué calendario restaurar desde schedule_legacy. Conservar colección, recibos e historial. Este documento no ejecuta ese procedimiento ni autoriza un despliegue.

## Pruebas y evidencias

Los resultados de esta tarea se registran en `VALIDACION_PROGRAMACION_MULTIPLE.md`. XML, logs y capturas están en `.tmp/multiple-20261116/`. Se usan únicamente bases sintéticas, almacenamiento GCS en memoria y APIs simuladas. No se llamó a servicios productivos, SDK autenticados contra producción ni portales.

La fase 1 pasó 144 pruebas antes de implementar UI. Se repitieron/ampliaron pruebas tras integrar la presentación. Los intentos fallidos y las correcciones se distinguen de los resultados finales en el informe de validación.

## Revisión local segura

Desde este clon, con su entorno de desarrollo existente:

```powershell
.\.venv\Scripts\python.exe consola/tools/revisar_programaciones.py --port 8770
```

Abrir `http://127.0.0.1:8770/v0.6/ejecuciones/programaciones`. El lanzador crea `.tmp/programaciones-demo-UUID`, usa los dobles de prueba y bloquea red externa/subprocesos; no toma credenciales ADC. Muestra un aviso de demostración. Cada arranque crea datos nuevos. No es un servidor operativo ni una prueba contra Google Cloud. Ctrl+C lo detiene. No usar `cloud.ps1`, `consola.cloud` ni el bucket operativo para esta revisión.

Para repetir pruebas (crear primero `.tmp/multiple-revision`):

```powershell
New-Item -ItemType Directory -Force .tmp/multiple-revision
.\.venv\Scripts\python.exe -m pytest -c consola/pytest.ini consola/tests --basetemp=.tmp/multiple-revision/consola -q
.\.venv\Scripts\python.exe -m pytest -c catalogo/pytest.ini catalogo/tests --basetemp=.tmp/multiple-revision/catalogo -q
.\.venv\Scripts\python.exe -m pytest -c scraper/pytest.ini scraper/tests --basetemp=.tmp/multiple-revision/scraper -q
```

## Impacto y límites pendientes

No hay recursos creados, despliegues, cambios Scheduler/control productivos, capturas reales, commits, push, merge ni tags. El horario operativo anterior sigue independiente de estos archivos locales.

Un pulso por minuto supone 43.200 solicitudes en 30 días, aunque no haya capturas; por eso tiene más actividad que el cron semanal anterior. Reutiliza un solo Scheduler y servicio, sin nuevos cargos por cantidad de programaciones Scheduler. Consume peticiones/CPU del disparador, lecturas GCS y logs. No se puede afirmar costo cero ni garantizar el presupuesto de USD 10 sin medir tamaño de control, latencia, duración de solicitudes, región y nivel gratuito compartido. Una ejecución única consumida no vuelve a capturar; el pulso central puede seguir habilitado hasta una gestión explícita que pause el conjunto, por lo que también puede tener consumo en reposo. Las capturas adicionales dependen de horarios y búsquedas; son un costo distinto. Si la frecuencia de uso resulta muy baja, una optimización futura podría reducir señales o ajustar el próximo despertar, pero requiere su propia validación de sincronización y fallos. No se introdujo esa complejidad ahora.

No se validó la nueva cadencia en Cloud real ni una transición mixta de imágenes desplegadas. Se requiere una futura autorización operativa, confirmar las revisiones compatibles y medir consumo antes de habilitarlo. La versión semántica recomendada es 0.14.0 por la ampliación funcional; las APIs internas de programación durante 0.x cambian de calendario único a colección. La recomendación no crea una versión ni un tag.
