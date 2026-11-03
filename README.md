# Radar Inmobiliario

Radar Inmobiliario es un proyecto para recopilar y revisar información pública de inmuebles.

La **Consola v0.6** abre en [http://127.0.0.1:8000/v0.6/](http://127.0.0.1:8000/v0.6/): dashboard de cuatro secciones, clientes Activos/Inactivos y ficha individual para revisar coincidencias. Reutiliza catálogo, clientes, oportunidades y matching determinista; añade decisiones persistentes y una segunda capa opcional con Gemini Flash. Guardar una fuente no ejecuta scraping.

El catálogo detallado de v0.5 se conserva en `/v0.4/`, con filtros, fichas, comentarios, historial y exportaciones. `/consola/` y la interfaz técnica `/` mantienen compatibilidad. No se añadieron frameworks ni infraestructura.

- [Guía v0.6, Gemini, fuentes, pruebas y limitaciones](consola/docs/V06.md).
- [Documento rector vigente](RADAR_PROYECTO_RECTOR.md) e [instrucciones de trabajo](AGENTS.md).
- [Instalación y ejecución del scraper propio](scraper/README.md).
- [Catálogo](catalogo/README.md), [clientes y matching](oportunidades/README.md) y [guía de consola e interfaces anteriores](consola/README.md).

Inicio local desde la raíz:

```powershell
.\.venv\Scripts\python.exe scraper/run.py serve
```

Las evaluaciones reales de Gemini requieren `GEMINI_API_KEY` y un `GEMINI_MODEL` Flash disponible para la cuenta. Sin configuración, o ante error, el motor determinista permanece disponible y se informa la limitación. El objetivo de operación inferior a US$10/mes queda sujeto a medir consumo y alojamiento. No hay despliegue de producción ni migración a Sheets en esta entrega.

```text
radar-inmobiliario/
├── .gitignore
├── README.md
├── catalogo/
├── consola/
├── oportunidades/
└── scraper/
    ├── README.md
    ├── docs/
    ├── metro/
    ├── tests/
    ├── tools/
    ├── run.py
    ├── pytest.ini
    ├── requirements.txt
    ├── requirements.lock.txt
    ├── start-interface.ps1
    ├── Dockerfile
    └── .dockerignore
```

El repositorio Git y su historial pertenecen a esta raíz. Los entornos virtuales, credenciales, cachés y resultados locales quedan excluidos de Git. El nombre de la carpeta local puede diferir de `radar-inmobiliario`; no hace falta crear otra carpeta contenedora.
