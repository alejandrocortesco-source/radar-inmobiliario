# Changelog

## 0.11.0 — 2026-11-11

Entrega MINOR en `develop`, posterior al tag `v0.10.0` (`91802de`). Incluye el commit ya publicado `a9f6992` de matching manual/Gemini y la protección de acceso implementada posteriormente. Conserva rutas históricas, identidades y datos; etiqueta anotada `v0.11.0`.

- «Buscar coincidencias» es determinista; solo la solicitud explícita «Evaluar con Gemini» autoriza llamadas. Novedades persistentes, caché, concurrencia y decisiones independientes.
- Adaptador Gemini con esquema estructural inline y validación local completa. La validación auténtica anterior documentó HTTP 200, persistencia, presentación y reutilización de caché; no se repite al publicar. Ver [informe saneado](consola/docs/GEMINI_AISLAMIENTO.md).
- Middleware central para JWT IAP ES256 con audiencia de Cloud Run directo, caché JWKS y rechazo cerrado. Todas las páginas/API/estáticos quedan protegidos salvo GET/HEAD `/health` exacto; documentación deshabilitada en modo IAP.
- Desarrollo local sin login Google, explícito y limitado a loopback; prohibido en Cloud Run. Origin estricto en escrituras y política `same-origin` en formularios.
- Variables, preparación futura de IAP/IAM/OAuth, dependencias criptográficas y pruebas sintéticas. El Word privado queda excluido de Git y del contexto Docker.

Compatibilidad durante 0.x: el arranque web requiere `RADAR_AUTH_MODE=local` en desarrollo o configuración IAP completa; las escrituras de clientes API deben enviar Origin. Esto cambia los requisitos de acceso anteriores, sin migrar el modelo de negocio ni reconstruir módulos. La versión aumenta por funcionalidad, no por la sincronización Git.

Cloud Run, persistencia en nube, integración consola/Job y Sheets siguen pendientes. Este versionado no acredita despliegue, operación desatendida ni costos mensuales.

Verificación nueva de publicación (11 de noviembre): **753 pruebas aprobadas**, en procesos independientes: 385 consola, 247 catálogo y 121 scraper, con Chromium en escritorio/tablet/móvil y bases sintéticas en `.tmp/publicacion-v011-20261111/`. Versiones de módulo/API/consola consistentes, enlaces locales, `pip check`, revisión del índice y `git diff --check` correctos. Solo la advertencia conocida BlockingPortal de Starlette/AnyIO. No se llamaron Gemini ni portales reales; la evidencia auténtica anterior no se presenta como una prueba nueva.

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
