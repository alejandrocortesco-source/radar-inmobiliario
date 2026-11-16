# Changelog

## 0.13.1 — 2026-11-16 (revisión privada)

- Conserva la programación automática semanal y el flujo durable compartido con ejecuciones manuales.
- Reconoce el ID corto y el nombre completo del Scheduler configurado, normalizados a una identidad canónica para deduplicación.
- Añade diagnóstico detallado de Wasi por etapas, evidencia privada acotada y advertencias recuperadas en el informe.
- Validación: pruebas aisladas documentadas y una captura individual Wasi completada, con dos páginas, 69 anuncios y guardado durable confirmado. El fallo intermitente de las 09:00 no se reprodujo y su causa sigue pendiente.
- Registro de versión en Git; no cambia despliegues, programación activa ni diseño. Sin tag nuevo.

## 0.13.0 — 2026-11-16 (revisión privada)

- Programación general de búsquedas por días y hora de Bogotá, con guardado,
  activación futura, pausa, próximas fechas y estimación semanal de lotes/capturas.
- Scheduler con OIDC hacia disparador interno, CAS en GCS, recibos de ocurrencias,
  omisión de conflictos y recuperación conservadora. Mismo Job durable, fuentes,
  métricas finales, cobertura y bloqueo que Manual; sin Gemini ni reintentos completos.
- Sincronización verificable y registro acotado de cambios; incertidumbre bloquea
  inicios y conserva configuración anterior para corrección explícita.
- Origen Manual/Automático, hora prevista/real y motivos de omisión en historial.
- Sin migración SQLite, alteración de snapshots históricos ni producción. Recurso
  Scheduler diferido hasta activación explícita; entrega desactivada.

## Sin publicar — 2026-11-16 (informes de revisión)

- Clasificación final compartida del informe, separada del motivo inicial de
  relectura. Comparación de precios fiables anterior/final, sin tratar success
  como prueba de igualdad y sin cambiar datos o decisiones de extracción.
- Conciliación exhaustiva de procesados, estados no satisfactorios y resultados
  sin evidencia; pendientes aparte. Reutilizados y releídos son subconjuntos.
- Históricos derivados de su generación exacta en modo inmutable, sin reescribir
  control o snapshots; límites visibles y contadores originales disponibles.
- Pruebas sintéticas comunes para las tres fuentes y evidencia responsive. Revisión
  privada de web y Job, sin ejecutar scraping ni alterar tráfico de producción.

## Sin publicar — 2026-11-15 (Job de revisión)

- Wasi cierra anuncios ProductFruits reconocidos aunque el host no tenga altura,
  usando el diálogo y el control normal Close dialog. Maneja apariciones tardías y
  consecutivas con límites de cierres y tiempo, sin botones comerciales ni clics forzados.
- Evita doble despacho de Buscar/Siguiente; conserva verificaciones de listado,
  filtros y cobertura. Una ventana desconocida, ambigua o persistente conserva
  incompleto con diagnóstico fijo y no aplica ausencias.
- La nueva imagen del Job se construye desde el estado actual, conservando la
  corrección de paginación Metrocuadrado. No modifica web ni producción.

- Metrocuadrado reconoce las dos rutas de listado verificadas, con hostname y path
  exactos. Conserva estructura, página activa, identificadores principales y cobertura;
  los destacados repetidos no impiden un avance real.
- Pruebas Chromium aisladas de las dos rutas, respuestas ajenas o inválidas, falta
  de avance y cobertura incompleta sin aplicación de ausencias.
- Cambio compatible sin migración; la entrega se identifica por commit y digest.
  Sin nuevo tag ni publicación en producción. La validación operativa queda pendiente
  de una captura manual autorizada en Radar Central.

## 0.12.3 — 2026-11-13

- Wasi reconoce el contenedor ProductFruits y permite un único cierre normal con
  botón explícito Close/Cerrar. No fuerza clics ni elimina elementos del portal.
- Mantiene comprobación de filtros, renovación del listado y cobertura; un bloqueo
  no resuelto conserva el resultado incompleto y no confirma ausencias.
- Radar separa incidencias de listado y anuncios, con mensaje comprensible y
  códigos técnicos fijos; no copia trazas o contenido del portal al informe.
- Se preparan imágenes web y Jobs para actualizar solo los componentes de revisión.

## 0.12.2 — 2026-11-13

- Corregir lectura de generaciones GCS y comprobación del bloqueo vigente; los
  reintentos CAS recuperan cambios concurrentes en vez de releer una versión anterior.
- Consultar el progreso sin escrituras web sobre un trabajador activo, compatible
  con la imagen existente del Job. Mantenimiento protegido también por CAS.
- Reconciliar cierres con Cloud Run y distinguir actividad confirmada de estado por
  verificar, con nombre, hora, seguimiento y referencias técnicas en detalle.
- Pruebas sintéticas con el SDK real y objetos versionados, carreras, locks vivos,
  lanzamientos inciertos y actualización del aviso en escritorio, tablet y móvil.

## 0.12.1 — 2026-11-13

Radar Central sustituye el recuadro Agregar fuente de Inicio y el nombre visible
Ejecuciones. Resume hasta tres búsquedas con estado y acceso a la ejecución manual.
La gestión de búsquedas se abre desde Radar Central, conservando formularios,
validaciones, endpoints POST, historial y bloqueo de escritura. Las rutas de
seguimiento siguen operativas. No cambia scrapers, Jobs ni matching.

## 0.12.0 — 2026-11-13

Entrega compatible en la rama local autorizada `codex/ejecuciones-manuales`, sin
push, merge ni tags. Página Ejecuciones: selección estricta de búsquedas activas,
Job durable secuencial, progreso durante el bloqueo, informe y control GCS acotado.
Reutiliza los tres scrapers y matching determinista, con guardado remoto confirmado
y recuperación de lanzamientos inciertos. IAP y Origin existentes; sin Scheduler.
La revisión de prueba comparte snapshot y recursos con producción y no recibe su
tráfico. Detalles y límites: [Ejecuciones](consola/docs/EJECUCIONES.md).

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
