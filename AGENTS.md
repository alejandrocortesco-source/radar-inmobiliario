# Radar Inmobiliario

**Primera lectura:** `RADAR_PROYECTO_RECTOR.md` contiene las decisiones vigentes. Los README de los módulos documentan el código real; contrastar diferencias antes de asumir.

## Alcance y conservación

- Herramienta privada para Mónica, unos 30 clientes activos y presupuesto operativo objetivo inferior a 10 USD/mes, sujeto a medición. Priorizar simplicidad, mantenimiento y reutilización.

- La especificación vigente está en `RADAR_PROYECTO_RECTOR.md`. v0.6 se desarrolla en `v0.6`; no hacer merge a main ni push sin solicitud.
- Reutilizar scraper, catálogo, identidades, historial, clientes, oportunidades y matching determinista. No reconstruirlos para un cambio visual.
- FastAPI, Jinja2, CSS y JavaScript nativo. Sin React, Carbon instalado, Firestore ni infraestructura adicional.
- El dashboard tiene **exactamente cuatro secciones**: oportunidades recientes, estado del catálogo, agregar fuente y nuevo cliente. La actividad pertenece a las dos primeras; no existe una quinta sección.
- El catálogo es de solo lectura desde la consola. Guardar nombres, fuentes, comentarios, clientes, decisiones y caché en la base auxiliar; nunca escribir esos datos en SQLite del scraper.
- Clientes y oportunidades son entidades distintas. Las oportunidades cerradas y clientes inactivos no participan en matching automático. Conservar relaciones e historial.
- Operación, tipo, ubicación, presupuesto y límites de habitaciones son estrictos. Desconocido significa pendiente de verificar; baños, área y otras características son preferencias.
- La única moneda del sistema es COP, ahora y a futuro. Comparar directamente precios numéricos y presupuesto con límites inclusivos, sin solicitar ni verificar moneda, ni convertir importes. El campo histórico `moneda` no filtra, ordena ni condiciona el matching. Precio ausente o inválido sigue desconocido; no sustituirlo por cero.
- Gemini solo evalúa candidatos seleccionados por código. No inventar resultados ni presentar IA disponible si falta configuración o falla. No enviar nombre ni teléfono del cliente al proveedor.
- Las decisiones comerciales (pendiente/preseleccionado/descartado) son independientes de los resultados y de la revisión conservadora técnica del scraper.

## Validación

- Usar exclusivamente bases sintéticas en `.tmp/` o `tmp_path`. No modificar datos reales ni ejecutar extracciones reales como prueba.
- Ejecutar pruebas de consola, catálogo y scraper; incluir Chromium cuando cambien flujos o presentación. Ver `consola/docs/V06.md` para comandos y límites.
- En Windows el sandbox puede bloquear el socket local de asyncio/TestClient y Chromium. Una ejecución fuera del sandbox conserva las mismas bases de prueba.
- Verificar desktop, tablet y móvil, foco, labels, errores, estados vacíos y ausencia de desbordamiento de página. Las tablas anchas tienen desplazamiento en su propio contenedor.
- Mantener presentación en `consola/`, reglas en `oportunidades/` y `catalogo/`, persistencia detrás de adaptadores sustituibles.

## Fuera de alcance

WhatsApp, comunicaciones automáticas, otros portales, CRM empresarial, migración integral a Sheets y despliegue a producción. Sheets y Cloud Run son objetivos futuros.

## Disciplina Git e informes

- Antes de modificar, verificar `git status`, `git branch --show-current` y `git log -1`; el nombre de una rama no demuestra su estado funcional.
- `main` es la referencia estable, `release/v0.5` conserva el cierre `291ce82` y `v0.4` y `feat/consola-v0.3` son históricas. No reescribirlas ni publicar en ellas sin autorización explícita.
- Hacer cambios pequeños y compatibles; no reconstruir módulos que funcionan. No desplegar ni efectuar operaciones destructivas sin autorización.
- Informar archivos modificados, conflictos, pruebas realmente ejecutadas, commit y pendientes. No presentar resultados de commits anteriores como pruebas nuevas.
