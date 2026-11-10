# Git y versionado de Radar Inmobiliario

Política vigente desde el 9 de noviembre de 2026. Un solo desarrollo personal, sin ramas por versión ni automatizaciones adicionales. Las decisiones funcionales siguen en [el documento rector](RADAR_PROYECTO_RECTOR.md).

La ubicación vigente de documentación, datos y archivos privados se consulta en [el mapa de archivos](docs/ESTRUCTURA.md). El diagnóstico privado que la auditoría histórica registra bajo `docs/` se trasladó después a `.local/diagnosticos/`, conservando su contenido y fuera de Git. Este traslado no altera las referencias Git de la auditoría.

## Política operativa

- Todo nuevo desarrollo y commit se realiza en `develop`. Antes de editar, comprobar rama, HEAD, índice y cambios pendientes. Si se está en una rama histórica, detenerse e informar; esta migración autorizada constituye la excepción.
- `v0.6` queda como referencia remota histórica: no desarrollar ni publicar nuevos commits en ella. Se renombra únicamente la rama local a `develop`; se conservan las demás referencias y respaldos.
- `main` mantiene su función prevista de referencia estable y su contenido actual; esta tarea no integra v0.8 allí ni cambia la rama predeterminada. `master` local no equivale automáticamente a `main`.
- El nombre de una rama no demuestra estabilidad, pruebas aprobadas ni disponibilidad en producción.
- Las versiones se identifican con tags anotados `vMAJOR.MINOR.PATCH`, asociados a commits concretos. Un commit documental no incrementa por sí solo la versión funcional. Las rutas heredadas `/v0.6/`, `/v0.4/`, `/consola/` y demás identificadores permanecen; no determinan la versión actual.
- PATCH: correcciones compatibles. MINOR: funciones nuevas compatibles. MAJOR: cambios incompatibles. Durante 0.x, describir expresamente cualquier incompatibilidad y no prometer estabilidad de API.
- Commit local, push, GitHub Release y despliegue son acciones distintas; ninguna acredita las demás. Push, merge y despliegue requieren autorización expresa para su alcance. Esta organización solo autoriza el commit documental y la publicación de `develop` y `v0.8.0`, sin Release ni despliegue.
- No usar `git push --all` ni `git push --tags`; publicar referencias explícitas. No mover tags ya publicados ni reescribir historial. Conservar ramas históricas, tags existentes y respaldos.

## Operación breve

Desde la raíz, revisar antes de editar:

```powershell
git status --short
git diff --cached --stat
git branch --show-current
git log -1 --oneline
git branch -vv
```

Consultar GitHub directamente y actualizar referencias sin integrar ni importar tags:

```powershell
git ls-remote --symref origin
git fetch --no-tags origin
git rev-list --left-right --count origin/develop...develop
git log --oneline --left-right origin/develop...develop
```

El primer número cuenta commits exclusivos remotos; el segundo, locales. `fetch` actualiza referencias de seguimiento; no es merge ni autorización para resolver divergencias. Ante cambios incompatibles, detenerse e informar.

Publicar exclusivamente `develop`, solo con autorización:

```powershell
git push -u origin develop
```

Crear y publicar exclusivamente un tag autorizado, después de verificar que no existe localmente ni en GitHub. Sustituir las dos variables por valores expresamente aprobados; no usar HEAD por suposición:

```powershell
$tagAutorizado = 'vMAJOR.MINOR.PATCH'
$commitAutorizado = 'HASH_COMPLETO_APROBADO'
git show-ref --verify "refs/tags/$tagAutorizado"
git ls-remote origin "refs/tags/$tagAutorizado" "refs/tags/$tagAutorizado^{}"
git tag -a $tagAutorizado $commitAutorizado -m 'Descripción y límites de la entrega autorizada'
git push origin "refs/tags/$tagAutorizado"
```

Para publicar rama y tag juntos cuando ambos estén autorizados, el remoto debe admitir atomicidad; si la rechaza, informar sin forzar ni improvisar otra publicación:

```powershell
git push --atomic -u origin develop refs/tags/v0.8.0
```

Comprobar hashes directamente en GitHub; para un tag anotado comparar la línea `^{}` con el commit, no el objeto tag:

```powershell
git rev-parse develop
git rev-parse 'v0.8.0^{}'
git ls-remote origin refs/heads/develop refs/heads/v0.6 refs/heads/main refs/tags/v0.8.0 'refs/tags/v0.8.0^{}'
```

## Auditoría y transición autorizada

Base inicial comprobada: `4781daeb9adefc310028d40dcec88795657530eb`, `feat(v0.8): integrar Wasi y preparar ejecución en Cloud Run Jobs`. Índice y contenido versionado limpios; únicamente `docs/` sin seguimiento. Se conserva sin leer su contenido, modificarlo ni publicarlo. Las bases, secretos y temporales quedan fuera.

| Referencia inicial | Hash / alcance comprobado |
| --- | --- |
| `v0.6` local y GitHub | `4781daeb9adefc310028d40dcec88795657530eb` |
| `main` en GitHub, predeterminada | `069fc89d4c2562684228fbefa163220066600c39`; antecesora de la entrega, sin rama local `main` |
| `master`, solo local | `06bc626dc8bcdf0dd957884a59ec69b9eb9d4b64` |
| `release/v0.5`, en GitHub | `291ce82b6ee83884d5501630b5da9d5e47dd8c61`; sin rama local homónima |
| `v0.4` local y GitHub | `291ce82b6ee83884d5501630b5da9d5e47dd8c61` |
| `feat/consola-v0.3` local y GitHub | `e912bdcc3eda408b0ceee635900b52fc9799d1e4` |
| Respaldo anterior local `codex/backup-v0.6-pre-sync-20261103` | `4a444f1b0ce2ec3c85f38af68c5a3e7b0b6e410b` |
| Nuevo respaldo exclusivamente local `codex/backup-pre-develop-20261109-190254` | `4781daeb9adefc310028d40dcec88795657530eb` |
| `develop` y `v0.8.0` | Inexistentes localmente y en GitHub antes de esta tarea |

Los tags históricos compartidos conservan estos valores (objeto tag → commit resuelto):

| Tag | Objeto tag | Commit |
| --- | --- | --- |
| `consola-v0.1` | `c35b225bad7198b7d2301f9b5058e4497f8283a3` | `fb495340a22d7b02323dffb7e4fb7b431f1117b6` |
| `v0.1.0` | `2bf6538536eed5d0a61618d63d545c873b790632` | `646bf7be11addc9a852b90b7eff8631c742f38c9` |
| `v0.2.0` | `9853462933d397cef4db3e17e7f1cf5d0661f930` | `a1c87720aba4a8cd9ac3fe13c759726b19d9e010` |
| `v0.3.0` | `d25aeab3614f796221eb3a33b036831c9538bd7b` | `2153bf966fdcf94320b7f607f9a800857b8585d7` |
| `v0.4.0` | `4f2525296df476ba8c181220cf8c6003efc8158c` | `b8dd256f61b7a8206eeb935cf988623f0337151b` |

El tag **local y ligero** `v0.5.0` apunta a `a52159c0387ce13d2990c7cc49a9092b7f0b6ed3` (modelo común de catálogo), distinto del cierre funcional v0.5 `291ce82`. No existe en GitHub al auditar. No se corrige, mueve, convierte ni publica: la numeración histórica no prueba equivalencia funcional.

`v0.8.0` es anotado y apunta exactamente al commit funcional `4781daeb9adefc310028d40dcec88795657530eb`: Wasi y preparación para Cloud Run Jobs. No acredita despliegue ni validación desatendida en Google Cloud. El único commit documental posterior organiza Git sin cambiar esa versión ni incluir su propio hash futuro.

Las coincidencias de `v0.6` se clasificaron así: instrucciones vigentes de rama en AGENTS, rector y README actualizadas a `develop`; informes de V06, V07 y Wasi conservados con aclaraciones; rutas HTTP, módulos, tests, comentarios técnicos y nombres de archivos conservados. No hay workflows versionados ni hooks locales activos, solo ejemplos `.sample`; no se encontró configuración versionada de integración dependiente de esa rama. Esto no certifica la ausencia de integraciones externas no expuestas por Git; no se modifican servicios externos ni configuración operativa.

La verificación de esta organización es documental: diff completo, enlaces locales nuevos/modificados, finales de línea, alcance de archivos, índice, hashes y referencias remotas. No se repiten suites funcionales, extracciones ni pruebas con datos reales porque no cambia código ni presentación. Los resultados de pruebas de informes anteriores siguen siendo históricos.

## Recuperación sin pérdida de trabajo

Consultar primero el estado y una referencia conservada:

```powershell
git status --short
git show --no-patch --oneline codex/backup-pre-develop-20261109-190254
git show --no-patch --oneline 'v0.8.0^{}'
```

Si se necesita recuperar el código, abrir un checkout separado desde `v0.8.0` o el respaldo con el gestor de worktrees del entorno, usando una ruta nueva. No cambiar el checkout con trabajo pendiente ni suponer que el respaldo contiene `docs/`: una rama protege commits, no archivos sin seguimiento. Conservar por separado los archivos locales privados cuando corresponda.

Para deshacer cambios ya registrados, revisar el commit y crear un nuevo commit de reversión en `develop` (`git revert HASH_REVISADO`) cuando proceda; su push requiere autorización. No usar `reset --hard`, borrar historial, mover tags ni eliminar referencias para recuperar trabajo.
