"""Auditoría reproducible de SQLite y exportación local sin peticiones al portal."""
import json
from pathlib import Path
import sys
from collections import Counter
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from metro.storage import Store
from metro.extraction import walk

store=Store()
run_id=int(sys.argv[1]) if len(sys.argv)>1 else 1
summary=store.summary(run_id)
with store.connect() as db:
    integrity=db.execute('PRAGMA integrity_check').fetchone()[0]
    documents=[json.loads(r[0]) for r in db.execute('SELECT data_json FROM jobs WHERE run_id=? AND data_json IS NOT NULL',(run_id,))]
    attempts=[dict(r) for r in db.execute('SELECT property_id,attempts,status FROM jobs WHERE run_id=? AND attempts!=1',(run_id,))]
    errors=[dict(r) for r in db.execute("SELECT kind,context_json FROM events WHERE run_id=? AND level='error'",(run_id,))]
report={'summary':summary,'sqlite_integrity':integrity,
        'types':dict(Counter(d['normalized'].get('property_type') for d in documents)),
        'photo_urls':sum(len(d['photos']) for d in documents),
        'without_description':sum(not d['normalized'].get('description') for d in documents),
        'without_photos':sum(not d['photos'] for d in documents),
        'field_errors':sum(len(d['errors']) for d in documents),
        'non_single_attempt_jobs':attempts,'error_events':errors}
out=Path(__file__).resolve().parents[1]/'data/verification'
out.mkdir(parents=True,exist_ok=True)
(out/'integrity.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=False,indent=2))
