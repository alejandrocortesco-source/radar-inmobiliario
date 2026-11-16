"""Informe histórico derivado del snapshot confirmado: sin lock, Store ni escrituras remotas."""
import copy
import sqlite3
import tarfile
import tempfile
import time
from threading import RLock
from collections import OrderedDict
from contextlib import closing
from pathlib import Path

from wasi.durable import ARCHIVOS
from .control import ACTIVE
from .resultados import from_db, valid, unavailable

FILES = {'metrocuadrado':'metro.sqlite', 'wasi':'wasi.sqlite', 'fincaraiz':'fincaraiz.sqlite'}


class SnapshotReports:
    cache = OrderedDict()  # Solo métricas, nunca tarballs ni datos de fichas.
    cache_lock = RLock()

    def __init__(self, state_factory, data_dir):
        self.state_factory = state_factory
        self.data_dir = Path(data_dir)

    def load(self, run):
        selected = tuple((b['fuente'], b.get('technical_run'), b['id_busqueda']) for b in run['searches'])
        generation = run.get('snapshot_generation')
        if (not run.get('persisted') or not str(generation).isdigit() or int(generation) <= 0 or
                any(source not in FILES or type(rid) is not int or rid < 1 or not isinstance(search,str) for source,rid,search in selected)):
            return [unavailable(b) for b in run['searches']]
        try:
            state = self.state_factory()
        except Exception:
            return [unavailable(b) for b in run['searches']]
        key = (getattr(state.bucket, 'name', id(state.bucket)), state.objeto, str(generation), selected)
        now = time.monotonic()
        with self.cache_lock:
            if key in self.cache and self.cache[key][0] > now:
                self.cache.move_to_end(key)
                return copy.deepcopy(self.cache[key][1])
        result = [unavailable(b) for b in run['searches']]
        complete = False
        try:
            if not run.get('persisted') or not str(generation).isdigit() or int(generation) <= 0:
                raise ValueError('Sin snapshot final confirmado')
            if any(source not in FILES or type(rid) is not int or rid < 1 for source,rid,_ in selected):
                raise ValueError('Sin referencia técnica')
            # Construir el adaptador no adquiere bloqueo. No llamar __enter__/cargar.
            blob = state.bucket.blob(state.objeto, generation=int(generation))
            self.data_dir.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(prefix='report-read-', dir=self.data_dir) as folder:
                root = Path(folder)
                archive = root/'snapshot.tar.gz'
                blob.download_to_filename(str(archive), if_generation_match=int(generation), timeout=30)
                with tarfile.open(archive, 'r:gz') as tar:
                    members = tar.getmembers()
                    if any(not m.isfile() or m.name not in ARCHIVOS for m in members) or len({m.name for m in members}) != len(members):
                        raise ValueError('Snapshot incompatible')
                    for filename in {FILES[source] for source,_,_ in selected}:
                        member = tar.getmember(filename)
                        (root/filename).write_bytes(tar.extractfile(member).read())
                for index,(source,rid,search) in enumerate(selected):
                    try:
                        with closing(sqlite3.connect((root/FILES[source]).as_uri()+'?mode=ro&immutable=1', uri=True)) as db:
                            db.execute('PRAGMA query_only=ON')
                            report = from_db(db, rid, search, source=source)
                        if run['searches'][index].get('processed') not in (None, report['processed']):
                            raise ValueError('El total no coincide con el cierre registrado')
                        result[index] = dict(report, report_origin='snapshot', report_generation=str(generation))
                    except (sqlite3.Error, ValueError, TypeError):
                        pass  # Un registro histórico incompatible no oculta los otros informes.
                complete = all(valid(r) for r in result)
        except Exception:
            pass  # No copiar excepciones del SDK/archivos a la interfaz o logs.
        with self.cache_lock:
            self.cache[key] = (now + (3600 if complete else 30), copy.deepcopy(result))
            self.cache.move_to_end(key)
            while len(self.cache) > 4:
                self.cache.popitem(last=False)
        return result


def project(doc, reader, requested=None):
    projected = copy.deepcopy(doc)
    ordered = sorted(projected['runs'], key=lambda r:r['created'], reverse=True)
    active = next((r for r in ordered if r['status'] in ACTIVE), None)
    run = next((r for r in ordered if r['id']==requested), None) if requested else (active or next(iter(ordered),None))
    if run and run['status'] not in ACTIVE and any(not valid(b) for b in run['searches']):
        reports = reader.load(run)
        for b,report in zip(run['searches'], reports):
            if not valid(b):
                original = {k:b.get(k) for k in ('processed','new','changed','unchanged')}
                b.update(report)
                if valid(report):
                    b.update(reported=original, report_note='Clasificación final derivada del snapshot confirmado; el registro original se conserva.')
    return projected
