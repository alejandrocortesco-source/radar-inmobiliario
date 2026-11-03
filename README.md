# Radar Inmobiliario

**Proyecto privado para Mónica:** herramienta sencilla para registrar necesidades de clientes, mantener un catálogo de inmuebles de Metrocuadrado y encontrar coincidencias útiles. Prioridades: **simplicidad, reutilización del código existente y costo operativo inferior a USD 20/mes**, sujeto a medición.

**Primera referencia para decisiones de producto y desarrollo:** [Documento rector](RADAR_PROYECTO_RECTOR.md).  
**Instrucciones permanentes para Codex:** [AGENTS.md](AGENTS.md).

## Estado y ramas

- **v0.5 cerrada:** cierre técnico en el commit `291ce82b` del 3 de noviembre de 2026, preservado como `release/v0.5`.
- **`main`:** versión estable y documentación rectora. No desarrollar aquí nuevas funciones de v0.6.
- **`v0.6`:** rama activa de trabajo para el nuevo dashboard y la evolución del matching.
- **`v0.4` y `feat/consola-v0.3`:** ramas históricas que se conservan. El nombre de la rama `v0.4` no significa que la versión funcional cerrada sea v0.4.

## Componentes existentes

- [`scraper/`](scraper/README.md): extracción con Playwright, actualizaciones incrementales, nuevos, cambios de precio, revisión conservadora e historial.
- [`catalogo/`](catalogo/README.md): modelo compartido, identidad estable, consultas y API.
- [`oportunidades/`](oportunidades/README.md): clientes, oportunidades, persistencia local y **matching por reglas ya implementado**.
- [`consola/`](consola/README.md): vistas existentes, filtros, fichas, detalle y exportación. La interfaz histórica está en `/consola/` y la siguiente vista en `/v0.4/`, según la documentación técnica.

## Próxima etapa: v0.6

Dashboard de entrada con actividad reciente, clientes y oportunidades, estado de catálogo, agregar URL y nuevo cliente. La revisión detallada se hace en la **ficha del cliente con coincidencias**; el catálogo completo permanece como acceso secundario. Se incorporarán persistencia de preselecciones/descartes, ajustes de criterios y Gemini aprovechando el motor ya existente. La captura manual precede a WhatsApp.

**Tecnología:** Python, FastAPI, Jinja2, JavaScript, SQLite para desarrollo; Google Sheets es el objetivo de persistencia en producción. El despliegue futuro es Cloud Run. No se ha decidido migrar a Firestore.

Antes de cada implementación, contrastar esta guía con el código vigente y conservar sus datos, identificadores, rutas y pruebas.
