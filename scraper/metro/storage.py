import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from .paths import DEFAULT_DB


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
            return db.execute('INSERT INTO runs(url,started,status,config_json) VALUES(?,?,?,?)',
                              (url, now(), 'running', dumps(config))).lastrowid

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

    def pages(self, run_id):
        with self.connect() as db:
            return [dict(r) for r in db.execute('SELECT * FROM pages WHERE run_id=? ORDER BY number', (run_id,))]

    def save_page(self, run_id, number, active, url, fingerprint, links, next_action):
        # Página, procedencias y cola se confirman en una única transacción.
        with self.connect() as db:
            db.execute('INSERT INTO pages VALUES(?,?,?,?,?,?,?,?)',
                       (run_id, number, active, url, fingerprint, dumps(links), dumps(next_action), now()))
            for item in links:
                db.execute('INSERT INTO properties(id,url) VALUES(?,?) ON CONFLICT(id) DO NOTHING',
                           (item['id'], item['url']))
                db.execute('INSERT OR IGNORE INTO appearances VALUES(?,?,?,?)',
                           (run_id, number, item['id'], item['url']))
                db.execute('INSERT OR IGNORE INTO jobs(run_id,property_id) VALUES(?,?)', (run_id, item['id']))

    def pending(self, run_id, attempts):
        with self.connect() as db:
            return [dict(r) for r in db.execute('''SELECT j.*,p.url FROM jobs j JOIN properties p
              ON p.id=j.property_id WHERE j.run_id=? AND j.status NOT IN ('success','partial')
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
                db.execute('''UPDATE properties SET data_json=?,title=?,price=?,city=?,property_type=?,updated=?
                  WHERE id=?''', (dumps(data), n.get('title'), n.get('price'), n.get('city'),
                                  n.get('property_type'), now(), property_id))

    def summary(self, run_id):
        run = self.run(run_id)
        with self.connect() as db:
            counts = {r['status']: r['n'] for r in db.execute(
                'SELECT status,count(*) n FROM jobs WHERE run_id=? GROUP BY status', (run_id,))}
            pages = db.execute('SELECT count(*) FROM pages WHERE run_id=?', (run_id,)).fetchone()[0]
            appearances = db.execute('SELECT count(*) FROM appearances WHERE run_id=?', (run_id,)).fetchone()[0]
            retries = db.execute('SELECT coalesce(sum(max(attempts-1,0)),0) FROM jobs WHERE run_id=?', (run_id,)).fetchone()[0]
        return {**run, 'pages': pages, 'unique': sum(counts.values()), 'statuses': counts,
                'duplicates': appearances-sum(counts.values()), 'retries': retries}
