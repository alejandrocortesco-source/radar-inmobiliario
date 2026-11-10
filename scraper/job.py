"""Proceso de Cloud Run Job/local; no importa FastAPI ni inicia un servidor."""
import argparse
import asyncio
import json
import os
import signal
from contextlib import ExitStack
from pathlib import Path

from metro import paths
from metro.scraper import Scraper, Config
from wasi.scraper import WasiScraper
from fincaraiz.scraper import FincaraizScraper
from fincaraiz.__main__ import configuracion as configuracion_fincaraiz
from wasi.__main__ import configuracion
from wasi.locking import bloqueo
from wasi.durable import EstadoGCS
from catalogo.persistencia.busquedas import BusquedasSQLite


def horario(dias):
    dias = [d.strip().upper() for d in dias.split(',')]
    if len(dias) != 2 or len(set(dias)) != 2 or not set(dias) <= {'MON','TUE','WED','THU','FRI','SAT','SUN'}:
        raise ValueError('RADAR_DAYS requiere dos días distintos: MON,TUE,WED,THU,FRI,SAT,SUN')
    return {'schedule': '0 0 * * ' + ','.join(dias), 'timeZone': 'America/Bogota'}


async def ejecutar(carpeta, fuentes, resume_wasi=None, estado=None, resume_fincaraiz=None):
    metro, wasi, crm = [carpeta / nombre for nombre in ('metro.sqlite', 'wasi.sqlite', 'metro-consola.sqlite')]
    fincaraiz = carpeta / 'fincaraiz.sqlite'
    os.environ.update(FINCARAIZ_DB=str(fincaraiz), METRO_DB=str(metro), WASI_DB=str(wasi), RADAR_CRM_DB=str(crm))
    repo = BusquedasSQLite(crm)
    registradas = repo.listar()
    resultados = {}
    async def capturar():
        with ExitStack() as stack:
            for base in (metro, wasi, fincaraiz):
                stack.enter_context(bloqueo(base))
            if 'metrocuadrado' in fuentes:
                urls = [b['id_busqueda'] for b in registradas if b['fuente'] == 'metrocuadrado']
                if urls:
                    resultados['metrocuadrado'] = await Scraper(Config(db=str(metro), url=urls[0], urls=urls)).run()
            if 'wasi' in fuentes:
                config = configuracion(repo, wasi, resume=resume_wasi, concurrency=1)
                if config.searches or resume_wasi:
                    resultados['wasi'] = await WasiScraper(config).run()
            if 'fincaraiz' in fuentes:
                config = configuracion_fincaraiz(repo, fincaraiz, resume=resume_fincaraiz)
                if config.searches or resume_fincaraiz:
                    resultados['fincaraiz'] = await FincaraizScraper(config).run()
    task = asyncio.create_task(capturar())
    # Cloud Run envía SIGTERM antes de terminar. Conserva checkpoints al cancelar.
    anterior = signal.getsignal(signal.SIGTERM)
    signal.signal(signal.SIGTERM, lambda *_: task.cancel())
    try:
        if estado:
            while not task.done():
                done, _ = await asyncio.wait({task}, timeout=60)
                if not done:
                    await asyncio.to_thread(estado.guardar, carpeta)
        await task
    finally:
        if not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        signal.signal(signal.SIGTERM, anterior)
    if not resultados:
        raise ValueError('No hay búsquedas registradas de las fuentes solicitadas')
    return resultados


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', default=os.getenv('RADAR_DATA_DIR', str(paths.DEFAULT_DB.parent)))
    parser.add_argument('--source', choices=('all', 'metrocuadrado', 'wasi', 'fincaraiz'), default='all')
    parser.add_argument('--resume-wasi', type=int)
    parser.add_argument('--resume-fincaraiz', type=int)
    parser.add_argument('--schedule', action='store_true', help='Imprimir horario propuesto; no crea Scheduler')
    parser.add_argument('--initialize-state', action='store_true', help='Subir bases locales al objeto durable si aún no existe')
    args = parser.parse_args()
    try:
        if args.schedule:
            print(json.dumps(horario(os.getenv('RADAR_DAYS', 'MON,THU'))))
            return
        carpeta = Path(args.data_dir).resolve()
        carpeta.mkdir(parents=True, exist_ok=True)
        fuentes = ('metrocuadrado', 'wasi', 'fincaraiz') if args.source == 'all' else (args.source,)
        bucket = os.getenv('RADAR_STATE_BUCKET')
        if os.getenv('CLOUD_RUN_JOB') and not bucket:
            raise ValueError('Cloud Run requiere RADAR_STATE_BUCKET; no se usará disco efímero como persistencia')
        with ExitStack() as stack:
            stack.enter_context(bloqueo(carpeta / 'radar-state'))
            estado = stack.enter_context(EstadoGCS(bucket, os.getenv('RADAR_STATE_OBJECT', 'radar/state.tar.gz'))) if bucket else None
            if args.initialize_state:
                if not estado or not (carpeta / 'metro-consola.sqlite').is_file():
                    raise ValueError('Inicializar requiere bucket y configuración auxiliar local')
                estado.guardar(carpeta)  # generation=0; nunca sobrescribe un estado existente.
                print('{"state":"initialized"}')
                return
            if estado:
                estado.cargar(carpeta)
            try:
                resultado = asyncio.run(ejecutar(carpeta, fuentes, args.resume_wasi, estado, args.resume_fincaraiz))
            finally:
                if estado:
                    estado.guardar(carpeta)
            # No imprimir config_json ni documentos/contactos en logs del Job.
            print(json.dumps({f: {k: r[k] for k in ('id','status','pages','unique','statuses','classifications','retries','details_opened','details_reused','errors','error_events')} for f, r in resultado.items()}))
            if any(r['status'] != 'completed' for r in resultado.values()):
                raise SystemExit(2)
    except Exception as exc:
        # Los SDK pueden incluir cabeceras/URLs en sus errores; solo tipo y estado.
        print(json.dumps({'status': 'job_failed', 'error_type': type(exc).__name__}))
        raise SystemExit(2) from None


if __name__ == '__main__':
    main()
