"""Programaciones independientes sobre las reservas y el Scheduler existentes.

La lectura migra en memoria; solo una escritura explícita confirma el formato.
El calendario anterior se conserva en schedule_legacy. No migra snapshots SQLite.
"""
import copy
from datetime import datetime, timedelta, timezone
from uuid import uuid4, uuid5, NAMESPACE_URL
from .control import ACTIVE, Conflict, IntegrityError, now, select
from .programacion import (Programacion, DEFAULT, TZ, DAYS, validate, upcoming,
                          scheduler_identity, scheduled_time)

LEGACY_ID = str(uuid5(NAMESPACE_URL, 'radar:legacy-shared-schedule'))
MAX_PLANS = 100


class FieldError(ValueError):
    def __init__(self, field, message):
        self.field = field
        super().__init__(message)


def plans(doc, at=None):
    if doc.get('schedules_version', 1) != 1:
        raise IntegrityError('Formato de programación más reciente; actualización requerida.')
    if 'schedules' in doc:
        return copy.deepcopy(doc['schedules'])
    old = doc.get('schedule', DEFAULT)
    if not old.get('revision'):
        return {}
    stamp = old.get('effective_after') or at or now()
    last = next((r for r in sorted(doc.get('runs', []), key=lambda r:r.get('created',''), reverse=True) if r.get('origin')=='automatic'), None)
    return {LEGACY_ID: dict({k:v for k,v in copy.deepcopy(old).items() if k != 'pending'}, id=LEGACY_ID,
        name='Programación general', frequency='weekly', date=None,
        created_at=stamp, updated_at=stamp, cursor=at or now(),
        timezone='America/Bogota', legacy_identity=True, last_run=dict(id=last['id'], scheduled_at=last.get('scheduled_at')) if last else None,
        deleted=False, consumed_at=None)}


def migrate(doc, at=None):
    # Rechazar formatos futuros también al escribir, no solo en la vista.
    if doc.get('schedules_version', 1) != 1:
        raise IntegrityError('Formato de programación más reciente; actualización requerida.')
    if 'schedules' in doc and doc.get('version') != 2:
        raise IntegrityError('Colección múltiple sin barrera de versión; requiere revisión explícita')
    if 'schedules' not in doc:
        if any(r.get('status') in ACTIVE for r in doc.get('runs', [])):
            raise Conflict('Espera el cierre de las ejecuciones antes de convertir el calendario')
        doc['schedules'] = plans(doc, at)
        doc['version'] = 2
        doc['schedule_legacy'] = copy.deepcopy(doc.get('schedule', DEFAULT))
        doc['schedules_version'] = 1


def next_dates(plan, after=None, count=1):
    if plan.get('deleted') or not plan['enabled'] or plan.get('consumed_at'):
        return []
    after = after or datetime.now(timezone.utc)
    if after.tzinfo is None:
        raise ValueError('La fecha requiere zona horaria.')
    after = max(after, datetime.fromisoformat(plan['effective_after']))
    if plan['frequency'] == 'once':
        date = datetime.fromisoformat(plan['date']+'T'+plan['time']).replace(tzinfo=TZ)
        return [date.isoformat()] if date > after else []
    return upcoming(plan, after, count)


def validate_plan(values, at=None):
    at = at or datetime.now(timezone.utc)
    name = values.get('name', '')
    if not isinstance(name, str) or not 1 <= len(name.strip()) <= 120:
        raise FieldError('name', 'Escribe un nombre de 1 a 120 caracteres.')
    frequency = values.get('frequency')
    if frequency not in {'daily', 'weekly', 'once'}:
        raise FieldError('frequency', 'Selecciona una frecuencia válida.')
    keys, days = values.get('keys'), values.get('days', [])
    if not keys:
        raise FieldError('keys', 'Selecciona al menos una búsqueda activa.')
    try:
        clock = f"{int(values['hour']):02}:{int(values['minute']):02}"
        if str(values['hour']) not in [str(n) for n in range(24)] + [f'{n:02}' for n in range(24)] or str(values['minute']) not in [str(n) for n in range(60)] + [f'{n:02}' for n in range(60)]:
            raise ValueError()
    except (ValueError, TypeError, KeyError):
        raise FieldError('time', 'Selecciona hora y minutos válidos.') from None
    if frequency != 'weekly':
        days = list(range(7))
    try:
        config = validate(keys, days, clock)
    except ValueError as exc:
        field = 'days' if not days or any(type(d) is not int or not 0 <= d <= 6 for d in days) else 'keys'
        raise FieldError(field, str(exc)) from None
    date = None
    if frequency == 'once':
        try:
            raw = values.get('date', '')
            date = datetime.strptime(raw, '%Y-%m-%d').date().isoformat()
            if raw != date or datetime.fromisoformat(date+'T'+clock).replace(tzinfo=TZ) <= at:
                raise ValueError()
        except (ValueError, TypeError):
            raise FieldError('date', 'Selecciona una fecha y hora futuras válidas.') from None
    if type(values.get('enabled', False)) is not bool:
        raise FieldError('enabled', 'El estado inicial no es válido.')
    return dict(config, name=name.strip(), frequency=frequency, date=date,
                enabled=values.get('enabled', False), timezone='America/Bogota')


class Calendarios(Programacion):
    def read(self, doc=None):
        doc = self.control.read()[0] if doc is None else doc
        rows = plans(doc)
        cfg = doc.get('schedule', DEFAULT)
        error = None
        try:
            remote = self.scheduler.get()
            if cfg.get('pending') or (cfg['enabled'] and (not remote or remote.get('state') != 'ENABLED' or not self.scheduler.matches(remote, cfg))):
                error = 'No se pudo confirmar la programación. Guarda o pausa para verificarla.'
        except Exception:
            error = 'No se pudo verificar el servicio de programación. Vuelve a intentarlo.'
        result = []
        for p in rows.values():
            if p.get('deleted'):
                continue
            dates = next_dates(p)
            result.append(dict(p, next=dates[0] if dates and not error else None,
                uncertain=bool(error), summary=(('Diaria' if p['frequency']=='daily' else 'Una sola vez · '+p['date'] if p['frequency']=='once' else ', '.join(DAYS[d] for d in p['days']))+' · '+p['time']),
                last=next((r for r in doc['runs'] if r['id']==(p.get('last_run') or {}).get('id')), None)))
        result.sort(key=lambda p:(p['created_at'],p['id']))
        return dict(items=result, error=error, active=sum(p['enabled'] and not p.get('consumed_at') and not error for p in result),
                    paused=sum(not p['enabled'] for p in result),
                    running=sum(r['status'] in {'running','saving'} and r.get('verification', {}).get('state')=='active' for r in doc['runs']),
                    next=min((p['next'] for p in result if p['next']), default=None), revision=cfg['revision'])

    def change(self, action, identifier=None, values=None, expected='', collection_revision=None):
        if action not in {'create','edit','activate','pause','duplicate','delete'}:
            raise ValueError('Acción inválida.')
        stamp, token = now(), str(uuid4())
        new_id = str(uuid4())
        validated = validate_plan(values) if action in {'create','edit'} else None
        if validated:
            self.service.snapshot_searches(lambda rows: select(rows, validated['keys']))
        if action == 'activate':
            existing = plans(self.control.read()[0]).get(identifier, {})
            try:
                self.service.snapshot_searches(lambda rows: select(rows, existing.get('keys', [])))
            except ValueError as exc:
                raise FieldError('keys', str(exc)) from None
        def begin(doc):
            migrate(doc, stamp)
            old = doc.get('schedule', DEFAULT)
            pending = old.get('pending')
            if pending and (datetime.now(timezone.utc)-datetime.fromisoformat(pending['at'])).total_seconds() < 90:
                raise Conflict('Hay un guardado en curso. Espera y recarga.')
            if collection_revision is not None and old['revision'] != collection_revision:
                raise Conflict('La lista cambió en otra ventana. Recarga antes de guardar.')
            rows = copy.deepcopy(doc['schedules'])
            plan = rows.get(identifier)
            if action != 'create' and (not plan or plan.get('deleted') or plan['revision'] != expected):
                raise Conflict('La programación cambió en otra ventana. Recarga antes de guardar.')
            target = new_id if action in {'create','duplicate'} else identifier
            if action in {'create','duplicate'} and len(rows) >= MAX_PLANS:
                raise ValueError('Se alcanzó el límite de 100 programaciones, incluidas las eliminadas. Conserva su historial y revisa la configuración.')
            if action == 'create':
                rows[target] = dict(validated, id=target, created_at=stamp, last_run=None, consumed_at=None, deleted=False)
            elif action == 'edit':
                rows[target].update(validated, consumed_at=None)
            elif action == 'duplicate':
                rows[target] = dict(copy.deepcopy(plan), id=target, name=('Copia de '+plan['name'])[:120], enabled=False,
                    created_at=stamp, last_run=None, consumed_at=None, legacy_identity=False)
            else:
                if action == 'activate' and plan['frequency']=='once' and (plan.get('consumed_at') or datetime.fromisoformat(plan['date']+'T'+plan['time']).replace(tzinfo=TZ) <= datetime.now(timezone.utc)):
                    raise FieldError('date', 'La ejecución única ya pasó. Edita su fecha para volver a programarla.')
                rows[target]['enabled'] = action == 'activate'
                if action == 'delete':
                    rows[target]['deleted'] = True
            rows[target].update(revision=token, updated_at=stamp, effective_after=stamp, cursor=stamp)
            desired = dict(DEFAULT, mode='multiple', revision=token,
                enabled=any(p['enabled'] and not p.get('deleted') and not p.get('consumed_at') for p in rows.values()),
                keys=[['coordinator','multiple']], days=list(range(7)), effective_after=stamp)
            doc['schedule'] = dict(old, pending=dict(token=token, at=stamp, desired=desired, schedules=rows))
            return desired
        desired = self.control.change(begin)
        try:
            self.scheduler.sync(desired)
            def finish(doc):
                pending = doc['schedule'].get('pending', {})
                if pending.get('token') != token:
                    raise Conflict('El guardado fue sustituido. Recarga la página.')
                doc['schedules'] = pending['schedules']
                doc['schedule'] = desired
                audit = doc.setdefault('schedule_audit', [])
                audit.append(dict(at=stamp, action=action, schedule_id=new_id if action in {'create','duplicate'} else identifier, revision=token, result='confirmed'))
                del audit[:-30]
            self.control.change(finish)
        except Exception:
            raise RuntimeError('No se confirmó el guardado. La programación automática queda bloqueada; recarga y vuelve a guardar o pausa.') from None
        return self.control.read()[0]['schedules'][new_id if action in {'create','duplicate'} else identifier]

    def tick(self, job, revision, scheduled_at, document=None):
        job, _ = scheduler_identity(job, self.scheduler.name)
        tick = datetime.fromisoformat(scheduled_time(scheduled_at))
        if tick.second or tick.microsecond:
            raise ValueError('El disparo debe corresponder a un minuto exacto.')
        current = datetime.now(timezone.utc)
        if not 0 <= (current-tick).total_seconds() <= 900:
            raise ValueError('Disparo fuera del margen de 15 minutos.')
        doc = document if document is not None else self.control.read()[0]
        cfg = doc.get('schedule', DEFAULT)
        if cfg.get('pending') or cfg['revision'] != revision or not cfg['enabled']:
            raise Conflict('El calendario cambió o está pausado.')
        due = []
        for p in plans(doc).values():
            if not p['enabled'] or p.get('deleted') or p.get('consumed_at'):
                continue
            cursor = max(datetime.fromisoformat(p['effective_after']), datetime.fromisoformat(p.get('cursor') or p['effective_after']))
            for date in next_dates(p, cursor, 100):
                if datetime.fromisoformat(date) <= tick:
                    due.append((date,p['id'],p))
        results = []
        for date, identifier, p in sorted(due)[:100]:
            occurrence = dict(job=job, revision=p['revision'], scheduled_at=scheduled_time(date), schedule_id=identifier, schedule_name=p['name'])
            material = job+'|'+('' if p.get('legacy_identity') else identifier+'|')+p['revision']+'|'+occurrence['scheduled_at']
            identity = str(uuid5(NAMESPACE_URL, material))
            results.append(self.submit(identity, occurrence, p))
        return dict(id=str(uuid5(NAMESPACE_URL, job+'|'+revision+'|'+tick.isoformat())), status='completed', occurrences=results)
