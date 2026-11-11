"""Copiar archivos estables sin abrir SQLite ni escribir en el origen."""
import hashlib
import json
import shutil
import sqlite3
import sys
from pathlib import Path

from wasi.durable import ARCHIVOS, empaquetar


def sha(path):
    return hashlib.file_digest(path.open('rb'), 'sha256').hexdigest()


def main():
    source, dest = map(lambda p: Path(p).resolve(), sys.argv[1:3])
    if source == dest or source in dest.parents or dest.exists():
        raise ValueError('Destino independiente nuevo obligatorio')
    files = [source / n for n in ARCHIVOS if (source / n).is_file()]
    if not {'metro.sqlite', 'metro-consola.sqlite'} <= {p.name for p in files}:
        raise ValueError('Faltan bases principales')
    for p in files:
        for suffix in ('-wal', '-journal'):
            journal = p.with_name(p.name + suffix)
            if journal.exists() and journal.stat().st_size:
                raise ValueError('Hay una transacción o WAL activo; coordinar respaldo consistente antes de continuar')
    before = {p.name: sha(p) for p in files}
    dest.mkdir(parents=True)
    for p in files:
        shutil.copyfile(p, dest / p.name)
    after = {p.name: sha(p) for p in files}
    if before != after:
        raise ValueError('Fuente cambió durante la copia; no usar este respaldo')
    checks = {}
    for p in files:
        copy = dest / p.name
        if sha(copy) != before[p.name]:
            raise ValueError('Copia no idéntica')
        with sqlite3.connect(copy.as_uri() + '?immutable=1', uri=True) as db:
            integrity = [r[0] for r in db.execute('PRAGMA integrity_check')]
            if integrity != ['ok']:
                raise ValueError('Base copiada inválida')
            tables = [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")]
            counts = {t: db.execute('SELECT count(*) FROM "' + t.replace('"','""') + '"').fetchone()[0] for t in tables}
        checks[p.name] = dict(sha256=before[p.name], bytes=copy.stat().st_size, integrity='ok', tables=counts)
    bundle = dest.parent / (dest.name + '.tar.gz')
    bundle.write_bytes(empaquetar(dest))
    manifest = dict(source=str(source), backup=str(dest), files=checks, bundle=str(bundle), bundle_sha256=sha(bundle))
    (dest.parent / (dest.name + '-manifest.json')).write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    print(json.dumps(dict(files=len(checks), integrity='ok', source_unchanged=True, bundle_sha256=sha(bundle), compressed_bytes=bundle.stat().st_size)))

if __name__ == '__main__':
    main()
