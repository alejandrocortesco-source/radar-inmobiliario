# Entrega local — identificación supervisada

10 de noviembre de 2026. Rama `develop`; HEAD conservado en `b6dddd9`. Estado inicial limpio. Sin conflictos, commits, tags, push, scraping externo, asociaciones reales ni despliegues. Las mutaciones y capturas de interfaz de esta validación usan exclusivamente bases sintéticas.

## Función y uso

Reiniciar el servidor local para cargar los cambios:

```powershell
.\.venv\Scripts\python.exe scraper/run.py serve
```

Abrir **Revisar publicaciones** (`/v0.6/identificacion`). **Analizar catálogo existente / reintentar** propone relaciones sin capturar. Comparar fichas, evidencias y todas las relaciones de un grupo antes de confirmar que es la misma unidad. Descartar conserva el rechazo; aplazar mantiene la revisión. **Asociaciones confirmadas → Deshacer agrupación** separa todo el grupo, con confirmación explícita, conservando publicaciones, decisiones comerciales e historial.

Solo las confirmaciones agrupan catálogo y recomendaciones. Los filtros se aplican primero a cada publicación íntegra. Se conserva acceso a todas sus fuentes y precios; el CSV sigue exportando publicaciones/ofertas. La identidad UUID5 original permanece. Corrección Wasi: una localidad explícita coincidente con la del barrio controlado deja de invalidar ese barrio.

## Componentes principales

- `catalogo/identificacion.py`: bloques de candidatos, comparación, reglas centralizadas, puntuación de similitud y huellas.
- `catalogo/persistencia/asociaciones.py`: contrato, migración aditiva, candidatos, auditoría, decisiones, grupos y reversión transaccional.
- `catalogo/modelos.py`, `consultas.py`, `servicio.py`: metadatos de agrupación, representante coherente, filtros, conteos, páginas y API.
- `catalogo/persistencia/_metrocuadrado.py`: interpretación conservadora de localidad/barrio explícitos de Wasi.
- `oportunidades/matching.py`, `automatizacion.py`: agrupación posterior al filtro individual, alternativas e integración incremental tras captura exitosa.
- `consola/identificacion.py`, plantillas y CSS: revisión paginada, comparación paralela y acciones. Navegación y fichas existentes presentan publicaciones vinculadas y conflictos de decisiones. `inicio.py` y `oportunidades.py` distinguen conteos físicos de publicaciones; `rutas.py` conserva CSV por publicación.
- `scraper/metro/web.py`: inyección del repositorio auxiliar en el servicio común.
- `catalogo/tests/test_identificacion.py`, `consola/tests/test_identificacion_ui.py`: regresiones nuevas. Dos aserciones históricas de diagnóstico se ajustaron a la etiqueta «publicaciones».

Documentación: rector, README principal y de módulos, mapa, índice, guías de captura y avisos temporales de informes históricos. [Reglas, esquema, migración y operación](IDENTIFICACION.md).

## Migración y operación

No hay comando de migración ni dependencias nuevas. Cinco tablas e índice auxiliares se crean de forma aditiva e idempotente al analizar/decidir. No cambia `user_version`, migración 1 ni almacenamiento de los scrapers. Una lectura no crea una base inexistente. La reversión funcional usa la interfaz; el código anterior puede dejar las tablas sin utilizar, sin borrarlas.

La identificación incremental precede al matching después de una captura completada. Se conservan decisiones al cambiar evidencia; fallos quedan registrados y pueden reintentarse. Si falla la propia escritura auxiliar, queda el log del proceso. No se añade cola, infraestructura, integración con Sheets ni horario automático.

## Validación realmente ejecutada

| Comprobación | Resultado |
| --- | --- |
| Suite final de catálogo | 247 aprobadas |
| Suite completa de scraper | 121 aprobadas |
| Consola, última suite completa | 300 aprobadas; cuatro fallos de aserciones de prueba |
| Repetición exacta de los cuatro casos después de corregir sus aserciones | 4 aprobadas; sin fallos pendientes |
| Chromium de la revisión nueva | 1440, 768 y 390 px; comparación, foco, confirmación y ausencia de desbordamiento de página |
| Integración sintética | Confirmación, descarte, aplazamiento, reversión, histórico, filtros, contadores, CSV y matching sin combinar atributos |
| Compilación Python y `git diff --check` | Correctos |
| Búsqueda documental sin distinguir mayúsculas del proveedor retirado | Cero menciones |
| Comprobación de enlaces documentales locales | Sin destinos inexistentes |

Los cuatro casos repetidos eran tres variantes de navegador que esperaban la etiqueta antigua «inmuebles» en conteos de publicaciones y una prueba nueva que buscaba un atributo DOM en otra vista. Se actualizaron las aserciones y se repitieron con éxito. La ejecución completa anterior de consola también aprobó sus 302 casos antes de añadir dos regresiones y completar la distinción de contadores. No se presenta ese resultado anterior como ejecución completa de la versión final. En conjunto se verificaron los 304 casos de consola vigentes. Solo quedó la advertencia conocida de deprecación de BlockingPortal de Starlette/AnyIO.

Comandos ejecutados: `python -m pytest -c catalogo/pytest.ini catalogo/tests`, `python -m pytest -c consola/pytest.ini consola/tests`, `python -m pytest -c scraper/pytest.ini scraper/tests` y repetición de consola con `--lf`. Se usó el intérprete `.venv`, `-q --tb=short` y directorios `--basetemp` distintos bajo `.tmp/identificacion-20261110/`. TestClient/Chromium se ejecutaron fuera del sandbox de Windows, conservando las mismas bases sintéticas. Los primeros intentos dentro del sandbox no cuentan como pruebas aprobadas.

Evidencia local no versionada: `.tmp/identificacion-20261110/documentacion.json` y capturas en `.tmp/identificacion-20261110/visual/`. Se inspeccionaron visualmente escritorio y móvil.

## Límites y pendientes

No se encontró un informe de viabilidad en las rutas documentales y diagnósticos disponibles; no se repitió un diagnóstico ni se inventaron resultados. La precisión y cobertura del motor con decisiones operativas reales quedan sin medir. Datos escasos pueden no generar candidatos; bloques con muchos anuncios parecidos pueden producir numerosas propuestas. La puntuación no garantiza identidad, particularmente en apartamentos del mismo edificio.

La aplicación local no autentica personas: registra `operadora local (sin autenticación)`. Deshacer disuelve el grupo entero. Si falta una fuente del grupo, debe restaurarse para revisarlo. No hay verificación desatendida nueva, despliegue ni Scheduler activo acreditados por esta tarea; consumo mensual, Cloud Run y adaptación Sheets siguen pendientes. Gemini no se configura ni interviene en identificación física.
