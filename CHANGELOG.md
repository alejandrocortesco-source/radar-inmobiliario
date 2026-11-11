# Changelog

## 0.10.0 — 2026-11-11

Funcionalidad MINOR compatible sobre v0.9, en `develop`. Conserva rutas y UUID de publicaciones; etiqueta anotada `v0.10.0`. Sin despliegue ni scraping externo en esta entrega.

- Identificación común y explicable entre Metrocuadrado, Wasi y Fincaraíz, con candidatos incrementales, puntuación de similitud, evidencias y versión del algoritmo.
- Revisión humana para confirmar, descartar, aplazar y deshacer asociaciones; auditoría local y persistencia aditiva en la base auxiliar. Ampliar grupos exige revisar todas sus relaciones.
- Catálogo y matching agrupan únicamente asociaciones confirmadas, después de evaluar cada publicación; conservan alternativas, precios, contactos e históricos. Contadores distinguen inmuebles y publicaciones; CSV conserva publicaciones/ofertas.
- Corrección conservadora de localidad/barrio explícitos en Wasi; comparación separada de áreas privadas, construidas y publicadas.
- Documentación revisada y referencias al proveedor anterior retiradas. Versión de API y consola unificada en 0.10.0; el identificador técnico seguía en 0.4.0.

Validación del versionado (11 de noviembre): seis pruebas de integración y Chromium aprobadas nuevamente con bases sintéticas, después de actualizar versión y cabecera.

Validación previa documentada: catálogo 247 casos, scraper 121 y consola 304 (300 en la última suite completa y cuatro aserciones corregidas y repetidas con éxito). Chromium: 1440, 768 y 390 px, con bases sintéticas. Detalles en [informe de implementación](docs/ENTREGA_IDENTIFICACION.md).

Límites: similitud no equivale a probabilidad; precisión real sin medir; operadora local sin autenticación de personas; deshacer separa el grupo completo. Cloud Run, Sheets y costos operativos siguen pendientes de validación. No se incorpora IA, fotografías descargadas ni servicios pagos para identidad física.
