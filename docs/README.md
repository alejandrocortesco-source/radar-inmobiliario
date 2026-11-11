# Documentación de Radar Inmobiliario

Punto de entrada a las guías y a la evidencia del proyecto. La entrega vigente es v0.10.0 — identificación supervisada (versionado y sincronización autorizados el 11 de noviembre de 2026); `v0.8.0` conserva la entrega publicada anterior; las rutas heredadas no identifican la versión ni la rama de trabajo.

## Referencias vigentes

| Consulta | Documento |
| --- | --- |
| Inicio y ejecución local | [README principal](../README.md) |
| Decisiones funcionales y límites | [Documento rector](../RADAR_PROYECTO_RECTOR.md) |
| Instrucciones para agentes | [AGENTS.md](../AGENTS.md) |
| Ramas, versiones y publicación | [Flujo Git](../GIT_WORKFLOW.md) |
| Carpetas y conservación de archivos | [Mapa de archivos](ESTRUCTURA.md) |
| Consola y navegación | [Guía de consola](../consola/README.md) |
| Configuración y pruebas de la consola | [V06](../consola/docs/V06.md) |
| Entrega local de identificación y pruebas | [Informe del 10 de noviembre](ENTREGA_IDENTIFICACION.md) |
| Identificación física y revisión humana | [Reglas, migración y operación](IDENTIFICACION.md) |
| Catálogo y persistencia | [Guía de catálogo](../catalogo/README.md) |
| Clientes, oportunidades y matching | [Guía de oportunidades](../oportunidades/README.md) |
| Instalación y ejecución de capturas | [Guía del scraper](../scraper/README.md) |
| Actualización incremental | [Captura incremental](../scraper/docs/INCREMENTAL.md) |
| Wasi y preparación de Cloud Run Jobs | [Guía Wasi](../scraper/docs/WASI.md) |
| Fincaraíz v0.9 | [Guía Fincaraíz](../scraper/docs/FINCARAIZ.md) |
| Validación local de Fincaraíz | [Resultados y límites](../scraper/docs/VALIDACION_FINCARAIZ.md) |
| Medición de recursos | [Recursos](../scraper/docs/RECURSOS.md) |

Las guías técnicas explican la implementación. El documento rector gobierna las decisiones funcionales. Los resultados de pruebas corresponden al momento de cada ejecución; este índice no acredita pruebas nuevas.

## Informes históricos y evidencias

| Hito | Informe |
| --- | --- |
| Correcciones de captura v0.3 | [Corrección](../consola/docs/CORRECCION_V03.md) |
| Geografía v0.3 | [Geografía](../consola/docs/GEOGRAFIA_V03.md) |
| Usabilidad v0.3 | [Usabilidad](../consola/docs/USABILIDAD_V03.md) |
| Interfaz v0.4 y evidencias | [V04](../consola/docs/V04.md) |
| Filtros v0.5 | [Filtros](../consola/docs/FILTROS_V05.md) |
| Fechas y búsquedas v0.5 | [Fechas y búsquedas](../consola/docs/FECHA_Y_BUSQUEDAS_V05.md) |
| Implementación e integración v0.6 | [Apartados históricos de V06](../consola/docs/V06.md) |
| Anunciantes v0.7 | [V07](../consola/docs/V07.md) |
| Verificación original del scraper | [Validación](../scraper/docs/VALIDACION.md) |
| Implementación y revisión de Wasi v0.8 | [Validación Wasi](../scraper/docs/VALIDACION_WASI.md) |

Se conservan los nombres, ubicaciones y referencias de los informes para mantener su trazabilidad. Sus autorizaciones antiguas no son instrucciones para nuevas publicaciones.

Los diagnósticos privados del equipo pertenecen a `.local/diagnosticos/`, no a esta carpeta compartida. No enlazar su contenido desde documentos públicos ni incorporarlo a commits o imágenes Docker.
