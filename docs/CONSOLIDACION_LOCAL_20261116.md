# Consolidación y cierre v0.14.1 — 16 noviembre 2026

La carpeta principal es `C:\Users\Palex25\Documents\Boch-Lab\Radar-CloudRun-20261111\repo`, rama `codex/ejecuciones-manuales`. Se conserva su ubicación para mantener el entorno activo, los scripts y las credenciales externas. El directorio padre no es un repositorio Git. La entrega funcional sigue siendo v0.14.1, commit `845912ee304938b584b4792296ad0fb257b78be1`; este cierre solo añade documentación, sin reconstrucción de imágenes.

## Producción verificada

- URL canónica con IAP: <https://radar-56106530298.us-central1.run.app/v0.6/ejecuciones/programaciones>.
- Web: 100 % en `radar-v0141-public-845912e`. La revisión privada `radar-v0141-private-845912e` conserva el tag `ejecuciones-review`, sin tráfico general. Las revisiones anteriores se conservan.
- Disparador interno: 100 % en `radar-schedule-review-v0141-845912e`; IAM, ingress y configuración conservados.
- Las revisiones web/disparador usan `web@sha256:9ac655848c350bf266aaca291d7b0ef0e054a9ba8c389abb08a4232d18a2cf59`. Job: `jobs@sha256:bcf9094a589781c3bb583b7b4c8def9f5792846056e625ecdc44e793751e651e`.
- Control GCS migrado mediante la operación explícita CAS de v0.14.1 a formato 2. Scheduler `radar-weekly-review` PAUSED, gate deshabilitado y programación general pausada. Se conservan lunes 09:00 Bogotá y las tres búsquedas originales. Cero trabajadores activos; no se ejecutaron Jobs ni scraping.
- Una escritura con generación anterior fue rechazada por GCS con 412. El lector real 0.13.1 rechaza formato 2; una escritura que hubiera leído formato 1 también queda detenida por CAS. Los accesos enrutados web/disparador y la imagen del trabajador corresponden a código compatible; ningún tag continúa apuntando a un editor antiguo.
- Historial, búsquedas y recibos comparados por igualdad; snapshot con generación `1794845033755129`, tamaño y hashes conservados. Salud y lectura autenticada de la versión 0.14.1 verificadas en navegador mediante IAP, sin acciones de negocio.

Las evidencias privadas están en `.tmp/preflight-0141-20261116/closure/`. El procedimiento de reversión sigue en [RELEASE_014.md](../deployment/RELEASE_014.md): pausar, confirmar cero trabajadores y usar `rollback_legacy` con la revisión actual para volver a formato 1 antes de restaurar escritores antiguos. Nunca copiar control/snapshot antiguos completos. Scheduler permanece pausado también tras rollback.

## Respaldo y trabajo conservado

`C:\Users\Palex25\Documents\Boch-Lab\Radar Inmobiliario` queda como respaldo histórico, identificado por `RESPALDO_NO_USAR_COMO_PROYECTO.md`. Windows mantiene abierta esa carpeta y rechazó su traslado antes de mover archivos; se conserva en su ubicación original sin forzar cierres ni eliminarla. El proyecto correspondiente de Codex se separó en la sección `Radar · respaldo e historial`.

La auditoría encontró ambos árboles versionados limpios y el mismo remoto `https://github.com/alejandrocortesco-source/radar-inmobiliario.git`. El respaldo está en `develop`, commit `d84f1dda914b5a211b0e00eef61de1c5b28a2b88`. Tras fetch, esa rama queda cuatro commits detrás de `origin/develop`, sin commits locales exclusivos respecto de esa rama remota. No se actualizó su árbol histórico.

Todas sus ramas y tags, incluidos los históricos solo locales, tienen referencias de archivo bajo `refs/archive/20261116-secondary/` en la principal. Sus dos worktrees existentes permanecen intactos; sus HEAD se preservaron además bajo `refs/archive/20261116-secondary/worktrees/0b1b` y `0c29`. Los commits de las ramas y de esos HEAD ya están contenidos en la historia de la entrega principal; se conservaron sus nombres y referencias sin integraciones. Los bundles completos verificados preservan además las referencias internas y checkpoints existentes, sin editar bases internas de Codex.

Auditoría privada: `.tmp/consolidacion-20261116/`, con remotos, ramas, referencias, estado, parches, inventarios de archivos con SHA-256, comparación con GitHub y bundles completos de ambos repositorios. El inventario de la principal registró 35.680 archivos y el de la secundaria 41.744, excluyendo entornos instalados y cachés; estos últimos también permanecen en sus ubicaciones originales.

Además se copiaron 87 archivos locales relevantes, 262.236.049 bytes, a `.local/consolidacion-20261116/`, verificando sus hashes contra el inventario. Incluyen los datos locales ignorados y el diagnóstico sin seguimiento de un worktree. No se activaron como datos operativos ni se sobrescribieron archivos. Los temporales, evidencias y el resto de archivos originales siguen en el respaldo; las credenciales cloud continúan en `..\credentials`, fuera del repositorio. Los artefactos exactos de despliegue siguen en `.local/releases/v0.14.1/`.

## GitHub y Codex

Se hizo fetch real en ambas copias. Antes del commit documental, `codex/ejecuciones-manuales` y su referencia remota coinciden en `845912e`; el tag anotado `v0.14.1` coincide localmente y en GitHub, tanto en objeto tag como en commit resuelto. Esta organización publica solo el commit documental en `codex/ejecuciones-manuales`, sin mover tags, publicar referencias de archivo, integrar ramas ni modificar `main` o `develop`.

Los conectores de Codex permiten separar proyectos en la barra lateral, pero no renombrar un proyecto local ni cambiar su carpeta vinculada. La revisión automática rechazó mover una conversación al proyecto todavía llamado `Radar-CloudRun-20261111`, por no coincidir con el proyecto operativo solicitado. No se repitió la operación ni se alteraron conversaciones o bases internas.

Paso de interfaz pendiente: crear o seleccionar una entrada de proyecto llamada **Radar Inmobiliario** que apunte exactamente a la carpeta principal indicada, mover allí las conversaciones de Radar que se quieran mantener agrupadas y retirar las entradas operativas antiguas de la barra lateral conservando los chats. No clonar ni crear una nueva carpeta del filesystem; seleccionar la carpeta existente. Mantener las conversaciones históricas accesibles y el respaldo fuera del uso diario. Hasta completar ese cambio, la entrada operativa actual sigue llamándose `Radar-CloudRun-20261111`; no se declara terminada la unificación de nombres de Codex.
