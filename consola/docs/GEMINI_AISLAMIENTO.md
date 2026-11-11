# VALIDACIÓN REAL CON GEMINI — aislamiento y cierre del HTTP 400

11 de noviembre de 2026. Checkout `develop`, HEAD `91802de`; cambios locales anteriores conservados. Sin commit, push, despliegue ni modificaciones de facturación.

## Resultado demostrado

El adaptador real completó el recorrido con una respuesta auténtica HTTP 200 y dos evaluaciones válidas. El rechazo anterior se aisló en la declaración del esquema completo enviado: con los mismos datos, instrucciones, modelo, límite de salida y LOW, JSON sin esquema funciona y JSON con un esquema estructural inline también funciona. No se aisló cuál de las referencias, metadatos o restricciones del esquema completo ocasionaba el 400; no se atribuye a un único keyword. El cambio anterior a `responseFormat.text` no había resuelto el bloqueo y no se conserva como mecanismo operativo.

Se comprobó acceso al modelo y funcionamiento del transporte antes de modificar el adaptador: GET de metadatos y petición mínima funcionaron con la misma credencial y endpoint. Esto descarta un fallo general de acceso o autenticación en esas pruebas, sin certificar el comportamiento futuro del proveedor.

## Metadatos y transporte

Consulta oficial `GET https://generativelanguage.googleapis.com/v1beta/models/gemini-3.8-flash`: HTTP 200. Resultado saneado:

```json
{
  "name": "models/gemini-3.8-flash",
  "version": "3.0",
  "inputTokenLimit": 1048576,
  "outputTokenLimit": 65536,
  "supportedGenerationMethods": [
    "generateContent", "countTokens", "createCachedContent", "batchGenerateContent"
  ],
  "thinking": true
}
```

`metadata.version` es distinto del campo `modelVersion` de las respuestas de generación: estas reportaron `gemini-3.8-flash`.

Se inspeccionó `httpx 0.28.1`: `trust_env=True`, `follow_redirects=False`, transporte HTTPTransport y cero montajes no nulos. HTTP_PROXY, HTTPS_PROXY, ALL_PROXY y NO_PROXY estaban ausentes; solo se registraron booleanos, nunca valores sensibles. No hubo reintentos automáticos. Las consultas de metadatos no se contabilizan como generaciones.

Fuentes oficiales: [metadatos de modelos](https://ai.google.dev/api/models) y [REST generateContent v1beta](https://aistudio.google.com/api-reference/generate-content/generate-content). La petición mínima se basó en el patrón `contents[].parts[].text` sin opciones. La documentación por sí sola no garantizaba que el esquema completo fuera aceptado; la compatibilidad de la variante implementada quedó comprobada mediante las solicitudes 3 y 4.

## Contador compartido y solicitudes reales

Se autorizaron hasta cuatro generaciones para esta fase. Se realizaron **exactamente cuatro**, secuencialmente; se reservó la cuarta para el validador completo. Antes de cada POST se incrementó el contador persistido en `.tmp/gemini-aislamiento-20261111/registro.json`. La envoltura de la última ejecución interceptó el envío de httpx y bloqueaba una quinta generación. Ni los transportes simulados ni las consultas locales a SQLite agregaron llamadas reales.

Todas usaron `POST /v1beta/models/gemini-3.8-flash:generateContent` y la misma credencial, que no se mostró ni se guardó en el registro.

| Nº | Diferencia deliberada y conclusión | HTTP | Entrada | Salida | Razonamiento | Total reportado |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Solo `contents` con «Responde únicamente OK», sin opciones. Respondió `OK`: el mínimo funciona. | 200 | 4 | 1 | 110 | 115 |
| 2 | Entrada sintética completa de Radar, instrucciones originales, LOW, 12000 tokens, `responseMimeType=application/json`, sin esquema. Funciona el resto de la solicitud; devolvió un array, que no se presentó como evaluación validada de Radar. | 200 | 660 | 253 | No reportado | 913 |
| 3 | Misma petición 2, añadiendo únicamente `responseJsonSchema` estructural inline. Devuelve objeto con `evaluaciones`: esquema simplificado aceptado. | 200 | 660 | 258 | No reportado | 918 |
| 4 | Adaptador real integrado y validador existente con exactamente la configuración e entrada de 3; verificación local antes del envío. Recorrido completo aprobado. | 200 | 660 | 289 | No reportado | 949 |

Total observado: **2895 tokens**, usando `totalTokenCount` sin volver a sumar razonamiento ni componentes. La ausencia de un contador particular significa no reportado, no cero. No se estimaron precios ni costos y no se garantiza el objetivo mensual de US$10 de toda la solución.

## Corrección mínima

`oportunidades/gemini.py` envía ahora:

```python
generacion = {
    'maxOutputTokens': 12000,
    'responseMimeType': 'application/json',
    'responseJsonSchema': esquema_proveedor()
}
# Se conserva thinkingConfig.thinkingLevel = LOW para Gemini 3.
```

`esquema_proveedor()` deriva del mismo contrato Pydantic fijo, resuelve `$ref` locales e incluye solamente `type`, `properties`, `required` e `items`. Omite del esquema enviado `$defs`, `title`, `additionalProperties` y restricciones numéricas/de longitud/de cantidad. No modifica `Respuesta`, `Evaluacion` ni `Evidencia`: Pydantic sigue rechazando campos extra, puntuaciones fuera de 0–100 o no enteras, explicaciones inválidas y cantidades excesivas. Después se siguen comprobando IDs exactos, ausencia de duplicados, evidencias no vacías y hechos sustentados. Una respuesta inválida no entra en caché ni aparece como éxito.

No se cambiaron el endpoint/modelo, candidatos, instrucciones, COP, pendientes, agrupaciones, decisiones, selección ni disparadores manuales. La versión de instrucciones no cambia porque su contenido no cambió. La comparación del cuerpo sin formato conserva la huella `1c8c28bb4110aebdf44dd2efbefec92bf81ed3a759a5dc2a0befda7f65262213`. Las solicitudes 2 y 3 compartieron la huella de entrada `71498376c2bc9346676050626de52da33c2172c2653012c9c0cb0bcd2ac5f704`.

## Validación final auténtica

Ejecutada con `consola/tools/validar_gemini_real.py --ejecutar`, mediante una envoltura local que aplica el contador compartido. Bases nuevas en `.tmp/gemini-real-ec4554f1-6d76-4f6c-b4e8-15b41615424a/`; sin datos operativos, scrapers ni contactos.

- HTTP 200, resultado `correcto`; versión `gemini-3.8-flash`.
- UUID local de ejecución: `8fd12c23-c417-4bbb-99f9-f0c5fb6c16f3`.
- `responseId` del proveedor: `8Wf0arabO8DHxdIP6rShsQw`.
- Los IDs sintéticos `c141287b-4337-59cb-a463-933c09278c64` y `5de4ba0a-4640-5975-bc90-8a21b13ca8f8` recibieron evaluaciones estructuradas válidas con evidencias verificadas por el adaptador.
- Dos evaluaciones persistidas y presentadas por FastAPI/Jinja; requisito de habitaciones desconocido continúa «Pendiente de verificar».
- El anuncio `10c47894-e317-5019-ac7e-29ab4a55a477`, con precio 500000001 COP para máximo 500000000, no se envió ni se mostró entre candidatos.
- La decisión «preseleccionado» permanece intacta.
- Repetir matching y evaluación con datos intactos reutilizó dos evaluaciones: cero nuevas solicitudes al proveedor, comprobado también por el contador global.
- `respuesta_validada=true`, `validacion_real=true`, `presentacion_verificada=true`.

Evidencia saneada en `evidencia.json`, auditoría y caché en `crm.sqlite`, presentación en `ficha.html` dentro de esa carpeta local. La validación de presentación auténtica verifica el HTML de la app; Chromium se ejecutó sobre los escenarios sintéticos de regresión.

## Pruebas nuevas y archivos

Antes de la cuarta generación: 58 pruebas pertinentes de consola (35,04 s, incluido Chromium), 247 de catálogo (8,89 s), 121 de scraper (65,86 s). Además, 14 casos de diagnóstico (0,90 s) comprobaron explícitamente las restricciones locales: nueve repiten casos de las 58 y cinco son adicionales. Son **431 casos únicos**, no una nueva ejecución de toda la consola. Se mantiene una advertencia de deprecación de BlockingPortal en Starlette/AnyIO, sin fallos.

Cambios de esta fase: `oportunidades/gemini.py`, `consola/tests/test_gemini_diagnostico.py`, `consola/tests/test_v06.py` y documentación (`GEMINI_AISLAMIENTO.md`, `GEMINI_HTTP400.md`, `GEMINI_MANUAL.md`, rector). Los scripts de contador y diagnóstico permanecen locales en `.tmp/gemini-aislamiento-20261111/`, sin credenciales. No se reconstruyeron módulos ni se alteraron bases operativas.

El bloqueo funcional está resuelto para el recorrido probado. Queda sin determinar el keyword individual del esquema completo que ocasionaba el rechazo; no se gastaron más generaciones para averiguarlo. No quedan llamadas de esta autorización disponibles. El consumo mensual y el funcionamiento con otros modelos/escenarios no quedan acreditados por esta prueba.
