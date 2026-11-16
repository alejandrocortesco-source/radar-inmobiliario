"""Proyección de resultados finales; no modifica decisiones ni documentos del scraper."""
import json
from decimal import InvalidOperation

from metro.prices import comparable, detail_price, price, same_price

VERSION = 2
FINAL_KEYS = ('new', 'changed', 'unchanged', 'partial', 'failed', 'blocked', 'unclassified')
COUNT_KEYS = ('processed',) + FINAL_KEYS + ('pending', 'reused', 'reread_unchanged', 'method_unknown')
TERMINAL = {'success', 'unchanged', 'partial', 'failed', 'blocked'}


def obj(value):
    if isinstance(value, dict):
        return value
    try:
        parsed = json.loads(value) if value else {}
        return parsed if isinstance(parsed, dict) else {}
    except (ValueError, TypeError):
        return {}


def final_result(job, fallback=None):
    status = job.get('status')
    if status in ('partial', 'failed', 'blocked'):
        return status
    if status not in TERMINAL:
        return 'pending'
    data = obj(job.get('data_json'))
    if data.get('quality') != 'success' or not isinstance(data.get('normalized'), dict):
        return 'unclassified'
    # new/no_catalog_detail prueba que no existía ficha, no que faltaba el precio.
    if job.get('classification') == 'new' and job.get('decision_reason') == 'no_catalog_detail':
        return 'new'
    previous = obj(job.get('previous_price_json'))
    if previous.get('status') != 'valid':
        return 'unclassified'
    previous = price(previous.get('amount'), previous.get('currency'), previous.get('operation'))
    try:
        current = detail_price(data, fallback)
        if not comparable(previous, current):
            return 'unclassified'
        return 'unchanged' if same_price(previous, current) else 'changed'
    except (ValueError, TypeError, KeyError, InvalidOperation):
        return 'unclassified'


def summarize(jobs, fallback=None):
    result = dict.fromkeys(COUNT_KEYS, 0)
    for job in jobs:
        category = final_result(job, fallback)
        result[category] += 1
        if category != 'pending':
            result['processed'] += 1
        if category == 'unchanged':
            attempts = job.get('attempts')
            if attempts == 0 and job.get('status') == 'unchanged':
                result['reused'] += 1
            elif isinstance(attempts, int) and attempts > 0:
                result['reread_unchanged'] += 1
            else:
                result['method_unknown'] += 1
    return dict(result, report_version=VERSION, report_origin='worker')


def from_db(db, run_id, search_url=None, *, source=None):
    """SELECT sobre una transacción del trabajador o una copia histórica immutable."""
    config_row = db.execute('SELECT config_json FROM runs WHERE id=?', (run_id,)).fetchone()
    if config_row is None:
        raise ValueError('Captura técnica no disponible')
    config = obj(config_row[0])
    args = [run_id]
    sql = 'SELECT * FROM jobs WHERE run_id=?'
    if search_url is not None:
        scopes = [r[0] for r in db.execute('SELECT search_url FROM run_searches WHERE run_id=?', (run_id,))]
        if search_url not in scopes and source == 'metrocuadrado':
            from metro.prices import search_identity
            search_url = search_identity(search_url)
        elif search_url not in scopes and source == 'fincaraiz':
            from catalogo.fuentes.fincaraiz import identidad
            search_url = identidad(search_url)
        if search_url not in scopes:
            raise ValueError('La captura no corresponde a esta búsqueda')
        if len(scopes) > 1:
            sql += ' AND property_id IN (SELECT property_id FROM listing_observations WHERE run_id=? AND search_url=?)'
            args += [run_id, search_url]
    cursor = db.execute(sql, args)
    columns = [c[0] for c in cursor.description]
    if 'status' not in columns:
        raise ValueError('Estados históricos no disponibles')
    jobs = [dict(zip(columns, row)) for row in cursor]
    return summarize(jobs, config.get('listing_currency'))


def valid(report):
    return (report.get('report_version') == VERSION and
            all(type(report.get(k)) is int and report[k] >= 0 for k in COUNT_KEYS) and
            sum(report[k] for k in FINAL_KEYS) == report['processed'] and
            report['reused'] + report['reread_unchanged'] + report['method_unknown'] == report['unchanged'])


def unavailable(search, note='No hay evidencia histórica suficiente para verificar la clasificación final.'):
    reported = search.get('reported') or {k:search.get(k) for k in ('processed','new','changed','unchanged')}
    return dict({k:None for k in COUNT_KEYS}, processed=search.get('processed'), report_version=0,
                report_origin='unavailable', report_note=note, reported=reported)


def presentation(search):
    if valid(search):
        return dict(search)
    return dict(search, **unavailable(search))
