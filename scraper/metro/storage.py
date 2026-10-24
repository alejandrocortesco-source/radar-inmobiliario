import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from .paths import DEFAULT_DB
from .prices import search_identity, listing_price, detail_price, comparable, same_price


def now():
    return datetime.now(timezone.utc).isoformat()


def dumps(value):
    return json.dumps(value, ensure_ascii=False)


class Store:
    def __init__(self, path=DEFAULT_DB):
        self.path = str(path)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript('''
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS runs (
              id INTEGER PRIMARY KEY, url TEXT NOT NULL, started TEXT NOT NULL,
              finished TEXT, status TEXT NOT NULL, advertised_json TEXT,
              listing_complete INTEGER NOT NULL DEFAULT 0, config_json TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS pages (
              run_id INTEGER NOT NULL REFERENCES runs(id), number INTEGER NOT NULL,
              active TEXT, url TEXT NOT NULL, fingerprint TEXT NOT NULL,
              links_json TEXT NOT NULL, next_json TEXT, visited TEXT NOT NULL,
              PRIMARY KEY(run_id,number), UNIQUE(run_id,fingerprint));
            CREATE TABLE IF NOT EXISTS properties (
              id TEXT PRIMARY KEY, url TEXT UNIQUE NOT NULL, data_json TEXT,
              title TEXT, price REAL, city TEXT, property_type TEXT, updated TEXT);
            CREATE TABLE IF NOT EXISTS appearances (
              run_id INTEGER NOT NULL, page INTEGER NOT NULL, property_id TEXT NOT NULL,
              url TEXT NOT NULL, PRIMARY KEY(run_id,page,property_id));
            CREATE TABLE IF NOT EXISTS jobs (
              run_id INTEGER NOT NULL, property_id TEXT NOT NULL REFERENCES properties(id),
              status TEXT NOT NULL DEFAULT 'pending', attempts INTEGER NOT NULL DEFAULT 0,
              error TEXT, data_json TEXT, updated TEXT,
              PRIMARY KEY(run_id,property_id));
            CREATE TABLE IF NOT EXISTS events (
              id INTEGER PRIMARY KEY, run_id INTEGER NOT NULL, time TEXT NOT NULL,
              level TEXT NOT NULL, kind TEXT NOT NULL, context_json TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS appearances_property ON appearances(property_id);
            ''')
            self._migrate_incremental(db)
            db.execute('CREATE INDEX IF NOT EXISTS observations_job ON listing_observations(run_id,property_id)')
            db.execute('CREATE INDEX IF NOT EXISTS memberships_property ON search_memberships(property_id)')

    def _migrate_incremental(self, db):
        if db.execute('PRAGMA user_version').fetchone()[0] >= 1:
            return
        # SQLite backup incluye el WAL; nunca se copia un archivo abierto a mano.
        if db.execute('SELECT count(*) FROM properties').fetchone()[0]:
            backup = Path(self.path).with_name(Path(self.path).stem+'.pre-incremental.sqlite')
            if not backup.exists():
                with sqlite3.connect(backup) as target:
                    db.backup(target)
        db.execute('BEGIN IMMEDIATE')
        if db.execute('PRAGMA user_version').fetchone()[0] >= 1:
            return
        old_pages = [dict(r) for r in db.execute('SELECT * FROM pages ORDER BY run_id,number')]
        old_appearances = [dict(r) for r in db.execute('SELECT * FROM appearances')]
        runs = {r['id']:dict(r) for r in db.execute('SELECT * FROM runs')}
        db.execute('''CREATE TABLE pages_v2 (
          run_id INTEGER NOT NULL REFERENCES runs(id), search_url TEXT NOT NULL, number INTEGER NOT NULL,
          active TEXT, url TEXT NOT NULL, fingerprint TEXT NOT NULL, links_json TEXT NOT NULL,
          next_json TEXT, visited TEXT NOT NULL, PRIMARY KEY(run_id,search_url,number),
          UNIQUE(run_id,search_url,fingerprint))''')
        db.execute('''CREATE TABLE appearances_v2 (
          run_id INTEGER NOT NULL,search_url TEXT NOT NULL,page INTEGER NOT NULL,
          property_id TEXT NOT NULL,url TEXT NOT NULL,PRIMARY KEY(run_id,search_url,page,property_id))''')
        for row in old_pages:
            db.execute('INSERT INTO pages_v2 VALUES(?,?,?,?,?,?,?,?,?)',
                       (row['run_id'],search_identity(runs[row['run_id']]['url']),row['number'],row['active'],
                        row['url'],row['fingerprint'],row['links_json'],row['next_json'],row['visited']))
        for row in old_appearances:
            db.execute('INSERT INTO appearances_v2 VALUES(?,?,?,?,?)',
                       (row['run_id'],search_identity(runs[row['run_id']]['url']),row['page'],row['property_id'],row['url']))
        db.execute('DROP TABLE pages')
        db.execute('ALTER TABLE pages_v2 RENAME TO pages')
        db.execute('DROP TABLE appearances')
        db.execute('ALTER TABLE appearances_v2 RENAME TO appearances')
        db.execute('CREATE INDEX appearances_property ON appearances(property_id)')
        db.execute('ALTER TABLE properties ADD COLUMN needs_refresh INTEGER NOT NULL DEFAULT 0')
        for column in ('classification','decision_reason','listing_price_json','previous_price_json'):
            db.execute(f'ALTER TABLE jobs ADD COLUMN {column} TEXT')
        db.execute("UPDATE jobs SET classification='legacy' WHERE status IN ('success','partial')")
        for statement in (
            '''CREATE TABLE run_searches (
              run_id INTEGER NOT NULL REFERENCES runs(id),search_url TEXT NOT NULL,source_url TEXT NOT NULL,
              listing_complete INTEGER NOT NULL DEFAULT 0,advertised_json TEXT,
              absence_applied INTEGER NOT NULL DEFAULT 0,PRIMARY KEY(run_id,search_url))''',
            '''CREATE TABLE listing_observations (
              run_id INTEGER NOT NULL,search_url TEXT NOT NULL,property_id TEXT NOT NULL,
              price_json TEXT NOT NULL,conflict INTEGER NOT NULL DEFAULT 0,verified_at TEXT NOT NULL,
              PRIMARY KEY(run_id,search_url,property_id))''',
            '''CREATE TABLE search_memberships (
              search_url TEXT NOT NULL,property_id TEXT NOT NULL REFERENCES properties(id),
              state TEXT NOT NULL DEFAULT 'active',first_seen TEXT NOT NULL,last_verified_at TEXT NOT NULL,
              last_seen_run INTEGER NOT NULL,missing_streak INTEGER NOT NULL DEFAULT 0,last_missing_run INTEGER,
              PRIMARY KEY(search_url,property_id))''',
            '''CREATE TABLE price_changes (
              id INTEGER PRIMARY KEY,run_id INTEGER NOT NULL,property_id TEXT NOT NULL,
              previous_price_json TEXT NOT NULL,new_price_json TEXT NOT NULL,detected_at TEXT NOT NULL,
              source TEXT NOT NULL,verification TEXT NOT NULL,detail_price_json TEXT,
              UNIQUE(run_id,property_id))''',
        ):
            db.execute(statement)
        for run_id, run in runs.items():
            # No se calculan retirados de manera retroactiva durante la migración.
            db.execute('INSERT INTO run_searches VALUES(?,?,?,?,?,1)',
                       (run_id,search_identity(run['url']),run['url'],run['listing_complete'],run['advertised_json']))
        for row in old_pages:
            for item in json.loads(row['links_json']):
                self._observe(db,row['run_id'],search_identity(runs[row['run_id']]['url']),item,row['visited'])
        db.execute('PRAGMA user_version=1')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        try:
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def new_run(self, url, config):
        with self.connect() as db:
            run_id = db.execute('INSERT INTO runs(url,started,status,config_json) VALUES(?,?,?,?)',
                                (url, now(), 'running', dumps(config))).lastrowid
            for source in config.get('urls') or [url]:
                db.execute('INSERT OR IGNORE INTO run_searches(run_id,search_url,source_url) VALUES(?,?,?)',
                           (run_id,search_identity(source),source))
            return run_id

    def run(self, run_id):
        with self.connect() as db:
            row = db.execute('SELECT * FROM runs WHERE id=?', (run_id,)).fetchone()
            if not row:
                raise ValueError(f'Ejecución inexistente: {run_id}')
            return dict(row)

    def update_run(self, run_id, **values):
        allowed = {'finished', 'status', 'advertised_json', 'listing_complete'}
        if not values.keys() <= allowed:
            raise ValueError('Columna no permitida')
        with self.connect() as db:
            db.execute('UPDATE runs SET '+','.join(f'{k}=?' for k in values)+' WHERE id=?',
                       (*values.values(), run_id))

    def event(self, run_id, kind, context, level='info'):
        with self.connect() as db:
            db.execute('INSERT INTO events(run_id,time,level,kind,context_json) VALUES(?,?,?,?,?)',
                       (run_id, now(), level, kind, dumps(context)))

    def pages(self, run_id, search_url=None):
        with self.connect() as db:
            query = 'SELECT * FROM pages WHERE run_id=?'
            args = [run_id]
            if search_url is not None:
                query += ' AND search_url=?'
                args.append(search_identity(search_url))
            return [dict(r) for r in db.execute(query+' ORDER BY search_url,number',args)]

    def save_page(self, run_id, number, active, url, fingerprint, links, next_action, search_url=None):
        # Página, procedencias y cola se confirman en una única transacción.
        with self.connect() as db:
            search_url = search_identity(search_url or db.execute('SELECT url FROM runs WHERE id=?',(run_id,)).fetchone()[0])
            visited = now()
            db.execute('INSERT INTO pages VALUES(?,?,?,?,?,?,?,?,?)',
                       (run_id, search_url, number, active, url, fingerprint, dumps(links), dumps(next_action), visited))
            for item in links:
                db.execute('INSERT INTO properties(id,url) VALUES(?,?) ON CONFLICT(id) DO NOTHING',
                           (item['id'], item['url']))
                db.execute('INSERT OR IGNORE INTO appearances VALUES(?,?,?,?,?)',
                           (run_id, search_url, number, item['id'], item['url']))
                db.execute('INSERT OR IGNORE INTO jobs(run_id,property_id) VALUES(?,?)', (run_id, item['id']))
                self._observe(db,run_id,search_url,item,visited)

    def _observe(self, db, run_id, search_url, item, verified_at):
        config = json.loads(db.execute('SELECT config_json FROM runs WHERE id=?',(run_id,)).fetchone()[0])
        observed = listing_price(item, config.get('listing_currency'))
        previous = db.execute('SELECT price_json,conflict FROM listing_observations WHERE run_id=? AND search_url=? AND property_id=?',
                              (run_id,search_url,item['id'])).fetchone()
        old_price = json.loads(previous['price_json']) if previous else None
        differs = (not same_price(old_price,observed) if old_price and
                   old_price.get('status') == observed.get('status') == 'valid' else old_price != observed)
        conflict = bool(previous and (previous['conflict'] or differs))
        db.execute('''INSERT INTO listing_observations VALUES(?,?,?,?,?,?)
          ON CONFLICT(run_id,search_url,property_id) DO UPDATE SET conflict=excluded.conflict,verified_at=excluded.verified_at''',
                   (run_id,search_url,item['id'],dumps(observed),int(conflict),verified_at))
        membership = db.execute('SELECT state FROM search_memberships WHERE search_url=? AND property_id=?',(search_url,item['id'])).fetchone()
        db.execute('''INSERT INTO search_memberships(search_url,property_id,first_seen,last_verified_at,last_seen_run)
          VALUES(?,?,?,?,?) ON CONFLICT(search_url,property_id) DO UPDATE SET state='active',
          last_verified_at=excluded.last_verified_at,last_seen_run=max(last_seen_run,excluded.last_seen_run),missing_streak=0,last_missing_run=NULL''',
                   (search_url,item['id'],verified_at,verified_at,run_id))
        if membership and membership['state'] != 'active':
            db.execute('INSERT INTO events(run_id,time,level,kind,context_json) VALUES(?,?,?,?,?)',
                       (run_id,verified_at,'info','availability_changed',dumps({'id':item['id'],'search_url':search_url,
                        'previous':membership['state'],'state':'active'})))

    def searches(self, run_id):
        with self.connect() as db:
            return [dict(r) for r in db.execute('SELECT * FROM run_searches WHERE run_id=? ORDER BY search_url',(run_id,))]

    def update_search(self, run_id, search_url, *, advertised=None, complete=False):
        search_url = search_identity(search_url)
        with self.connect() as db:
            if advertised is not None:
                db.execute('UPDATE run_searches SET advertised_json=? WHERE run_id=? AND search_url=?',
                           (dumps(advertised),run_id,search_url))
            if complete:
                db.execute('UPDATE run_searches SET listing_complete=1 WHERE run_id=? AND search_url=?',(run_id,search_url))
            rows = db.execute('SELECT * FROM run_searches WHERE run_id=?',(run_id,)).fetchall()
            totals = (json.loads(rows[0]['advertised_json']) if len(rows)==1 and rows[0]['advertised_json'] else
                      {'searches':[{'url':r['source_url'],'totals':json.loads(r['advertised_json']) if r['advertised_json'] else None} for r in rows]})
            db.execute('UPDATE runs SET listing_complete=?,advertised_json=? WHERE id=?',
                       (int(bool(rows) and all(r['listing_complete'] for r in rows)),dumps(totals),run_id))

    def plan_incremental(self, run_id):
        """Decide una sola cola global después de recopilar todas las búsquedas."""
        with self.connect() as db:
            config = json.loads(db.execute('SELECT config_json FROM runs WHERE id=?',(run_id,)).fetchone()[0])
            fallback = config.get('listing_currency')
            jobs = db.execute('''SELECT j.*,p.data_json catalog_json,p.needs_refresh FROM jobs j
              JOIN properties p ON p.id=j.property_id WHERE run_id=?''',(run_id,)).fetchall()
            for job in jobs:
                if job['status'] in ('success','partial') and job['classification']:
                    continue
                observations = db.execute('SELECT * FROM listing_observations WHERE run_id=? AND property_id=?',
                                          (run_id,job['property_id'])).fetchall()
                values = [json.loads(o['price_json']) for o in observations]
                observed = values[0] if values else {'status':'uncomparable','reason':'no_observation'}
                conflict = any(o['conflict'] for o in observations) or any(not same_price(observed,v) for v in values[1:])
                catalog = json.loads(job['catalog_json']) if job['catalog_json'] else None
                previous = json.loads(job['previous_price_json']) if job['previous_price_json'] else detail_price(catalog,fallback)
                quality = (catalog or {}).get('quality','success')
                if catalog is None:
                    classification, reason = 'new', 'no_catalog_detail'
                elif conflict:
                    classification, reason = 'review', 'conflicting_listing_prices'
                elif job['needs_refresh'] or quality != 'success':
                    classification, reason = 'review', 'previous_detail_incomplete_or_failed'
                elif (catalog.get('normalized') or {}).get('price') is None and previous.get('status')=='valid':
                    classification, reason = 'review', 'repair_legacy_price_normalization'
                elif not comparable(observed,previous):
                    classification, reason = 'review', 'price_not_comparable'
                elif same_price(observed,previous):
                    classification, reason = 'unchanged', 'same_comparable_price'
                else:
                    classification, reason = 'modified', 'price_changed'
                status = 'unchanged' if classification == 'unchanged' else (
                    'pending' if job['status']=='unchanged' else job['status'])
                db.execute('''UPDATE jobs SET classification=?,decision_reason=?,listing_price_json=?,previous_price_json=?,
                  status=?,data_json=CASE WHEN ?='unchanged' THEN ? ELSE data_json END WHERE run_id=? AND property_id=?''',
                           (classification,reason,dumps(observed),dumps(previous),status,classification,
                            job['catalog_json'],run_id,job['property_id']))
                if classification == 'modified':
                    db.execute('''INSERT OR IGNORE INTO price_changes(run_id,property_id,previous_price_json,new_price_json,detected_at,source,verification)
                      VALUES(?,?,?,?,?,'listing','pending')''',
                               (run_id,job['property_id'],dumps(previous),dumps(observed),now()))

    def validate_detail_price(self, run_id, property_id, data):
        with self.connect() as db:
            job = db.execute('SELECT listing_price_json FROM jobs WHERE run_id=? AND property_id=?',(run_id,property_id)).fetchone()
            config = json.loads(db.execute('SELECT config_json FROM runs WHERE id=?',(run_id,)).fetchone()[0])
        expected = json.loads(job[0]) if job and job[0] else {}
        actual = detail_price(data,config.get('listing_currency'))
        if expected.get('status') == 'valid' and not same_price(expected,actual):
            data['quality'] = 'partial'
            data.setdefault('errors',[]).append({'field':'price','error':'Listado y ficha difieren o no son comparables',
                                               'listing':expected,'detail':actual})
        return data

    def finalize_absences(self, run_id):
        """Sólo confirma ausencias con un recorrido completo y todas las fichas fiables."""
        with self.connect() as db:
            run = db.execute('SELECT * FROM runs WHERE id=?',(run_id,)).fetchone()
            unsafe = db.execute("SELECT count(*) FROM jobs WHERE run_id=? AND status NOT IN ('success','unchanged')",(run_id,)).fetchone()[0]
            unsafe += db.execute("SELECT count(*) FROM jobs WHERE run_id=? AND decision_reason='conflicting_listing_prices'",(run_id,)).fetchone()[0]
            unsafe += db.execute('SELECT count(*) FROM listing_observations WHERE run_id=? AND conflict=1',(run_id,)).fetchone()[0]
            searches = db.execute('SELECT * FROM run_searches WHERE run_id=?',(run_id,)).fetchall()
            if run['status'] != 'completed' or not run['listing_complete'] or unsafe or not searches or not all(s['listing_complete'] for s in searches):
                return False
            for search in searches:
                if search['absence_applied']:
                    continue
                missing = db.execute('''SELECT property_id,state,missing_streak FROM search_memberships
                  WHERE search_url=? AND last_seen_run<? AND (last_missing_run IS NULL OR last_missing_run<?)
                  AND property_id NOT IN (SELECT property_id FROM listing_observations WHERE run_id=? AND search_url=?)''',
                                     (search['search_url'],run_id,run_id,run_id,search['search_url'])).fetchall()
                # Una ejecución antigua reanudada no puede retirar un anuncio visto después.
                db.execute('''UPDATE search_memberships SET missing_streak=missing_streak+1,
                  state=CASE WHEN missing_streak+1>=2 THEN 'removed' ELSE 'possibly_removed' END,last_missing_run=?
                  WHERE search_url=? AND last_seen_run<? AND (last_missing_run IS NULL OR last_missing_run<?)
                  AND property_id NOT IN (SELECT property_id FROM listing_observations WHERE run_id=? AND search_url=?)''',
                           (run_id,search['search_url'],run_id,run_id,run_id,search['search_url']))
                for item in missing:
                    state = 'removed' if item['missing_streak']+1>=2 else 'possibly_removed'
                    if state != item['state']:
                        db.execute('INSERT INTO events(run_id,time,level,kind,context_json) VALUES(?,?,?,?,?)',
                                   (run_id,now(),'info','availability_changed',dumps({'id':item['property_id'],
                                    'search_url':search['search_url'],'previous':item['state'],'state':state})))
                db.execute('UPDATE run_searches SET absence_applied=1 WHERE run_id=? AND search_url=?',(run_id,search['search_url']))
            return True

    def pending(self, run_id, attempts):
        with self.connect() as db:
            return [dict(r) for r in db.execute('''SELECT j.*,p.url FROM jobs j JOIN properties p
              ON p.id=j.property_id WHERE j.run_id=? AND j.status NOT IN ('success','unchanged')
              AND j.attempts < ? ORDER BY j.property_id''', (run_id, attempts))]

    def attempt(self, run_id, property_id):
        with self.connect() as db:
            db.execute("UPDATE jobs SET attempts=attempts+1,status='processing',updated=? WHERE run_id=? AND property_id=?",
                       (now(), run_id, property_id))

    def result(self, run_id, property_id, status, data=None, error=None):
        with self.connect() as db:
            db.execute('UPDATE jobs SET status=?,data_json=?,error=?,updated=? WHERE run_id=? AND property_id=?',
                       (status, dumps(data) if data is not None else None, error, now(), run_id, property_id))
            if data is not None:
                n = data['normalized']
                # Una ficha parcial no borra el último catálogo completo y fiable.
                db.execute('''UPDATE properties SET data_json=?,title=?,price=?,city=?,property_type=?,updated=?,needs_refresh=?
                  WHERE id=? AND (?='success' OR data_json IS NULL)''',
                           (dumps(data),n.get('title'),n.get('price'),n.get('city'),n.get('property_type'),now(),
                            int(status!='success'),property_id,status))
                if status != 'success':
                    db.execute('UPDATE properties SET needs_refresh=1 WHERE id=?',(property_id,))
                config = json.loads(db.execute('SELECT config_json FROM runs WHERE id=?',(run_id,)).fetchone()[0])
                actual = detail_price(data,config.get('listing_currency'))
                job = db.execute('SELECT previous_price_json,listing_price_json FROM jobs WHERE run_id=? AND property_id=?',
                                 (run_id,property_id)).fetchone()
                previous = json.loads(job['previous_price_json']) if job and job['previous_price_json'] else {}
                if comparable(previous,actual) and not same_price(previous,actual):
                    db.execute('''INSERT OR IGNORE INTO price_changes(run_id,property_id,previous_price_json,new_price_json,detected_at,source,verification)
                      VALUES(?,?,?,?,?,'detail','pending')''',
                               (run_id,property_id,dumps(previous),dumps(actual),now()))
                change = db.execute('SELECT new_price_json FROM price_changes WHERE run_id=? AND property_id=?',(run_id,property_id)).fetchone()
                if change:
                    match = same_price(json.loads(change[0]),actual)
                    verification = ('confirmed' if status=='success' else 'price_confirmed_partial_detail') if match else 'disagreement_or_uncomparable'
                    db.execute('UPDATE price_changes SET verification=?,detail_price_json=? WHERE run_id=? AND property_id=?',
                               (verification,dumps(actual),run_id,property_id))
            elif status in ('failed','blocked'):
                db.execute('UPDATE properties SET needs_refresh=1 WHERE id=?',(property_id,))
                db.execute("UPDATE price_changes SET verification='detail_failed' WHERE run_id=? AND property_id=?",(run_id,property_id))

    def summary(self, run_id):
        run = self.run(run_id)
        with self.connect() as db:
            counts = {r['status']: r['n'] for r in db.execute(
                'SELECT status,count(*) n FROM jobs WHERE run_id=? GROUP BY status', (run_id,))}
            pages = db.execute('SELECT count(*) FROM pages WHERE run_id=?', (run_id,)).fetchone()[0]
            appearances = db.execute('SELECT count(*) FROM appearances WHERE run_id=?', (run_id,)).fetchone()[0]
            retries = db.execute('SELECT coalesce(sum(max(attempts-1,0)),0) FROM jobs WHERE run_id=?', (run_id,)).fetchone()[0]
            classifications = {r[0] or 'unclassified':r[1] for r in db.execute(
                'SELECT classification,count(*) FROM jobs WHERE run_id=? GROUP BY classification',(run_id,))}
            lifecycle = {r[0]:r[1] for r in db.execute('''SELECT state,count(*) FROM search_memberships
              WHERE search_url IN (SELECT search_url FROM run_searches WHERE run_id=?) GROUP BY state''',(run_id,))}
            conflicts = db.execute('''SELECT count(*) FROM jobs WHERE run_id=? AND
              (decision_reason='conflicting_listing_prices' OR property_id IN
               (SELECT property_id FROM listing_observations WHERE run_id=? AND conflict=1))''',(run_id,run_id)).fetchone()[0]
        return {**run, 'pages': pages, 'unique': sum(counts.values()), 'statuses': counts,
                'duplicates': appearances-sum(counts.values()), 'retries': retries,
                'classifications':classifications,'search_states':lifecycle,'searches':self.searches(run_id),
                'listing_conflicts':conflicts}

    def catalog(self, *, state=None, search_url=None, limit=100, offset=0):
        with self.connect() as db:
            condition = 'WHERE m.search_url=?' if search_url else ''
            params = [search_identity(search_url)] if search_url else []
            query = '''SELECT p.id,p.url,p.title,p.price,p.city,p.property_type,p.needs_refresh,
              max(m.last_verified_at) last_verified_at,
              CASE WHEN sum(m.state='active')>0 THEN 'active'
                   WHEN sum(m.state='possibly_removed')>0 THEN 'possibly_removed' ELSE 'removed' END state
              FROM properties p JOIN search_memberships m ON m.property_id=p.id '''+condition+' GROUP BY p.id'
            if state:
                query = 'SELECT * FROM ('+query+') WHERE state=?'
                params.append(state)
            total = db.execute('SELECT count(*) FROM ('+query+')',params).fetchone()[0]
            rows = [dict(r) for r in db.execute(query+' ORDER BY id LIMIT ? OFFSET ?',(*params,limit,offset))]
            return {'total':total,'items':rows,'limit':limit,'offset':offset}
