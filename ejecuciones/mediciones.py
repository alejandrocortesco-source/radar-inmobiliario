"""Lectura de métricas técnicas previas, sin abrir Store ni migrar el catálogo."""
import sqlite3
from contextlib import closing
from datetime import datetime


def previous(folder, search):
    filename = {'metrocuadrado':'metro.sqlite','wasi':'wasi.sqlite','fincaraiz':'fincaraiz.sqlite'}[search['fuente']]
    file = folder / filename
    if not file.is_file():
        return None, []
    try:
        with closing(sqlite3.connect(file.as_uri() + '?mode=ro', uri=True)) as db:
            db.row_factory = sqlite3.Row
            runs = db.execute("SELECT r.* FROM runs r JOIN run_searches s ON s.run_id=r.id WHERE s.search_url=? ORDER BY r.id DESC LIMIT 10", (search['id_busqueda'],)).fetchall()
            result = []
            for r in runs:
                one = db.execute('SELECT count(*) FROM run_searches WHERE run_id=?', (r['id'],)).fetchone()[0] == 1
                duration = max(0, (datetime.fromisoformat(r['finished']) - datetime.fromisoformat(r['started'])).total_seconds()) if r['finished'] else None
                counts = dict(db.execute('SELECT status,count(*) FROM jobs WHERE run_id=? GROUP BY status', (r['id'],))) if one else {}
                processed = sum(v for k,v in counts.items() if k in {'success','unchanged','partial','failed','blocked'}) if one else None
                result.append({'fuente':search['fuente'],'id_busqueda':search['id_busqueda'], 'technical_run':r['id'],
                               'status':{'incomplete':'partial','blocked':'failed'}.get(r['status'],r['status']),
                               'started':r['started'],'finished':r['finished'], 'duration':duration if one else None,
                               'technical_duration':duration, 'scope':'esta búsqueda' if one else 'captura compartida', 'processed':processed})
            return (result[0] if result else None), [r for r in result if r['status']=='completed' and r['duration'] is not None][:5]
    except sqlite3.OperationalError:
        # Un esquema histórico sin métricas compatibles no es una medición inventada.
        return None, []
