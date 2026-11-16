"""Demostración local aislada. Requiere las dependencias de desarrollo existentes.

Siempre crea .tmp/programaciones-demo-UUID. No usa ADC ni servicios cloud reales.
"""
import argparse
import ipaddress
import os
from pathlib import Path
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT/'scraper'), str(ROOT/'consola/tests')]


def block_external(event, args):
    if event == 'subprocess.Popen':
        raise PermissionError('La demostración no admite subprocesos.')
    if event == 'socket.connect':
        try:
            local = ipaddress.ip_address(args[1][0]).is_loopback
        except (ValueError, TypeError, IndexError):
            local = False
        if not local:
            raise PermissionError('Red externa deshabilitada en la demostración.')


def prepare():
    import pytest
    from test_ejecuciones import execution, A, B
    from test_programacion import FakeScheduler
    from ejecuciones.calendarios import Calendarios
    from metro.web import app
    patch = pytest.MonkeyPatch()
    for key in ('K_SERVICE','K_REVISION','K_CONFIGURATION','CLOUD_RUN_JOB'):
        patch.delenv(key, raising=False)
    patch.setenv('RADAR_AUTH_MODE','local')
    patch.setenv('RADAR_SCHEDULE_TARGET','https://synthetic.run.app')
    folder = ROOT/'.tmp'/('programaciones-demo-'+uuid4().hex)
    folder.mkdir(parents=True)
    fixture = execution.__wrapped__(folder, patch)
    service = fixture[0]
    from selector_fixtures import seed_searches
    from catalogo.persistencia.busquedas import BusquedasSQLite
    with fixture[3]() as state:
        state.cargar(folder/'selector-seed')
        seed_searches(BusquedasSQLite(folder/'selector-seed'/'metro-consola.sqlite'))
        state.guardar(folder/'selector-seed')
    service.overview(refresh=True)
    scheduler = FakeScheduler()
    patch.setattr('ejecuciones.scheduler.Scheduler',lambda:scheduler)
    multi = Calendarios(service,scheduler)
    for name,key,frequency,days,hour,enabled in [('Carolina · lunes',A,'weekly',[0],'9',True),('Norte · tardes',B,'daily',[],'18',False)]:
        multi.change('create',values=dict(name=name,keys=[['metrocuadrado',key]],frequency=frequency,days=days,hour=hour,minute='0',enabled=enabled))
    from fastapi import Request
    from starlette.responses import Response
    @app.middleware('http')
    async def demo_banner(request: Request, call_next):
        response = await call_next(request)
        if 'text/html' not in response.headers.get('content-type',''):
            return response
        content = b''.join([chunk async for chunk in response.body_iterator])
        banner = '<div role="note" style="padding:12px;background:#fff0ad;color:#332900">DEMOSTRACIÓN LOCAL · Datos sintéticos. No se ejecutan capturas externas ni servicios cloud.</div>'.encode()
        content = content.replace(b'<body>', b'<body>'+banner, 1)
        headers = dict(response.headers);headers.pop('content-length',None)
        return Response(content,status_code=response.status_code,headers=headers)
    return app, folder, patch


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',type=int,default=8770)
    args=parser.parse_args()
    sys.addaudithook(block_external)
    app,folder,patch=prepare()
    print('Datos aislados:',folder)
    print(f'Abrir http://127.0.0.1:{args.port}/v0.6/ejecuciones/programaciones')
    import uvicorn
    try:
        uvicorn.run(app,host='127.0.0.1',port=args.port,proxy_headers=False)
    finally:
        patch.undo()

if __name__=='__main__':
    main()
