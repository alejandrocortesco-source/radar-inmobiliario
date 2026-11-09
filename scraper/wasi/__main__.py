import argparse
import asyncio
import json
import os
from pathlib import Path

from metro.paths import DEFAULT_DB
from catalogo.persistencia.busquedas import BusquedasSQLite
from catalogo.fuentes.wasi import GEO, configurar
from .scraper import WasiScraper, WasiConfig, WasiStore
from .options import actualizar_opciones
from .locking import bloqueo
from metro.extraction import Restricted


def rutas(db=None, crm=None):
    metro = Path(os.getenv('METRO_DB', str(DEFAULT_DB))).resolve()
    wasi = Path(db or os.getenv('WASI_DB', str(metro.with_name('wasi.sqlite')))).resolve()
    auxiliar = Path(crm or os.getenv('RADAR_CRM_DB', str(metro.with_name(metro.stem + '-consola.sqlite')))).resolve()
    if len({metro, wasi, auxiliar}) != 3:
        raise ValueError('METRO_DB, WASI_DB y RADAR_CRM_DB deben ser distintas')
    return metro, wasi, auxiliar


def configuracion(repo, db, *, ids=None, **kwargs):
    searches = {}
    for b in repo.listar():
        if b['fuente'] != 'wasi':
            continue
        c = repo.configuracion_wasi(b['id_busqueda'])
        if not c:
            raise ValueError('Búsqueda Wasi sin configuración estable')
        searches[b['id_busqueda']] = c
    if ids is not None:
        if kwargs.get('resume'):
            raise ValueError('--search no se combina con --resume: reanudar conserva las búsquedas originales')
        if not ids or any(i not in searches for i in ids):
            raise ValueError('La búsqueda Wasi solicitada no está registrada')
        searches = {i: searches[i] for i in dict.fromkeys(ids)}
    ids = list(searches)
    return WasiConfig(db=str(db), searches=searches, url=ids[0] if ids else 'wasi:resume', urls=ids, **kwargs)




def main():
    parser = argparse.ArgumentParser(description='Wasi incremental, sin iniciar FastAPI')
    parser.add_argument('--db')
    parser.add_argument('--crm')
    sub = parser.add_subparsers(dest='command', required=True)
    scrape = sub.add_parser('scrape')
    scrape.add_argument('--resume', type=int)
    scrape.add_argument('--search', action='append', help='Ejecutar solo este ID de búsqueda registrada; repetir para varias')
    scrape.add_argument('--headed', action='store_true')
    scrape.add_argument('--retries', type=int, default=2)
    scrape.add_argument('--timeout', type=int, default=45000)
    options = sub.add_parser('options', help='Actualizar opciones del portal, sin buscar ni capturar anuncios')
    options.add_argument('--parent', action='append', default=[], metavar='CONTROL=ID')
    options.add_argument('--headed', action='store_true')
    register = sub.add_parser('register', help='Registrar búsqueda desde filtros JSON sin navegar')
    register.add_argument('--name', required=True)
    register.add_argument('--filters', required=True, help='Archivo JSON de filtros; sin credenciales')
    register.add_argument('--replace')
    status = sub.add_parser('status')
    status.add_argument('run', type=int)
    args = parser.parse_args()
    try:
        metro, db, crm = rutas(args.db, args.crm)
        os.environ['WASI_DB'], os.environ['RADAR_CRM_DB'] = str(db), str(crm)
        repo = BusquedasSQLite(crm)
        if args.command == 'register':
            config = configurar(json.loads(Path(args.filters).read_text(encoding='utf-8')), repo.opciones_wasi())
            print(json.dumps({'id': repo.guardar_wasi(args.name, config, args.replace)}, ensure_ascii=False))
            return
        if args.command == 'options':
            padres = dict(p.split('=', 1) for p in args.parent)
            if not set(padres) <= set(GEO):
                raise ValueError('Solo se admiten controles geográficos como padres')
            with bloqueo(db):
                print(json.dumps(asyncio.run(actualizar_opciones(repo, padres, args.headed))))
            return
        if args.command == 'status':
            if not db.exists():
                raise ValueError('No existe la base Wasi')
            print(json.dumps(WasiStore(db).summary(args.run), ensure_ascii=False, indent=2))
            return
        config = configuracion(repo, db, ids=args.search, resume=args.resume, headed=args.headed, retries=args.retries, timeout=args.timeout, concurrency=1)
        config.validate()
        with bloqueo(db):
            result = asyncio.run(WasiScraper(config).run())
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if result['status'] != 'completed':
            raise SystemExit(2)
    except (ValueError, OSError, Restricted) as exc:
        parser.exit(2, str(exc) + '\n')


if __name__ == '__main__':
    main()
