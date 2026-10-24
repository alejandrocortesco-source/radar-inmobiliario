import argparse
import asyncio
import json
import logging
import os
from pathlib import Path

from .scraper import Config, Scraper, DEFAULT_URL
from .storage import Store
from .paths import DEFAULT_DB


def main():
    parser = argparse.ArgumentParser(description='Scraper público de Metrocuadrado')
    parser.add_argument('--db',default=os.getenv('METRO_DB',str(DEFAULT_DB)))
    sub = parser.add_subparsers(dest='command',required=True)
    scrape = sub.add_parser('scrape',help='Descubrir y procesar fichas sin servidor web')
    scrape.add_argument('--url',default=DEFAULT_URL)
    scrape.add_argument('--headed',action='store_true')
    scrape.add_argument('--concurrency',type=int,default=2)
    scrape.add_argument('--delay',type=float,default=1.5)
    scrape.add_argument('--timeout',type=int,default=45000,help='Milisegundos')
    scrape.add_argument('--retries',type=int,default=2)
    scrape.add_argument('--resume',type=int)
    scrape.add_argument('--max-pages',type=int,help='Límite explícito de prueba; ejecución incompleta')
    scrape.add_argument('--max-details',type=int,help='Límite explícito de prueba; ejecución incompleta')
    scrape.add_argument('--metrics-dir',help='Carpeta de CSV de recursos; predeterminado: metrics junto a SQLite')
    scrape.add_argument('--resource-interval',type=float,default=0.2,help='Segundos entre muestras de CPU/RAM (0.05–60)')
    show = sub.add_parser('status')
    show.add_argument('run',type=int)
    web = sub.add_parser('serve')
    web.add_argument('--port',type=int,default=int(os.getenv('PORT','8000')))
    web.add_argument('--host',default='127.0.0.1')
    args = vars(parser.parse_args())
    command = args.pop('command')
    if command == 'serve':
        os.environ['METRO_DB']=args['db']
        import uvicorn
        uvicorn.run('metro.web:app',host=args['host'],port=args['port'])
        return
    if command == 'status':
        print(json.dumps(Store(args['db']).summary(args['run']),ensure_ascii=False,indent=2))
        return
    Path(args['db']).parent.mkdir(parents=True,exist_ok=True)
    logging.basicConfig(level=logging.INFO,format='%(asctime)s %(levelname)s %(message)s',
                        handlers=[logging.FileHandler(Path(args['db']).parent/'scraper.log',encoding='utf-8'),logging.StreamHandler()])
    # El SO libera el bloqueo incluso si se interrumpe el proceso.
    with open(args['db']+'.lock','a+b') as lock:
        lock.seek(0)
        lock.write(b'0')
        lock.flush()
        lock.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(lock.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        except OSError:
            parser.exit(2,'Ya hay un scraper usando esta base de datos.\n')
        result = asyncio.run(Scraper(Config(**args)).run())
    print(json.dumps(result,ensure_ascii=False,indent=2))
    if result['status'] != 'completed':
        raise SystemExit(2)


if __name__ == '__main__':
    main()
