# Radar Inmobiliario | Documento rector

**Fecha:** 3 de noviembre de 2026  
**Estado:** visión y decisiones aprobadas para v0.6. El estado técnico se contrasta con el código antes de desarrollar.  
**Referencia técnica:** hito de v0.5, commit `291ce82b6ee83884d5501630b5da9d5e47dd8c61`, originalmente en la rama histórica `v0.4`.

> **Regla central:** construir la herramienta que necesita Mónica, no una plataforma inmobiliaria general. Reutilizar y proteger lo que ya funciona.

## 1. Propósito, usuaria y límites

Radar Inmobiliario ayuda a Mónica, agente inmobiliaria individual, a encontrar ofertas para personas que buscan vivienda para sí mismas. La necesidad principal es ahorrar tiempo al capturar búsquedas, actualizar el catálogo, comparar inmuebles con las necesidades de cada cliente y revisar opciones para compartir personalmente.

Escala de referencia: unos **30 clientes activos**, cientos o eventualmente algunos miles de anuncios, no decenas de miles de usuarios simultáneos. Objetivo de costo operativo: **menos de USD 20 mensuales**, sujeto a medición real. La simplicidad de uso y de mantenimiento prevalece sobre una escalabilidad hipotética.

No convertir el producto en marketplace, CRM corporativo, portal público o motor de envío automático.

## 2. Modelo mental del negocio

- **Cliente:** persona que busca vivienda. Normalmente tiene **una oportunidad activa**; se admiten otras por historial o excepción, pero la UX no debe girar alrededor de múltiples búsquedas por cliente.
- **Oportunidad:** necesidad concreta de vivienda. Una oportunidad puede incluir **varios barrios** como alternativas. Cliente y oportunidad son registros distintos.
- **Búsqueda de origen:** URL específica de un portal que Mónica decide añadir para ampliar la cobertura de inmuebles; no equivale a los filtros de la oportunidad. Inicialmente solo Metrocuadrado.
- **Inmueble:** anuncio capturado, con identidad estable, fuente, disponibilidad observada, datos y trazabilidad.
- **Coincidencia:** inmueble evaluado en relación con una oportunidad. Puede cumplir según datos o requerir verificación por información relevante faltante.
- **Decisión de Mónica:** una coincidencia está pendiente de revisión, preseleccionada o descartada. Preseleccionar **no envía** el anuncio al cliente.

El acceso al catálogo completo es secundario a la ficha del cliente y sus coincidencias.

## 3. Reglas de matching aprobadas

**Estricto mediante código:** operación (compra/arriendo), tipo de inmueble, presupuesto y barrios/ciudad solicitados, más rango de habitaciones indicado. Los barrios de la misma oportunidad se combinan como alternativas. Mónica amplía la cobertura ingresando nuevas URL y cambia las preferencias editando la oportunidad; el sistema no amplía zonas por su cuenta.

**Rangos:** capturar límites cuando tienen sentido (presupuesto, habitaciones y área); no imponer un valor único si el cliente dio un intervalo. El área puede influir como preferencia flexible. Validar los límites y no inferir valores faltantes.

**Informativo, no criterio obligatorio:** el número de baños debe verse claramente en los resultados y no usarse para excluir inmuebles. Parqueaderos, estudio, antigüedad y otros datos adicionales no deben ser obligatorios por defecto; solo valorar preferencias expresamente declaradas y pertinentes, sin llenar el formulario de controles de obligatorio/flexible por campo.

**Desconocidos:** si falta evidencia de un requisito relevante, conservar como **pendiente de verificar**, sin declarar cumplimiento. Si existe incumplimiento estricto comprobado, excluir. No generar alertas sobre información que no afecta la oportunidad, ni permitir que Gemini invente características.

**Motor:** aplicar primero reglas verificables del matching existente; usar **Gemini Flash** sobre candidatos pertinentes para enriquecer explicación/ordenación de preferencias, no para relajar presupuestos o barrios ni reemplazar reglas estrictas. Evitar llamadas repetidas innecesarias.

**Disparadores:** matching al confirmar una oportunidad y ante nuevos inmuebles incorporados al catálogo, con recálculo manual disponible. Persistir las decisiones de preselección/descarte por oportunidad e inmueble y respetarlas tras nuevas ejecuciones. Una coincidencia pendiente es distinta de una publicación marcada para revisión técnica conservadora por el scraper.

## 4. UX objetivo de v0.6

**Dashboard de entrada = fotografía breve de actividad**, no una página donde se hace todo. Seguir principios de jerarquía, accesibilidad, estados vacíos, claridad y densidad visual de IBM Carbon Design System como referencia, **sin instalar otro framework**.

Secciones principales:

1. **Clientes y oportunidades recientes:** cliente como protagonista; actividad y coincidencias recientes. Acceso a lista completa de clientes con vistas Activos e Inactivos.
2. **Estado del catálogo:** total, última actualización exitosa, nuevos, actualizados y ausentes, con definiciones y contadores reales del código. Enlace al catálogo detallado existente.
3. **Agregar fuente:** ingreso sencillo de URL de Metrocuadrado, control de duplicados, estado y explicación clara de cuándo se ejecutará. No confundir registrar URL con hacer scraping completo si no existe una tarea configurada.
4. **Nuevo cliente:** acceso directo al formulario de necesidades, confirmación y navegación a **página propia del cliente y sus coincidencias**.
5. **Actividad reciente:** registro compacto de eventos útiles y errores que necesiten atención, sin dashboard técnico sobredimensionado.

**Página cliente/oportunidad:** datos editables, necesidades, resultados de matching con características visibles, motivos y faltantes relevantes, publicación original y decisiones persistentes «Pendiente», «Preseleccionado» o «Descartado». El dashboard solo muestra un resumen y enlaces a esta vista.

**Clientes inactivos:** conservar registros e historial; no ejecutar matching automático de oportunidades cerradas. El mecanismo exacto de cambio de estado debe aprovechar lo ya implementado y ser sencillo para Mónica.

## 5. Arquitectura: decisiones y restricciones

- Scraper **propio con Playwright**, no Apify. Una fuente al inicio, múltiples URLs.
- Reutilizar **Python, FastAPI, Jinja2, JavaScript nativo, módulos `scraper/`, `catalogo/`, `consola/` y `oportunidades/`**. Evitar reescrituras.
- **SQLite para desarrollo** y preservación de bases actuales. **Google Sheets como almacenamiento persistente objetivo en producción**, sin migración integral anticipada durante la v0.6 y sin introducir Firestore por defecto.
- El módulo de oportunidades ya tiene un protocolo de persistencia con adaptador SQLite; estudiarlo antes de agregar otro. Conservar IDs estables y relaciones explícitas para una migración futura a Sheets, sin depender de números de fila.
- **Cloud Run** es destino de despliegue futuro. No usar el sistema de archivos efímero de Cloud Run como almacenamiento definitivo.
- **Gemini Flash** para componentes justificados de matching e interpretación.
- **WhatsApp queda fuera de v0.6**; entrada manual.
- Seguridad de credenciales, datos personales, respaldos y bajo costo son requisitos prácticos. No introducir infraestructura nueva sin evidencia de necesidad.

## 6. Estado comprobado al cierre de v0.5

La rama histórica `v0.4` contiene el commit de hito `291ce82b` del 3 de noviembre de 2026, que declara la **Consola v0.5 cerrada**. Según documentación y descripción del commit:

- Scraper incremental de Metrocuadrado con detección de anuncios nuevos, cambios de precio, revisión conservadora, ausencias por búsqueda e historial.
- Catálogo y consola con filtros «Todos», «Nuevos», «Cambio de precio» y «Revisión conservadora», contadores reales, fechas y nombres de búsquedas persistentes.
- Clientes y oportunidades **ya implementados** con formulario, edición, almacenamiento SQLite separado y un **matching determinista por reglas**. **No reconstruirlos**.
- Interfaz anterior v0.3 en `/consola/`; otra vista en `/v0.4/`. Mantener compatibilidad mientras se crea la nueva portada.
- Comentarios por inmueble son globales al inmueble; **no equivalen a preselecciones y descartes por cliente**.
- Los matches previos se recalculan al consultar; no suponer historial persistente, matching automático tras scraping ni integración ya hecha con Gemini.
- El commit de cierre reporta **513 pruebas aprobadas** (193 consola, 230 catálogo, 90 scraper). Es evidencia declarada en ese commit; para cambios nuevos, Codex debe ejecutar las pruebas correspondientes y reportar lo que ejecutó realmente.
- La descripción de algunas guías todavía usa números de versión anteriores: leer código y commits más recientes, no tomar un README antiguo como estado final del producto.

**Prueba reciente reportada por el usuario:** una recarga detectó 12 inmuebles nuevos y 5 cambios de precio. Son resultados de una ejecución, no métricas fijas del dashboard.

## 7. Alcance de la próxima implementación v0.6

**Desarrollar evolucionando lo existente:**
- Dashboard como portada de actividad.
- Flujo de clientes activos/inactivos, ficha de cliente y coincidencias en página separada.
- Ajustar formulario a rangos y campos informativos definidos; mantener compatibilidad de registros.
- Persistir decisiones de revisión, preselección y descarte por oportunidad/inmueble.
- Ejecutar matching al confirmar y tras incorporación de nuevos inmuebles, sin duplicar trabajo.
- Integrar Gemini en la capa apropiada, con costo controlado y explicación legible.
- Registrar nuevas URL de Metrocuadrado mediante un flujo simple, sin cambiar la semántica del scraper.
- Mantener catálogo actual como vista secundaria, sin perder filtros, trazabilidad ni exportación.

**No implementar por defecto:** WhatsApp, Firestore, migración integral a Sheets, otros portales, envíos automáticos al cliente, cambio de stack frontend, plataforma CRM comercial, despliegue productivo integral.

**Pendiente de concretar por criterio de producto o revisión de código:** esquema y actualización de decisiones persistentes, semántica de ejecución después de añadir URL, límite de llamadas a Gemini, cambio de estado del cliente y manejo de concurrencia. Usar la opción mínima coherente con las decisiones aprobadas; solo elevar conflictos sustanciales.

## 8. Proceso de desarrollo y control de versiones

- `main`: referencia estable, sincronizada con el cierre de v0.5 y documentación rectora. **No desarrollar v0.6 directamente aquí**.
- `release/v0.5`: fotografía inmóvil del commit de cierre.
- `v0.6`: rama de desarrollo de la próxima UX y matching, creada desde `main`.
- `v0.4` y `feat/consola-v0.3`: ramas históricas, conservadas sin reescritura.

Antes de cambiar código, Codex comprueba rama, commit, archivos relevantes, datos y tests. Informa qué **ya existe**, qué **hay que ajustar** y qué **es nuevo**. Cambios pequeños, aditivos y con pruebas; no modificar scraper o esquemas reales en trabajos de UX sin necesidad comprobada. Mantener IDs, historial, APIs y decisiones de Mónica. Registrar commits descriptivos en `v0.6`; integrar en `main` solo una vez validado y autorizado.

**Regla de documentación:** mantener este documento como fuente de decisiones de producto; los README de cada componente sirven para detalles de implementación. Actualizar este documento solo por decisiones aprobadas o hitos verificados. No confundir el nombre de una rama con la versión funcional.

## 9. Referencias técnicas

- `scraper/README.md` y `scraper/docs/INCREMENTAL.md`: captura, actualización y ausencias.
- `catalogo/README.md`: identidad, estados, servicio y filtros comunes.
- `oportunidades/README.md`: clientes, oportunidades, motor de matching por reglas y persistencia.
- `consola/README.md` y `consola/docs/V04.md`: interfaces y conservación de funciones.
- Hito v0.5: https://github.com/alejandrocortesco-source/radar-inmobiliario/commit/291ce82b6ee83884d5501630b5da9d5e47dd8c61
