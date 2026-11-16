"""Un calendario semanal, CAS durable y sincronización recuperable con Scheduler."""
import copy
import json
import os
import re
from datetime import datetime, timedelta, timezone
from uuid import uuid4, uuid5, NAMESPACE_URL
from zoneinfo import ZoneInfo
from .control import ACTIVE, Conflict, now, select, reserve

TZ = ZoneInfo('America/Bogota')
DAYS = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo']
DEFAULT = {'enabled': False, 'revision': '', 'keys': [], 'days': [], 'time': '00:30', 'effective_after': None}


def validate(keys, days, clock):
    if not isinstance(keys, list) or not 1 <= len(keys) <= 100 or any(not isinstance(k, list) or len(k) != 2 or any(not isinstance(v, str) or not v for v in k) for k in keys):
        raise ValueError('Selecciona entre 1 y 100 búsquedas activas.')
    if not isinstance(days, list) or not days or any(type(d) is not int or not 0 <= d <= 6 for d in days):
        raise ValueError('Selecciona uno o varios días de lunes a domingo.')
    if not isinstance(clock, str) or not re.fullmatch(r'(?:[01][0-9]|2[0-3]):[0-5][0-9]', clock):
        raise ValueError('La hora debe tener formato de 24 horas: HH:MM.')
    return dict(keys=[list(k) for k in dict.fromkeys(tuple(k) for k in keys)], days=sorted(set(days)), time=clock)


def cron(config):
    hour, minute = config['time'].split(':')
    return f"{int(minute)} {int(hour)} * * " + ','.join(str((d + 1) % 7) for d in config['days'])


def upcoming(config, after=None, count=5):
    after = after or datetime.now(timezone.utc)
    if after.tzinfo is None:
        raise ValueError('Se requiere una fecha con zona horaria.')
    local = after.astimezone(TZ)
    h, m = map(int, config['time'].split(':'))
    dates = []
    for i in range(50):
        date = (local + timedelta(days=i)).replace(hour=h, minute=m, second=0, microsecond=0)
        if date > local and date.weekday() in config['days']:
            dates.append(date.isoformat())
            if len(dates) == count:
                break
    return dates


def view(doc, cloud_state=None, error=None):
    config = copy.deepcopy(doc.get('schedule', DEFAULT))
    selected = {tuple(k) for k in config['keys']}
    rows = doc.get('searches', [])
    available = {(b['fuente'], b['id_busqueda']) for b in rows if b['activa']}
    warnings = ['Una búsqueda seleccionada fue eliminada o está inactiva; se omitirá de forma segura.'] if selected - available else []
    pending = config.get('pending')
    active = bool(config['enabled'] and not pending and cloud_state == 'ENABLED' and not error)
    names = [DAYS[d].lower() for d in config['days']]
    summary = (', '.join(names[:-1]) + ' y ' + names[-1] if len(names) > 1 else ''.join(names)) + ' a las ' + config['time'] if names else 'Elige días y hora.'
    summary = summary[0].upper() + summary[1:]
    return dict(config=config, active=active, uncertain=bool(error or pending or (config['enabled'] and not active)),
                error=error, warnings=warnings, summary=summary, selected=selected, days=list(enumerate(DAYS)),
                next=upcoming(config) if active else [], weekly=len(config['days']), search_weekly=len(config['days'])*len(selected), cloud_state=cloud_state)


def occurrence_reason(doc, occurrence, at=None):
    cfg = doc.get('schedule', DEFAULT)
    if not cfg['enabled'] or cfg.get('pending'):
        return 'Omitida: programación desactivada o sincronización pendiente.'
    if occurrence['revision'] != cfg['revision']:
        return 'Omitida: configuración sustituida.'
    date = datetime.fromisoformat(occurrence['scheduled_at'])
    at = at or datetime.now(timezone.utc)
    if date.tzinfo is None:
        raise ValueError('Hora programada sin zona horaria.')
    if not cfg.get('effective_after') or date <= datetime.fromisoformat(cfg['effective_after']):
        return 'Omitida: fecha anterior a la activación o edición.'
    if not 0 <= (at-date).total_seconds() <= 900:
        return 'Omitida: entrega fuera del margen de 15 minutos.'
    local = date.astimezone(TZ)
    if local.weekday() not in cfg['days'] or local.strftime('%H:%M') != cfg['time'] or local.second or local.microsecond:
        return 'Omitida: hora ajena al calendario vigente.'
    return None


class InvalidOccurrence(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def scheduler_identity(value, expected):
    if value is None or value == '':
        raise InvalidOccurrence('missing_job_header')
    short = expected.rsplit('/', 1)[-1]
    if value == expected:
        return expected, 'full'
    if value == short:
        return expected, 'short'
    raise InvalidOccurrence('unrecognized_job')


def scheduled_time(value):
    if not value:
        raise InvalidOccurrence('missing_schedule_header')
    try:
        date = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if date.tzinfo is None:
            raise ValueError()
        return date.astimezone(timezone.utc).isoformat()
    except (ValueError, TypeError, AttributeError):
        raise InvalidOccurrence('invalid_schedule_time') from None


class Programacion:
    def __init__(self, service, scheduler):
        self.service, self.control, self.scheduler = service, service.control, scheduler

    def read(self, doc=None):
        doc = doc if doc is not None else self.control.read()[0]
        try:
            cfg = doc.get('schedule', DEFAULT)
            remote = self.scheduler.get()
            if cfg.get('pending'):
                # No reanuda automáticamente. Permite retomar explícitamente Guardar/Pausar.
                return view(doc, remote.get('state') if remote else None, 'Sincronización pendiente. Guarda de nuevo o pausa para recuperar el estado.')
            if cfg['enabled'] and (not remote or not self.scheduler.matches(remote, cfg)):
                return view(doc, None, 'Scheduler no coincide con la configuración. Guarda de nuevo o pausa antes de activar.')
            return view(doc, remote.get('state') if remote else None)
        except Exception:
            return view(doc, None, 'No se pudo verificar Scheduler. No se confirma la programación activa; vuelve a guardar o pausa.')

    def save(self, keys, days, clock, action, expected):
        if action not in {'save', 'activate', 'pause'}:
            raise ValueError('Acción de programación inválida.')
        initial = self.control.read()[0].get('schedule', DEFAULT)
        if action == 'pause':
            values = {k: copy.deepcopy(initial[k]) for k in ('keys','days','time')}
        else:
            values = validate(keys, days, clock)
            self.service.snapshot_searches(lambda rows: select(rows, values['keys']))
        token = str(uuid4())
        def begin(doc):
            old = doc.get('schedule', DEFAULT)
            if old['revision'] != expected:
                raise Conflict('La programación cambió en otra ventana. Recarga antes de guardar.')
            pending = old.get('pending')
            if pending and (datetime.now(timezone.utc)-datetime.fromisoformat(pending['at'])).total_seconds() < 90:
                raise Conflict('Hay una sincronización en curso. Espera y recarga.')
            desired = dict(values, enabled=(False if action == 'pause' else True if action == 'activate' else old['enabled']), revision=token, effective_after=now())
            doc['schedule'] = dict(old, pending=dict(token=token, at=now(), desired=desired))
            return desired
        desired = self.control.change(begin)
        try:
            self.scheduler.sync(desired)
            def finish(doc):
                cfg = doc['schedule']
                if cfg.get('pending', {}).get('token') != token:
                    raise Conflict('La sincronización fue sustituida. Recarga.')
                doc['schedule'] = desired
                audit = doc.setdefault('schedule_audit', [])
                audit.append(dict(at=now(), action=action, revision=token, enabled=desired['enabled'], result='confirmed'))
                del audit[:-30]
            self.control.change(finish)
        except Exception:
            def failure(doc):
                if doc.get('schedule', {}).get('pending', {}).get('token') == token:
                    doc['schedule']['pending']['error'] = 'scheduler_sync_failed'
                    audit = doc.setdefault('schedule_audit', [])
                    audit.append(dict(at=now(), action=action, revision=token, result='uncertain'))
                    del audit[:-30]
            self.control.change(failure)
            raise RuntimeError('No se confirmó la sincronización con Scheduler. El inicio automático queda bloqueado; vuelve a guardar o pausa.') from None
        return desired

    def deliver(self, job, revision, scheduled_at):
        job, _ = scheduler_identity(job, self.scheduler.name)
        scheduled_at = scheduled_time(scheduled_at)
        occurrence = dict(job=job, revision=revision, scheduled_at=scheduled_at)
        identity = str(uuid5(NAMESPACE_URL, job+'|'+revision+'|'+scheduled_at))
        doc = self.control.read()[0]
        prior = next((r for r in doc['runs'] if r['id'] == identity), None)
        if prior:
            return prior
        reason = occurrence_reason(doc, occurrence)
        # No descarga ni bloquea SQLite en el disparador. El Job revalida la selección
        # autoritativa antes de tocar portales, igual que Manual. Nunca deja un lock
        # de snapshot huérfano si el proceso HTTP muere después de reservar.
        lookup = {(b['fuente'], b['id_busqueda']): b for b in doc.get('searches', [])}
        selected = [lookup.get(tuple(k), dict(fuente=k[0], id_busqueda=k[1], nombre=k[1], url='', activa=True)) for k in doc.get('schedule', DEFAULT)['keys']]
        if not reason:
            from .cloud_run import reconcile
            from google.api_core.exceptions import NotFound
            reconcile(self.control, self.service.cloud, self.service.unlock)
            try:
                self.service.state_factory().lock.reload(timeout=10)
                reason = 'Omitida por ejecución en curso o catálogo ocupado.'
            except NotFound:
                pass
        if reason:
            occurrence['reason'] = reason
        run, created = reserve(self.control, identity, selected, automatic=occurrence)
        if created:
            try:
                self.service.cloud.launch(run['id'])
            except Exception:
                pass  # Reserva incierta: la reconciliación existente revoca; jamás relanza.
        return self.control.get(run['id']) if created else run
