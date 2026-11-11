"""Revisión supervisada: usa el catálogo común y el repositorio auxiliar."""
import sqlite3
from urllib.parse import parse_qs

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from oportunidades.api import proveedor_oportunidades
from oportunidades.persistencia import ErrorPersistencia
from catalogo.persistencia.asociaciones import AsociacionesSQLite, DecisionInvalida
from catalogo.persistencia.contrato import ErrorLecturaCatalogo


def crear_router(proveedor, templates):
    router = APIRouter(prefix='/v0.6/identificacion', include_in_schema=False)

    @router.get('')
    def revision(request: Request, vista: str = 'pendiente', pagina: int = 1,
                 a: str = '', b: str = '', catalogo=Depends(proveedor), s=Depends(proveedor_oportunidades)):
        if vista not in ('pendiente', 'confirmado', 'descartado', 'despues') or pagina < 1:
            raise HTTPException(422, 'Vista o página desconocida.')
        repo = AsociacionesSQLite(s.repositorio.ruta)
        try:
            items = catalogo.listar()
            por_id = {i.id_interno: i for i in items}
            filas = []
            no_disponibles = 0
            for par in repo.pares():
                if par['estado'] != ('pendiente' if vista == 'despues' else vista):
                    continue
                if par['a'] not in por_id or par['b'] not in por_id:
                    no_disponibles += 1
                    continue
                try:
                    revisada = repo.revisar(par['a'], par['b'], items)
                except DecisionInvalida:
                    no_disponibles += 1
                    continue
                actual = next(e for e in revisada['relaciones'] if (e['a'],e['b']) == (par['a'],par['b']))
                desactualizada = bool(par['firma_decision'] and par['firma_decision'] != actual['huella'])
                filas.append(par | {'actual': actual, 'revision': revisada, 'desactualizada': desactualizada,
                                    'diferida': par['fecha'] is not None and par['estado'] == 'pendiente'})
            if vista == 'despues':
                filas = [f for f in filas if f['diferida']]
            # Alertas primero; después similitud y desempate estable. Diferidos al final.
            filas.sort(key=lambda f: (not f['desactualizada'], f['diferida'], -f['actual']['puntuacion'], f['a'],f['b']))
            total = len(filas)
            pagina = min(pagina, max(1, (total+11)//12))
            filas = filas[(pagina-1)*12:pagina*12]
            return templates.TemplateResponse(request=request, name='identificacion06.html', context={
                'filas': filas, 'por_id': por_id, 'vista': vista, 'pagina': pagina, 'total': total,
                'paginas': max(1,(total+11)//12), 'no_disponibles': no_disponibles, 'ejecucion_id': repo.ejecucion()})
        except (ErrorPersistencia, ErrorLecturaCatalogo, OSError, sqlite3.Error) as exc:
            raise HTTPException(503, 'No se pudo abrir la revisión. Los anuncios se conservan.') from exc

    @router.post('/analizar')
    def analizar(catalogo=Depends(proveedor), s=Depends(proveedor_oportunidades)):
        try:
            AsociacionesSQLite(s.repositorio.ruta).analizar(catalogo.listar(), completo=True)
        except (ErrorPersistencia, ErrorLecturaCatalogo, OSError, sqlite3.Error) as exc:
            raise HTTPException(503, 'No se completó la identificación. Puedes reintentar; la captura se conserva.') from exc
        return RedirectResponse('/v0.6/identificacion', 303)

    @router.post('/decision')
    async def decidir(request: Request, catalogo=Depends(proveedor), s=Depends(proveedor_oportunidades)):
        datos = {k:v[-1] for k,v in parse_qs((await request.body()).decode()).items()}
        try:
            AsociacionesSQLite(s.repositorio.ruta).decidir(datos.get('a',''), datos.get('b',''),
                datos.get('accion',''), catalogo.listar(), datos.get('firma',''), datos.get('aceptar') == 'si')
        except DecisionInvalida as exc:
            return templates.TemplateResponse(request=request, name='error06.html', context={'mensaje': str(exc)}, status_code=409)
        except (ErrorPersistencia, ErrorLecturaCatalogo, OSError) as exc:
            raise HTTPException(503, 'No se pudo guardar la decisión. Vuelve a intentar.') from exc
        return RedirectResponse('/v0.6/identificacion?vista=' + ('confirmado' if datos.get('accion') == 'confirmado' else 'pendiente'), 303)

    return router
