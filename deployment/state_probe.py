"""Comprobación manual: sin scraping ni Gemini. Limpieza solo de marcador propio."""
import argparse
import asyncio
import json
import os
import sqlite3
import tempfile
from contextlib import closing
from pathlib import Path
from uuid import UUID
from wasi.durable import ARCHIVOS, EstadoGCS

MARKER = 'RADAR_CLOUD_TEST_20261111'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--client')
    parser.add_argument('--cleanup', action='store_true')
    parser.add_argument('--browser', action='store_true')
    args = parser.parse_args()
    if args.cleanup and not args.client:
        raise ValueError('Limpieza requiere UUID exacto')
    if args.client:
        args.client = str(UUID(args.client))
    root = Path(os.environ.get('RADAR_DATA_DIR', '/data'))
    root.mkdir(parents=True, exist_ok=True)
    with EstadoGCS(os.environ['RADAR_STATE_BUCKET'], os.getenv('RADAR_STATE_OBJECT', 'radar/state.tar.gz')) as state:
        with tempfile.TemporaryDirectory(dir=root) as folder:
            state.cargar(folder)
            checked = []
            for name in ARCHIVOS:
                path = Path(folder) / name
                if path.exists():
                    with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)) as db:
                        if [r[0] for r in db.execute('PRAGMA integrity_check')] != ['ok']:
                            raise ValueError('Integridad no confirmada')
                    checked.append(name)
            report = {'status': 'ok', 'integrity': checked, 'scraping': False, 'gemini': False}
            crm = Path(folder) / 'metro-consola.sqlite'
            if args.client:
                with closing(sqlite3.connect(crm)) as db, db:
                    db.execute('PRAGMA foreign_keys=ON')
                    row = db.execute('SELECT nombre FROM consola_clientes WHERE id=?', (args.client,)).fetchone()
                    if not row or row[0] != MARKER:
                        raise ValueError('UUID no corresponde al marcador sintético de esta validación')
                    opportunities = [r[0] for r in db.execute('SELECT id FROM consola_oportunidades WHERE cliente_id=?', (args.client,))]
                    report.update(client=args.client, synthetic_verified=True, opportunities=len(opportunities))
                    if args.cleanup:
                        for table, in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'radar_%'").fetchall():
                            # Nombres proceden de SQLite, escapados como identificadores.
                            quoted = '"' + table.replace('"', '""') + '"'
                            columns = {r[1] for r in db.execute('PRAGMA table_info(' + quoted + ')')}
                            if 'oportunidad' in columns:
                                db.executemany('DELETE FROM ' + quoted + ' WHERE oportunidad=?', [(o,) for o in opportunities])
                            if 'cliente' in columns:
                                db.execute('DELETE FROM ' + quoted + ' WHERE cliente=?', (args.client,))
                        db.execute('DELETE FROM consola_oportunidades WHERE cliente_id=?', (args.client,))
                        db.execute('DELETE FROM consola_clientes WHERE id=? AND nombre=?', (args.client, MARKER))
                        if db.execute('PRAGMA foreign_key_check').fetchall():
                            raise ValueError('Relaciones no válidas después de limpieza')
                        report['cleaned'] = True
                if args.cleanup:
                    state.guardar(folder)
            if args.browser:
                from playwright.async_api import async_playwright
                async def browser_check():
                    async with async_playwright() as p:
                        browser = await p.chromium.launch(headless=True)
                        page = await browser.new_page()
                        await page.set_content('<h1>synthetic</h1>')
                        assert await page.locator('h1').inner_text() == 'synthetic'
                        await browser.close()
                asyncio.run(browser_check())
                report['chromium'] = 'ok'
            print(json.dumps(report))

if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(json.dumps({'status': 'failed', 'error_type': type(exc).__name__}))
        raise SystemExit(2) from None
