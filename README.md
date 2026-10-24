# Radar Inmobiliario

Radar Inmobiliario es un proyecto para recopilar y revisar información pública de inmuebles.

El componente implementado actualmente es el **scraper de Metrocuadrado**: recorre una búsqueda con Playwright, guarda anuncios y su trazabilidad en SQLite y ofrece una interfaz local con FastAPI para revisar y exportar los resultados.

Consulta las [instrucciones de instalación, ejecución y pruebas del scraper](scraper/README.md). Su código, dependencias, herramientas y documentación se encuentran en [`scraper/`](scraper/).

```text
radar-inmobiliario/
├── .gitignore
├── README.md
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
