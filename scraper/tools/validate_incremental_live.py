"""Prueba dos recorridos reales sobre una copia de SQLite; no altera el catálogo original."""
import asyncio
import json
from pathlib import Path
import sqlite3
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from metro.paths import DEFAULT_DB
from metro.scraper import Config, Scraper


async def main():
    target = DEFAULT_DB.parent/'incremental-validation.sqlite'
    if target.exists():
        raise RuntimeError(f'La base de validación ya existe: {target}')
    with sqlite3.connect(DEFAULT_DB.resolve().as_uri()+'?mode=ro',uri=True) as source:
        with sqlite3.connect(target) as destination:
            source.backup(destination)
    summaries = []
    for _ in range(2):
        summary = await Scraper(Config(db=str(target),delay=1,concurrency=2)).run()
        summaries.append(summary)
        print(json.dumps({'run':summary['id'],'status':summary['status'],
                          'classifications':summary['classifications'],'statuses':summary['statuses']},ensure_ascii=True),flush=True)
        if summary['status'] != 'completed':
            break
    out = DEFAULT_DB.parent/'verification/incremental-live.json'
    out.write_text(json.dumps(summaries,ensure_ascii=False,indent=2),encoding='utf-8')


if __name__ == '__main__':
    asyncio.run(main())
