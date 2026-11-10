"""CLI local de Fincaraíz; configuración auxiliar y motor común."""
import argparse
import asyncio
import json
import os
from pathlib import Path
from metro.paths import DEFAULT_DB
from catalogo.persistencia.busquedas import BusquedasSQLite
from wasi.locking import bloqueo
from .browser import verificar
from .scraper import FincaraizConfig, FincaraizScraper, FincaraizStore


def configuracion(repo, db, *, ids=None, **kwargs):
    searches = {b['id_busqueda']: repo.configuracion_fincaraiz(b['id_busqueda']) for b in repo.listar()
                if b['fuente'] == 'fincaraiz' and b.get('activa', True)}
    if ids:
        if kwargs.get('resume') or any(i not in searches for i in ids):
            raise ValueError('--search requiere búsquedas activas y no se combina con --resume')
        searches = {k: searches[k] for k in dict.fromkeys(ids)}
    if any(c is None for c in searches.values()):
        raise ValueError('Búsqueda sin configuración verificada')
    urls = list(searches)
    return FincaraizConfig(db=str(db), url=urls[0] if urls else 'resume', urls=urls, searches=searches, **kwargs)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db'); parser.add_argument('--crm')
    sub = parser.add_subparsers(dest='command', required=True)
    r = sub.add_parser('register'); r.add_argument('--url', required=True); r.add_argument('--name', required=True)
    r.add_argument('--replace')
    s = sub.add_parser('scrape'); s.add_argument('--search', action='append'); s.add_argument('--resume', type=int)
    s.add_argument('--headed', action='store_true'); s.add_argument('--max-pages', type=int); s.add_argument('--max-details', type=int)
    st = sub.add_parser('status'); st.add_argument('run', type=int)
    args = parser.parse_args()
    metro = Path(os.getenv('METRO_DB', str(DEFAULT_DB))).resolve()
    db = Path(args.db or os.getenv('FINCARAIZ_DB', str(metro.with_name('fincaraiz.sqlite')))).resolve()
    crm = Path(args.crm or os.getenv('RADAR_CRM_DB', str(metro.with_name(metro.stem + '-consola.sqlite')))).resolve()
    wasi = Path(os.getenv('WASI_DB', str(metro.with_name('wasi.sqlite')))).resolve()
    if len({metro, db, crm, wasi}) != 4:
        parser.error('Las bases de fuentes y la auxiliar deben ser distintas')
    os.environ.update(FINCARAIZ_DB=str(db), RADAR_CRM_DB=str(crm))
    repo = BusquedasSQLite(crm)
    if args.command == 'register':
        c = asyncio.run(verificar(args.url))
        print(json.dumps({'id': repo.guardar_fincaraiz(args.name, c, args.replace)}, ensure_ascii=False)); return
    if args.command == 'status':
        if not db.is_file():
            parser.error('No existe la base Fincaraíz')
        print(json.dumps(FincaraizStore(db).summary(args.run), ensure_ascii=False, indent=2)); return
    config = configuracion(repo, db, ids=args.search, resume=args.resume, headed=args.headed,
                           max_pages=args.max_pages, max_details=args.max_details)
    config.validate()
    with bloqueo(db):
        result = asyncio.run(FincaraizScraper(config).run())
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result['status'] != 'completed':
        raise SystemExit(2)


if __name__ == '__main__':
    main()
