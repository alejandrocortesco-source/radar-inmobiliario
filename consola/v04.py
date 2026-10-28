"""Adaptador v0.4: mismas consultas y formularios, plantillas y rutas aisladas."""
from pathlib import Path
from urllib.parse import parse_qs, urlencode
from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from fastapi.templating import Jinja2Templates
from jinja2 import FileSystemLoader
from oportunidades.api import proveedor_oportunidades
from oportunidades.persistencia import ErrorPersistencia, NoEncontrado
from catalogo.persistencia.contrato import ErrorLecturaCatalogo
from .comentarios import Comentarios
from . import rutas

RAIZ = Path(__file__).parent
ESTATICOS = RAIZ / 'static' / 'v04'


def destino(url):
    return url.replace('/consola', '/v0.4').replace('%2Fconsola', '%2Fv0.4')


class Loader(FileSystemLoader):
    def get_source(self, environment, template):
        source, filename, uptodate = super().get_source(environment, template)
        return source.replace('/consola', '/v0.4'), filename, uptodate


URLS = {'url', 'volver', 'anterior', 'siguiente', 'primera', 'exportar', 'reintentar',
        'match_anterior', 'match_siguiente', 'match_form_action'}


def enlaces(contexto):
    """Solo cambia campos de navegación; nunca texto proveniente de los datos."""
    if isinstance(contexto, dict):
        salida = {}
        for k, v in contexto.items():
            if k in URLS and isinstance(v, str):
                salida[k] = destino(v)
            elif k == 'orden_url':
                salida[k] = lambda valor, f=v: destino(f(valor))
            elif k == 'match_limite_urls':
                salida[k] = {n: destino(u) for n, u in v.items()}
            else:
                salida[k] = enlaces(v)
        return salida
    if isinstance(contexto, (list, tuple)):
        return [enlaces(v) for v in contexto]
    return contexto


class Plantillas(Jinja2Templates):
    @staticmethod
    def contexto_captura(request, todos):
        from .oportunidades import contexto_captura
        return contexto_captura(request, todos, calcular=request.query_params.get('sin_buscar') != '1')

    @staticmethod
    def regreso_seguro(valor):
        from .presentacion import regreso_seguro
        return destino(regreso_seguro(valor.replace('/v0.4', '/consola') if valor else valor))

    def TemplateResponse(self, *, request, name, context, **kwargs):
        context = enlaces(context)
        context['v04'] = True
        context['panel'] = request.query_params.get('panel', '')
        context['sin_buscar'] = request.query_params.get('sin_buscar') == '1'
        oportunidad = context.get('oportunidad')
        if oportunidad:
            pares = [('match_orden' if k == 'orden' and 'matching_independiente' in context else k, v)
                     for k, v in request.query_params.multi_items() if k not in {'panel', 'oportunidad'}]
            context['editar_url'] = '/v0.4/?' + urlencode(pares + [('oportunidad', oportunidad.id), ('panel', 'editar')])
        if name == 'catalogo.html' and request.query_params.get('cliente'):
            context['panel'] = 'nueva'
        if name == 'captura.html':
            context['panel'] = 'editar'
        try:
            s = proveedor_oportunidades()
            repo = Comentarios(s.repositorio.ruta)
        except HTTPException:
            s, repo = None, None
        def comentario(identificador):
            try:
                return repo.leer(identificador) if repo else None
            except ErrorPersistencia:
                return None
        context['comentario'] = comentario
        if name == 'ficha.html':
            context['comentario_texto'] = comentario(context['inmueble'].id_interno)
            oid = request.query_params.get('oportunidad')
            if oid and s:
                # Evidencia producida por el motor existente para este inmueble.
                from oportunidades.matching import diagnosticar
                try:
                    informe = diagnosticar(s.oportunidad(oid).necesidades, [context['inmueble']])
                    context['evidencia'] = informe['resultados'][0] if informe['resultados'] else None
                except (NoEncontrado, ErrorPersistencia):
                    context['error_evidencia'] = 'No se pudo recuperar la oportunidad para consultar su evidencia.'
        return super().TemplateResponse(request=request, name=name, context=context, **kwargs)


class Ruta(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()
        async def atender(request):
            respuesta = await handler(request)
            if 'location' in respuesta.headers:
                url = destino(respuesta.headers['location'])
                if request.method == 'POST' and request.url.path == '/v0.4/oportunidades':
                    datos = parse_qs((await request.body()).decode(), keep_blank_values=True)
                    if datos.get('accion') != ['buscar']:
                        url = url.split('#')[0] + '&sin_buscar=1'
                respuesta.headers['location'] = url
            return respuesta
        return atender


def crear_router(proveedor):
    templates = Plantillas(directory=str(RAIZ / 'templates' / 'v04'))
    templates.env.loader = Loader([str(RAIZ / 'templates' / 'v04'), str(RAIZ / 'templates')])
    templates.env.filters.update(rutas.templates.env.filters)
    templates.env.filters['v04url'] = destino
    templates.env.globals.update(rutas.templates.env.globals)
    templates.env.globals.update(shared_css='/consola/static/consola.css', shared_js='/consola/static/consola.js')
    from oportunidades.modelos import CRITERIOS
    templates.env.globals['etiquetas_necesidades'] = dict(CRITERIOS, operacion='Operación',
        tipo='Tipo de inmueble', ciudad='Ciudad', barrios='Barrios', zonas='Zonas',
        presupuesto_max='Presupuesto máximo COP', tipo_area='Tipo de área para comparar',
        preferencias='Criterios tratados como preferencias', observaciones='Observaciones')
    router = APIRouter(route_class=Ruta)

    def verificar_inmueble(catalogo, identificador):
        try:
            if catalogo.obtener(identificador) is None:
                raise HTTPException(404, 'Inmueble no encontrado')
        except (FileNotFoundError, ErrorLecturaCatalogo) as exc:
            raise HTTPException(503, 'El catálogo no está disponible. Vuelve a intentar.') from exc

    @router.get('/v0.4/comentarios/{identificador:path}')
    def leer(identificador: str, catalogo=Depends(proveedor), s=Depends(proveedor_oportunidades)):
        verificar_inmueble(catalogo, identificador)
        try:
            return {'texto': Comentarios(s.repositorio.ruta).leer(identificador)}
        except ErrorPersistencia as exc:
            raise HTTPException(503, str(exc)) from exc

    @router.post('/v0.4/comentarios/{identificador:path}')
    async def guardar(request: Request, identificador: str, catalogo=Depends(proveedor), s=Depends(proveedor_oportunidades)):
        verificar_inmueble(catalogo, identificador)
        try:
            datos = await request.json()
        except ValueError as exc:
            raise HTTPException(422, 'Se requiere JSON válido') from exc
        if not isinstance(datos, dict) or not isinstance(datos.get('texto'), str):
            raise HTTPException(422, 'Se requiere texto')
        try:
            Comentarios(s.repositorio.ruta).guardar(identificador, datos['texto'])
        except ErrorPersistencia as exc:
            raise HTTPException(503, str(exc)) from exc
        return JSONResponse({'texto': datos['texto'], 'guardado': True})

    for route in rutas.crear_router(proveedor, templates).routes:
        if route.path.startswith('/consola'):
            router.add_api_route(destino(route.path), route.endpoint, methods=route.methods,
                                 response_class=route.response_class, include_in_schema=False)
    return router
