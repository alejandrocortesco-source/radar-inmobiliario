"""Reversión lógica explícita; no restaura snapshots ni ejecuta capturas."""
import copy
from datetime import datetime, timezone
from uuid import uuid4
from .control import ACTIVE, Conflict, IntegrityError, now


def rollback_legacy(control, scheduler, expected):
    token = str(uuid4())
    def begin(doc):
        if doc.get('version') != 2 or doc['schedule']['revision'] != expected:
            raise Conflict('Versión o revisión distinta de la esperada')
        if any(r['status'] in ACTIVE for r in doc['runs']):
            raise Conflict('Hay trabajadores; no se puede revertir')
        pending = doc['schedule'].get('pending')
        if pending and (datetime.now(timezone.utc)-datetime.fromisoformat(pending['at'])).total_seconds()<90:
            raise Conflict('Hay una transición pendiente')
        legacy = copy.deepcopy(doc.get('schedule_legacy'))
        if not legacy:
            raise IntegrityError('No existe calendario previo para restaurar')
        legacy.pop('pending', None)
        legacy.update(enabled=False, revision=token, effective_after=now())
        doc['schedule']['pending'] = dict(token=token, at=now(), desired=legacy)
        return legacy
    desired = control.change(begin, transition=True)
    # Si falla, el gate pending queda cerrado. No se baja el esquema.
    scheduler.sync(desired)
    def finish(doc):
        if doc['schedule'].get('pending', {}).get('token') != token:
            raise Conflict('La transición fue sustituida')
        if any(r['status'] in ACTIVE for r in doc['runs']):
            raise Conflict('Apareció un trabajador; conservar gate cerrado')
        archives = doc.setdefault('schedules_archives', [])
        archives.append(dict(at=now(), schedules=copy.deepcopy(doc['schedules'])))
        del doc['schedules']
        doc.pop('schedules_version', None)
        doc.update(version=1, schedule=desired)
        doc.setdefault('schedule_audit', []).append(dict(at=now(), action='rollback', revision=token, result='confirmed'))
    control.change(finish, transition=True)
    return desired
