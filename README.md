# Radar Inmobiliario

Radar Inmobiliario es un proyecto para recopilar y revisar información pública de inmuebles.

La **Consola v0.9 — Fincaraíz (desarrollo local)** abre en [http://127.0.0.1:8000/v0.6/](http://127.0.0.1:8000/v0.6/): dashboard de cuatro secciones, clientes Activos/Inactivos y ficha individual para revisar coincidencias. Integra Fincaraíz, Wasi y Metrocuadrado reutilizando catálogo, clientes, oportunidades y matching determinista; conserva decisiones persistentes y una segunda capa opcional con Gemini Flash. Guardar una fuente no ejecuta scraping.

Todos los precios y presupuestos inmobiliarios son COP. El presupuesto se compara directamente con el precio numérico, con límites inclusivos, sin solicitar ni verificar moneda y sin conversiones. Los campos históricos de moneda se conservan como metadatos.

El catálogo detallado de v0.5 se conserva en `/v0.4/`, con filtros, fichas, comentarios, historial y exportaciones. `/consola/` y la interfaz técnica `/` mantienen compatibilidad. No se añadieron frameworks ni infraestructura.

- [Anunciantes v0.7, contactos y límites de datos](consola/docs/V07.md).
- [Guía v0.6, Gemini, fuentes, pruebas y limitaciones](consola/docs/V06.md).
- [Documento rector vigente](RADAR_PROYECTO_RECTOR.md) e [instrucciones de trabajo](AGENTS.md).
- [Instalación y ejecución del scraper propio](scraper/README.md).
- [Catálogo](catalogo/README.md), [clientes y matching](oportunidades/README.md) y [guía de consola e interfaces anteriores](consola/README.md).

Inicio local desde la raíz:

```powershell
.\.venv\Scripts\python.exe scraper/run.py serve
```

Las evaluaciones reales de Gemini requieren `GEMINI_API_KEY` y un `GEMINI_MODEL` Flash disponible para la cuenta. Sin configuración, o ante error, el motor determinista permanece disponible y se informa la limitación. El objetivo de operación inferior a US$10/mes queda sujeto a medir consumo y alojamiento. No hay despliegue de producción ni migración a Sheets en esta entrega.

## Estado y ramas

- `develop`: rama de todo nuevo desarrollo y commit. Política operativa: [GIT_WORKFLOW.md](GIT_WORKFLOW.md).
- `v0.8.0`: tag anotado de la entrega funcional v0.8 en `4781daeb9adefc310028d40dcec88795657530eb`; el commit documental posterior no cambia esa versión. Las rutas `/v0.6/`, `/v0.4/` y demás existentes se conservan.
- `v0.6`: referencia remota histórica de esa entrega; no desarrollar ni publicar nuevos commits en ella.
- `main`: conserva su función prevista de referencia estable y su contenido en `069fc89`; esta organización no integra v0.8 allí. `master` es exclusivamente local y no equivale automáticamente a `main`.
- `release/v0.5`: conserva el cierre funcional `291ce82b`.
- `v0.4` y `feat/consola-v0.3`: ramas históricas. El nombre `v0.4` no cambia que el hito funcional cerrado sea v0.5.

La herramienta es privada para Mónica, con unos 30 clientes activos. Se mantiene la arquitectura existente; Sheets sigue como adaptación futura. Cloud Run Jobs tiene preparación local, sin despliegue ni operación desatendida real validada. El presupuesto objetivo vigente es inferior a 10 USD/mes, sujeto a medición.

## Archivos y documentación

La distribución vigente de módulos, datos, documentos privados y temporales está en el [mapa de archivos](docs/ESTRUCTURA.md). El [índice documental](docs/README.md) permite distinguir guías vigentes e informes históricos. Se conserva una sola carpeta de trabajo; las versiones se identifican con Git, no duplicando el proyecto.

El repositorio Git y su historial pertenecen a esta raíz. Los entornos virtuales, credenciales, cachés y resultados locales quedan excluidos de Git. El nombre de la carpeta local puede diferir de `radar-inmobiliario`; no hace falta crear otra carpeta contenedora.

## Ampliación Wasi — v0.8

La consola integra Metrocuadrado y Wasi mediante el catálogo común. Configuración de búsquedas, credenciales externas, captura incremental, recuperación y preparación de Jobs: [guía Wasi](scraper/docs/WASI.md). La operación real desatendida y el coste siguen pendientes; no se desplegó.

## v0.9 — Fincaraíz (desarrollo local)

Tercera fuente integrada en «Agregar fuente» del inicio, catálogo, anunciantes, CSV y matching. Conserva las rutas actuales. [Configuración y ejecución](scraper/docs/FINCARAIZ.md) · [Validación y límites](scraper/docs/VALIDACION_FINCARAIZ.md). Commit local de v0.9 autorizado posteriormente, sin tag, push ni despliegue; `v0.8.0` conserva su referencia.
