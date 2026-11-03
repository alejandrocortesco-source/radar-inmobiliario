# Radar Inmobiliario | Instrucciones permanentes para Codex

**Primera lectura:** [RADAR_PROYECTO_RECTOR.md](RADAR_PROYECTO_RECTOR.md). Es la referencia de visión, escala, decisiones de negocio y alcance vigente. Los README de los módulos documentan el código real. Si hay diferencias entre documentación antigua y código, verificar antes de asumir.

## Prioridades

- Herramienta privada para Mónica, unos 30 clientes activos, presupuesto objetivo menor a USD 20/mes. No construir un CRM masivo.
- Proteger la v0.5 ya cerrada y aprovechar el código existente. Ya existen scraper, catálogo, clientes, oportunidades y matching por reglas.
- En v0.6: dashboard de entrada resumido, ficha del cliente y coincidencias en otra página, registro de URL, decisiones de preselección/descarte y Gemini donde aporte.
- Mantener Playwright, FastAPI, Jinja2 y JavaScript nativo; SQLite en desarrollo y Google Sheets como destino previsto de persistencia productiva. No introducir Firestore ni frameworks nuevos sin necesidad demostrada.
- Filtros de requisitos verificables antes de Gemini, barrios y presupuesto estrictos; no inventar características. Baños informativos; campos opcionales no excluyentes por defecto.
- Respetar IDs, procedencia, estados de revisión y ausencias, historial del scraper y decisiones guardadas de Mónica.

## Disciplina Git

- `main` es la base estable; `release/v0.5` guarda el cierre; desarrollar nuevos cambios únicamente en `v0.6` (o ramas de trabajo derivadas de ella).
- Verificar `git status`, `git branch --show-current` y `git log -1` antes de modificar. No asumir versión por nombre de rama.
- No hacer cambios destructivos, merges a `main`, despliegues o pushes fuera de la rama autorizada sin instrucción explícita. No tocar bases reales en pruebas.

## Forma de trabajar

1. Inspeccionar archivos y tests pertinentes, separar «ya existe», «hay que ajustar» y «es nuevo».
2. Elegir el cambio mínimo con pruebas y compatibilidad. No reconstruir módulos que ya funcionan.
3. Avisar si hay conflicto de negocio real, pero no volver a debatir decisiones ya aprobadas en el documento rector.
4. Informar archivos modificados, pruebas ejecutadas, commit y riesgos pendientes. No presentar reportes de commits anteriores como pruebas nuevas.
