# Mapa de archivos y conservación

## Estructura del proyecto

Una sola carpeta de trabajo y un solo repositorio: no crear carpetas como copias v0.8 o v0.9. Las versiones se recuperan con Git según [su política](../GIT_WORKFLOW.md).

| Ubicación | Contenido | Conservación |
| --- | --- | --- |
| Raíz | README, instrucciones, decisiones y política Git | Versionado; puntos de entrada estables |
| `catalogo/` | Modelo común, filtros, identidad, geografía, adaptadores y pruebas | Versionado; no mover por cambios de versión |
| `consola/` | FastAPI, Jinja2, CSS, JavaScript, pruebas y herramientas de interfaz | Versionado; conservar imports, plantillas y rutas |
| `oportunidades/` | Clientes, necesidades, matching, decisiones y proveedor Gemini | Versionado; reglas separadas de presentación |
| `scraper/metro/` | Captura e interfaz técnica de Metrocuadrado | Versionado |
| `scraper/fincaraiz/` | Adaptador público de Fincaraíz sobre el motor incremental común | Versionado |
| `scraper/wasi/` | Acceso y captura de Wasi | Versionado |
| `scraper/examples/` | Configuraciones de ejemplo sin secretos | Versionado |
| `scraper/tools/` y `consola/tools/` | Utilidades de cada componente | Versionado; revisar si una utilidad escribe datos antes de usarla |
| `scraper/tests/`, `catalogo/tests/`, `consola/tests/` | Pruebas y fixtures sintéticos | Versionado |
| `docs/` | Índice general y organización del proyecto | Versionado; sin datos privados |
| `consola/docs/` y `scraper/docs/` | Guías técnicas, informes históricos y evidencia asociada | Versionado; no renombrar hitos ni trasladarlos sin revisar enlaces y herramientas |
| `Dockerfile.jobs` y `scraper/Dockerfile` | Preparación de contenedores | Versionado; conservar contextos y rutas COPY |
| `scraper/data/` | Bases operativas, respaldos, inspecciones, logs y mediciones | Solo local, excluido de Git; no mover ni borrar con el servicio activo |
| `.local/diagnosticos/` | Documentos privados del equipo | Solo local; excluido de Git y del contexto Docker de Jobs |
| `.tmp/` | Evidencias nuevas, bases sintéticas y resultados temporales | Solo local; una subcarpeta única por tarea |
| `.venv/` y cachés de Python/pytest | Entorno y archivos generados | Solo local; mantener donde las herramientas los esperan |

Las carpetas de caché y los temporales preexistentes de cada componente se conservan en su ubicación. No son copias de la app ni versiones nuevas. Las siguientes tareas deben preferir `.tmp/<tarea>-<fecha>-<identificador>/` desde la raíz y registrar allí sus evidencias; no borrar ejecuciones anteriores para reutilizar un nombre.

## Datos y archivos privados

- Metrocuadrado utiliza por defecto `scraper/data/metro.sqlite`; el CRM usa una base auxiliar independiente y Wasi su almacenamiento técnico. Las rutas exactas y sus variables están en las guías de cada módulo.
- Mover una base exige un cambio operativo específico y la revisión de procesos activos, configuración y respaldos. Esta organización no migra bases ni cambia rutas predeterminadas.
- Los secretos permanecen en sus ubicaciones externas protegidas. No trasladarlos a documentación ni confundir una carpeta ignorada por Git con un almacén seguro de secretos.
- Git no respalda archivos ignorados. Conservar los respaldos de datos existentes; cualquier copia externa debe protegerse y definirse por separado. No subir datos operativos para limpiar el estado Git.
- No borrar, compactar, fusionar ni sobrescribir bases, logs, capturas o diagnósticos como parte de una limpieza general.

## Organización local del 10 de noviembre de 2026

Se revisó la estructura existente y se conservó la separación funcional de los módulos. Los informes y evidencias históricos permanecen en sus rutas por trazabilidad. El mapa anterior del README se sustituyó por este inventario vigente.

El único traslado de un archivo preexistente es:

| Origen anterior | Destino local | Motivo |
| --- | --- | --- |
| `docs/wasi/diagnostico-red-2026-11-08.md` | `.local/diagnosticos/wasi/diagnostico-red-2026-11-08.md` | Separar un diagnóstico privado de la documentación compartida |

El traslado conserva los bytes del archivo y se verifica mediante SHA-256. Las menciones a la ubicación anterior en informes históricos describen el estado de aquel momento y no deben sustituirse globalmente. Las carpetas vacías que queden no contienen archivos pendientes.

La evidencia técnica de esta operación se conserva localmente en `.tmp/organizacion-local-20261110/`. Esta guía no acredita pruebas funcionales de la app ni una publicación en GitHub.

## Antes de organizar de nuevo

1. Consultar el estado Git, esta guía y las referencias de la ruta que se pretenda mover.
2. Clasificar el archivo como código, guía vigente, histórico, dato operativo, privado o temporal.
3. Comprobar el destino, conservar contenido y evitar sobrescrituras.
4. Actualizar enlaces vigentes si hay un traslado; conservar hechos históricos.
5. Verificar hashes, alcance del diff, exclusiones y las pruebas pertinentes al cambio.
6. Informar lo cambiado y distinguir trabajo local de commit y publicación. No incrementar la versión funcional por organizar documentación.
