# Radar Inmobiliario

Radar Inmobiliario es un proyecto para recopilar y revisar información pública de inmuebles.

El componente implementado actualmente es el **scraper de Metrocuadrado**: recorre búsquedas con Playwright, actualiza incrementalmente un catálogo por cambios de precio, guarda su trazabilidad en SQLite y ofrece una interfaz local con FastAPI para revisar y exportar los resultados.

La **Consola v0.1** permite consultar el catálogo visual en [http://127.0.0.1:8000/consola/](http://127.0.0.1:8000/consola/) dentro del mismo FastAPI. Consulta su [guía de inicio y uso](consola/README.md). El servicio y el modelo compartidos están en `catalogo/`; la interfaz técnica permanece en `/`.

Consulta las [instrucciones de instalación, ejecución y pruebas del scraper](scraper/README.md). Su código, dependencias, herramientas y documentación se encuentran en [`scraper/`](scraper/).

```text
radar-inmobiliario/
├── .gitignore
├── README.md
├── catalogo/
├── consola/
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
