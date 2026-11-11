# Diagnóstico de HTTP 400 — 11 de noviembre de 2026

> Cierre posterior: el aislamiento controlado y la validación final auténtica resolvieron el bloqueo usando un esquema estructural inline con validación local completa. Ver [pruebas, contador y consumo](GEMINI_AISLAMIENTO.md). El contenido siguiente es histórico.

> Actualización posterior: se agotó la única solicitud pendiente probando exclusivamente `generationConfig.responseFormat.text`, respaldado por la referencia REST de v1beta. También devolvió HTTP 400 genérico. Ver el último apartado; la validación auténtica sigue bloqueada. Los apartados anteriores conservan su alcance histórico.

## Estado: validación real bloqueada

No se ha identificado una causa raíz de parámetros con evidencia suficiente. Se corrigió la pérdida de diagnóstico HTTP y se reforzó el validador; no se declara corregido el rechazo del proveedor ni completado el recorrido auténtico. El modelo y los parámetros de generación se conservaron, sin tantear combinaciones ni eliminar validaciones.

La evidencia histórica `.tmp/gemini-real-23ca1bf2-cf81-47cd-b37b-9ac2a9a84067/evidencia.json` solo acreditaba HTTP 400, modelo solicitado y ausencia de evaluaciones/métricas. HTTP 400 por sí solo no identifica un parámetro incorrecto. El intento anterior HTTP 402 es otro resultado histórico, no prueba de la causa del 400.

## Solicitud efectiva inspeccionada, sin generación preliminar

| Elemento | Valor comprobado |
| --- | --- |
| Método / endpoint | POST `https://generativelanguage.googleapis.com/v1beta/models/gemini-3.8-flash:generateContent` |
| Modelo efectivo | `gemini-3.8-flash`, valor predeterminado; `GEMINI_MODEL` no estaba definido |
| Autenticación | `x-goog-api-key` desde entorno, sin mostrar ni registrar su valor |
| Tipo de cuerpo | `application/json`, serializado por `httpx` |
| Contenido | `systemInstruction.parts[].text` y `contents[].parts[].text` con necesidades estructuradas y hechos de candidatos; sin identidad/contactos ni textos libres |
| Configuración | `generationConfig.maxOutputTokens=12000`, `responseMimeType=application/json`, `responseJsonSchema=Respuesta.model_json_schema()`, `thinkingConfig.thinkingLevel=LOW` |
| Límites de la prueba | El validador fija `GEMINI_MAX_CANDIDATES=2`; una sola generación, sin scraper ni reintentos |
| Almacenamiento | Nueva carpeta UUID bajo `.tmp/`; todas las rutas operativas se sustituyen antes de crear los servicios |

No hay `temperature`, `topP`, `topK`, `candidateCount`, herramientas ni parámetros de búsqueda. El esquema generado tiene objetos con `required` y `additionalProperties=false`, definiciones `$defs`/referencias locales `$ref`, puntuación entera de 0 a 100, explicación de 1 a 800 caracteres, máximo 12 evidencias y 30 evaluaciones. Las validaciones Pydantic, IDs exactos y evidencias contra hechos se mantienen en el cliente.

## Contraste oficial e hipótesis

Fuentes oficiales consultadas el 11 de noviembre de 2026:

- [Ficha del modelo](https://ai.google.dev/gemini-api/docs/models/gemini-3.8-flash): salida de texto, respuestas estructuradas, razonamiento LOW/MEDIUM/HIGH y máximo de salida de 65.536 tokens.
- [Guía de migración de 3.8](https://ai.google.dev/gemini-api/docs/whats-new-gemini-3.8): mantiene referencias al uso de generateContent; no exige sustituir este adaptador por Interactions.
- [Referencia generateContent](https://ai.google.dev/api/generate-content): endpoint, `generationConfig`, configuración de respuesta JSON y enum de razonamiento. También documenta un formato alternativo `responseFormat`; su existencia no demuestra que los campos actuales sean la causa.
- [Esquemas estructurados](https://ai.google.dev/gemini-api/docs/structured-output): subconjunto JSON Schema, referencias, propiedades adicionales, límites numéricos y de arrays. Los límites de longitud de strings se validan localmente, pues la guía indica que no se imponen durante la decodificación. Los ejemplos actuales de esa guía se centran en Interactions; no se asume equivalencia perfecta entre endpoints por compartir modelo.

12000 está bajo el máximo publicado; LOW está documentado para el modelo. El contraste no ofrece una incompatibilidad concreta demostrada de nuestro esquema/endpoint. Que una opción aparezca documentada tampoco acredita que esta cuenta y petición específica hayan sido aceptadas. No se cambió de modelo, no se quitaron referencias/restricciones y no se migró de API sin causa comprobada.

## Cambios de esta tarea

- `oportunidades/gemini.py`: extracción acotada de `error.code`, `error.status`, mensaje, `fieldViolations` y motivos/parametros permitidos de ErrorInfo; IDs de respuesta disponibles; consumo explícito `no_reportado` si faltan métricas. Mensaje comprensible para HTTP 400 y conservación del resultado determinista.
- El saneamiento omite claves conocidas, valores de entrada enviados, emails, teléfonos, URLs, caracteres de control y ecos JSON. Limita mensajes, número de detalles y tamaño del cuerpo procesado. No persiste cuerpos crudos, encabezados completos, prompts ni metadata arbitraria. Un error no JSON o demasiado grande deja una explicación fija.
- `consola/tools/validar_gemini_real.py`: verifica también una decisión comercial preseleccionada. `respuesta_validada` y `validacion_real` son distintas: solo al completar presentación, persistencia, caché y requisitos se marca validación completa. Un HTTP 200 no basta.
- `consola/tests/test_gemini_diagnostico.py`: casos simulados de construcción, saneamiento, errores incompletos/no JSON/grandes, preservación del matching, ausencia de evaluaciones falsas y una única solicitud.

El adaptador no confunde el estado de tarea terminada (`listo`) con éxito: `resultado=proveedor`, aviso de rechazo y evaluaciones ausentes representan el fallo. No hay reintentos ni llamadas automáticas nuevas.

## Solicitudes reales adicionales de esta tarea

**Exactamente 1 de las 2 permitidas**. Se ejecutó individualmente después de pruebas simuladas. No se usó la segunda: no existe una causa concreta obtenida de la primera que permita autorizar una corrección y otra generación. Tampoco hubo consultas preliminares de generación.

| Dato | Resultado |
| --- | --- |
| Ejecución | `785baaef-9e5b-43ea-affe-9cd950e726ee` |
| Fecha | 11/11/2026, 07:35:12 America/Bogota (12:35:12 UTC) |
| HTTP / error | `400`, `error.code=400`, `INVALID_ARGUMENT` |
| Mensaje saneado capturado | `Request contains an invalid argument.` |
| Candidatos enviados | 2 sintéticos; el tercero que supera presupuesto quedó excluido |
| Requisito desconocido | Habitaciones sin dato permanece pendiente en matching |
| Decisiones comerciales | Lectura posterior de SQLite confirma una preselección conservada |
| Duración | 2594 ms |
| Modelo solicitado | `gemini-3.8-flash` |
| Versión devuelta / tokens | No reportados; consumo desconocido, sin inferir cero tokens ni cero costo |
| Evaluaciones / caché real | Ninguna evaluación válida; repetición con caché auténtica pendiente |
| Presentación auténtica | Pendiente; no se fingieron explicaciones |

Evidencia local saneada: `.tmp/gemini-real-908b6ee9-9fb7-4817-bea7-36f0f194673b/evidencia.json`. La auditoría y el matching están en el `crm.sqlite` sintético contiguo. La evidencia capturada no contiene un parámetro rechazado. No se guardó el cuerpo crudo y no se puede reconstruir información que no quedó capturada. La extracción permitida se amplió después también a motivos ErrorInfo para futuros diagnósticos, sin realizar otra llamada.

Para continuar hace falta evidencia específica del proveedor sobre el argumento rechazado (por ejemplo, un diagnóstico vinculado a esa solicitud obtenido por el usuario), o una nueva autorización para una estrategia de diagnóstico explícita y sustentada. No se activó facturación ni se realizaron pagos. La credencial permanece oculta. No hubo commit, push ni despliegue; se conservaron los cambios locales previos en `develop`, HEAD `91802de`.

## Pruebas de esta tarea

Antes de contactar al proveedor pasaron los 49 casos de matching/Gemini/v0.6 y los 8 casos nuevos de diagnóstico, en ejecuciones dirigidas. La primera pasada tuvo un error de infraestructura de pruebas: pytest derivó un nombre de archivo demasiado largo del caso de cuerpo grande; se corrigió con identificadores cortos y los ocho casos pasaron. No fue un fallo del adaptador ni una llamada a Google.

Regresión final ejecutada en procesos separados, fuera del sandbox para permitir sockets locales/Chromium y usando exclusivamente bases sintéticas:

| Suite / comprobación | Resultado nuevo |
| --- | --- |
| Consola, incluido Chromium y diagnóstico HTTP | 330 aprobadas, 208,19 s |
| Catálogo | 247 aprobadas, 8,27 s |
| Scraper sin extracciones reales | 121 aprobadas, 69,12 s |
| Total de las tres suites | **698 aprobadas** |
| Sintaxis Python, enlaces locales y `git diff --check` | Correctos |

Una advertencia de deprecación `BlockingPortal` de Starlette/AnyIO continúa, sin fallos. No se suman de nuevo las repeticiones dirigidas al total. Los conteos de la entrega anterior no se presentan como pruebas nuevas. La verificación local de la base del intento real confirma dos resultados deterministas, una preselección, una ejecución y cero evaluaciones en caché: no se fabricaron evaluaciones al fallar.

## Hipótesis aislada: GenerationConfig.responseFormat

La solicitud posterior del usuario autorizó consumir únicamente la generación real que quedaba pendiente, después de inspección y pruebas locales. La [página específica de generateContent](https://aistudio.google.com/api-reference/generate-content/generate-content) define el endpoint `POST /v1beta/models/{model}:generateContent` y, dentro de su `generationConfig`, `responseFormat.text.mimeType` con enum `APPLICATION_JSON` y `responseFormat.text.schema` como objeto JSON Schema. La [ficha de gemini-3.8-flash](https://ai.google.dev/gemini-api/docs/models/gemini-3.8-flash) documenta texto y salida estructurada; su [guía de migración](https://ai.google.dev/gemini-api/docs/whats-new-gemini-3.8) mantiene el uso de generateContent. Esto respalda probar esa declaración en este endpoint/modelo, sin demostrar previamente que la cuenta acepte la combinación exacta.

Se sustituyeron únicamente los campos de formato en el adaptador:

```python
generacion = {'maxOutputTokens': 12000, 'responseFormat': {
    'text': {'mimeType': 'APPLICATION_JSON', 'schema': Respuesta.model_json_schema()}}}
```

Se conservan `thinkingConfig.thinkingLevel=LOW`, modelo, límite de tokens, instrucciones, orden/IDs/hechos de candidatos, esquema íntegro, validaciones, caché y solicitudes exclusivamente manuales. No se cambió la versión de instrucciones porque no cambió su contenido. No se añadió el formato alternativo junto a los campos antiguos: estos se eliminaron.

### Comparación previa sin consumo

Se capturó lo recibido por `httpx.MockTransport` antes y después de modificar el adaptador, con la misma oportunidad y los mismos tres anuncios sintéticos del intento de las 07:35. Solo se almacenaron huellas y configuración saneada, sin encabezados de autenticación ni prompts. Evidencia local: `.tmp/gemini-responseformat-20261111/anterior.json` y `nuevo.json`.

| Comparación | Resultado |
| --- | --- |
| URL/modelo | Idénticos: `v1beta/models/gemini-3.8-flash:generateContent` |
| Esquema JSON completo | Idéntico; SHA-256 `ac83ee44348f5e8c4b669ca0c77935955d3d7715a1fb5c614b7f22a23cb2ddea` |
| Cuerpo completo excluyendo solo declaración del formato | Idéntico; SHA-256 `1c8c28bb4110aebdf44dd2efbefec92bf81ed3a759a5dc2a0befda7f65262213` |
| Parámetros restantes | `maxOutputTokens=12000`, `thinkingLevel=LOW` |
| Candidatos enviados al transporte simulado | 2; el tercero excedido se excluye |
| Solicitudes reales en la comparación | 0 |

El nuevo caso `test_response_format_conserva_solicitud_sintetica_anterior` verifica esas huellas sobre los bytes JSON efectivamente entregados a httpx, el esquema completo y una respuesta simulada con los dos IDs válidos. Las pruebas de formato existentes se adaptaron sin retirar las de puntuación, evidencias, IDs, requisitos pendientes, errores ni caché.

Antes de la única llamada pasaron **426 pruebas nuevas de esta ejecución**: 58 pertinentes de consola (34,88 s, incluido Chromium), 247 de catálogo (8,54 s) y 121 de scraper (68,99 s, sin extracciones reales), con bases sintéticas. No es una nueva pasada completa de los 330 casos de consola. `git diff --check` también pasó. Continúa la advertencia de deprecación de BlockingPortal, sin fallos.

### Resultado de la única solicitud pendiente

| Dato | Resultado |
| --- | --- |
| Fecha | 11/11/2026 07:52:30 America/Bogota; `2026-11-11T12:52:30.572925+00:00` |
| UUID local de ejecución | `616d24d6-aa8f-4d3e-b415-3ebf540b7972` |
| HTTP / error | `400`, `code=400`, `status=INVALID_ARGUMENT` |
| Mensaje saneado completo | `Request contains an invalid argument.` |
| Detalles de parámetros / IDs del proveedor | No quedaron capturados |
| Modelo solicitado | `gemini-3.8-flash`; versión no reportada |
| Candidatos / solicitudes | 2 sintéticos / exactamente 1 generación intentada, sin reintentos |
| Duración | 2141 ms |
| Tokens | `{}`; consumo `no_reportado`, desconocido, sin inferir costo cero |
| Resultado | Fallo del proveedor; `respuesta_validada=false`, `validacion_real=false` |

Evidencia saneada: `.tmp/gemini-real-6e45c7a9-7ea9-462a-bb24-0d96de8a7a87/evidencia.json`. El validador terminó ante el fallo; no intentó obtener otra respuesta ni afirmó reutilización de evaluaciones auténticas inexistentes.

Quedó demostrado localmente que cambió solo la declaración del formato. **No quedó demostrado que Gemini aceptara esa nueva estructura**, porque el 400 genérico no permite saber qué validación rechazó. Tampoco quedó completado el recorrido de respuesta, persistencia, presentación y caché auténticas. La hipótesis no resolvió por sí sola el bloqueo.

No quedan generaciones autorizadas pendientes de la pareja anterior: se usó una en el diagnóstico previo y esta fue la segunda, cada una bajo solicitud explícita distinta. No se hicieron pagos, cambios de facturación, commit, push ni despliegue. En esta fase se modificaron únicamente el formato en `oportunidades/gemini.py`, las comprobaciones en `consola/tests/test_gemini_diagnostico.py` y `test_v06.py`, y la documentación de este informe y `GEMINI_MANUAL.md`; se preservaron los demás cambios locales.
