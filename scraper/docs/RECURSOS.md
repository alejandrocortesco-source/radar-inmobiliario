# Monitoreo de recursos

El monitor se ejecuta automáticamente al llamar a `Scraper.run()` o a `scrape` por consola. Envuelve el recorrido existente sin cambiar selectores, paginación, extracción, deduplicación, estados ni documentos de resultados. Usa `psutil==7.1.0` en Windows y Linux.

## Ejecutar y encontrar los CSV

Desde la raíz con el entorno existente:

```powershell
.\.venv\Scripts\python.exe -m pip install -r scraper/requirements.txt
.\.venv\Scripts\python.exe scraper/run.py scrape
```

Dentro de `scraper/`, con un entorno instalado allí: `.\.venv\Scripts\python.exe -m metro scrape`. El comando habitual sigue funcionando; al terminar imprime un resumen de recursos antes del resumen JSON que ya existía.

La carpeta predeterminada es `metrics/` junto a la base SQLite seleccionada. Para la base habitual:

* `scraper/data/metrics/resource_usage.csv`: una fila por invocación, con encabezado único y escritura protegida por bloqueo entre procesos.
* `scraper/data/metrics/samples-<fechaUTC>-<id>.csv`: serie temporal propia de cada invocación, que se vacía a disco después de cada muestra.

Los archivos anteriores se conservan. Cada invocación tiene un `measurement_id` distinto. Al reanudar, el `run_id` del scraping puede repetirse, pero la nueva fila representa sólo el tramo reanudado: no suma de nuevo el consumo anterior. No se generan mediciones retroactivas para ejecuciones previas a instalar el monitor. Los CSV quedan excluidos de Git.

Ejemplo pequeño, separado de la base original:

```powershell
.\.venv\Scripts\python.exe scraper/run.py --db scraper/data/resource-check.sqlite scrape --max-pages 1 --max-details 2 --resource-interval 0.1
```

`--resource-interval` controla la espera entre muestras: predeterminado **0.2 s**, permitido **0.05–60 s**. El tiempo efectivo incluye el trabajo de cada muestra y queda visible en `elapsed_seconds`. Un intervalo menor observa mejor los picos breves y añade más trabajo. `--metrics-dir scraper/data/otra-medicion` permite elegir la carpeta de CSV. No se cambia el directorio de la base ni se sobrescriben sus resultados.

## Interpretación de las columnas

| Columna | Significado |
|---|---|
| `started_at_utc`, `finished_at_utc` | Fecha y hora ISO 8601 en UTC |
| `duration_seconds`, `duration_minutes` | Duración total de `Scraper.run()`, medida con reloj monotónico |
| `cpu_seconds` | CPU de usuario + sistema consumida por Python y los descendientes observados, descontando el consumo previo de los procesos ya existentes |
| `cpu_average_percent_one_core` | `100 × cpu_seconds / duration_seconds`; 100 % equivale al uso continuo de un núcleo, 200 % a dos |
| `cpu_peak_percent_one_core` | Mayor porcentaje observado entre dos muestras; no se divide por el número de núcleos del equipo |
| `peak_tree_rss_bytes`, `peak_tree_rss_mib` | Máximo observado de la suma de RSS de Python y todos los descendientes vivos y legibles en la muestra |
| `peak_python_rss_mib`, `peak_children_rss_mib` | Máximos separados del proceso Python principal y del conjunto de hijos; pueden ocurrir en momentos distintos y **no deben sumarse** para obtener el pico total |
| `max_live_processes`, `observed_processes` | Máximo de procesos legibles simultáneos y número de identidades de proceso observadas |
| `samples`, `interval_seconds` | Número de muestras y espera configurada entre ellas |
| `status`, `run_id`, `resumed` | Estado final, ejecución del scraper y si esta invocación reanudó un avance |
| `headed`, `concurrency`, `delay_seconds`, `max_pages`, `max_details` | Configuración necesaria para comparar pruebas equivalentes |
| `platform`, `python_version` | Plataforma y versión del intérprete |
| `measurement_quality`, `warnings` | `sampled` si se pudo muestrear normalmente; `partial` si hubo incidentes de lectura/escritura |
| `cgroup_cpu_seconds`, `cgroup_peak_memory_bytes` | Campos opcionales de Linux con cgroup v2 disponible en `/sys/fs/cgroup`; diferencia de `cpu.stat:usage_usec` y máximo muestreado de `memory.current` |
| `samples_csv` | Ruta al archivo de muestras de esa invocación |

1 MiB = 1.048.576 bytes. Las celdas opcionales no disponibles quedan vacías, por ejemplo las de cgroup en Windows. No se sustituyen por cero. Los CSV usan UTF-8, separador coma, punto decimal y comillas CSV cuando hacen falta.

## Alcance y límites

El muestreador corre en un hilo y sigue recursivamente los procesos de Python: incluye el controlador Node de Playwright, Chromium y sus procesos de renderizado/GPU. Conserva lo ya observado cuando un hijo termina, identifica procesos por PID **y fecha de creación** para evitar confundir PIDs reutilizados, y sigue observando hijos conocidos aunque se desvinculen del árbol original. No suma de nuevo los campos de CPU de hijos acumulados por el padre.

La RAM es un **pico observado por muestreo**, no un máximo exacto del sistema. Un proceso o pico que nazca y termine entre muestras puede no observarse; puede faltar la última fracción de CPU antes de que un hijo desaparezca. La suma RSS también puede contar páginas compartidas más de una vez. El coste del propio monitor forma parte de la ejecución medida. El arranque de Python anterior a `Scraper.run()` y la instalación de dependencias no están incluidos.

Las métricas opcionales de cgroup v2 pueden ayudar a ver el conjunto del contenedor en Linux, incluyendo memoria que no figura en RSS. Su alcance es **todo el cgroup expuesto**: si está compartido con otros procesos, también los incluye. El código no modifica ni reinicia los contadores del cgroup. Si no están disponibles, las métricas de psutil siguen funcionando.

El bloque `finally` produce un resumen para ejecuciones completas, limitadas, bloqueadas, fallidas o canceladas mediante la cancelación normal de Python/Ctrl+C. Un cierre forzado, SIGKILL, OOM o apagado del sistema puede impedir escribir la fila final; las muestras ya volcadas pueden recuperarse. Un fallo del monitor o al escribir el CSV se informa en logs y no convierte un scraping correcto en fallido. No se recogen argumentos de los procesos, variables de entorno, cookies ni credenciales.

## Uso para dimensionar Cloud Run Jobs

Los datos permiten comparar duración y capacidad necesaria, pero **CPU consumida no equivale a CPU facturada**. Para presupuestar un Job hay que elegir vCPU y memoria asignadas y considerar el tiempo facturable de la instancia. Cloud Run Jobs factura su vida completa y aplica un mínimo de un minuto, según la [documentación oficial de precios](https://cloud.google.com/run/pricing) consultada el 24/10/2026.

Con las asignaciones elegidas, las unidades de cálculo son `vCPU asignadas × segundos facturables` y `GiB asignados × segundos facturables`. Luego se aplican las tarifas de la región, frecuencia de ejecuciones, reintentos, nivel gratuito y otros cargos pertinentes. No multiplicar directamente `cpu_seconds` o el pico RSS por una tarifa para presentar una factura estimada.

Conviene medir una búsqueda completa y comparar varias ejecuciones: una prueba de una página no representa todo el recorrido. Las mediciones locales orientan el dimensionamiento; se deben repetir dentro del contenedor Linux con los recursos elegidos. Los CSV de Cloud Run deben guardarse en almacenamiento persistente o exportarse antes de que termine el contenedor, cuyo filesystem es efímero. No se añadió un cálculo de dinero ni un despliegue en Google Cloud.
