"""UX v0.6: servicios existentes, páginas independientes y tareas posteriores al guardado."""
import sqlite3
from pathlib import Path
from urllib.parse import parse_qs
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, Request, HTTPException
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError

from catalogo.persistencia.contrato import ErrorLecturaCatalogo
from catalogo.servicio import ConsultaInvalida
from oportunidades.api import proveedor_oportunidades
from oportunidades.modelos import ClienteDatos, Necesidades
from oportunidades.persistencia import ErrorPersistencia, NoEncontrado
from oportunidades.seguimiento import SeguimientoSQLite
from oportunidades.automatizacion import recalcular_seguro, plan_gemini, solicitar_gemini, clave_novedad
from oportunidades.matching import buscar
from .oportunidades import contexto_captura, leer_formulario, mensajes_validacion
from .ubicaciones import actualizar_ciudad
from oportunidades.normalizacion import normalizar_ciudad
from .anunciantes import url_anunciante
from .presentacion import fecha, numero, enlace_publico
from .inicio import indicadores, resumen_clientes
from catalogo.fuentes import wasi, fincaraiz, metrocuadrado

RAIZ = Path(__file__).parent
templates = Jinja2Templates(directory=[str(RAIZ / 'templates' / 'v06'), str(RAIZ / 'templates')])
templates.env.filters.update(fecha=fecha, numero=numero)
templates.env.globals.update(enlace_publico=enlace_publico, url_anunciante=url_anunciante)


def crear_router(proveedor):
    router = APIRouter(prefix='/v0.6', include_in_schema=False)
    from .identificacion import crear_router as router_identificacion
    # El router de revisión ya contiene el prefijo /v0.6.
    router_identidad = router_identificacion(proveedor, templates)

    def render(request, name, status=200, **context):
        return templates.TemplateResponse(request=request, name=name, context=context, status_code=status)

    def seguimiento(s):
        return SeguimientoSQLite(s.repositorio.ruta)

    def error(request, exc, status=503):
        return render(request, 'error06.html', status, mensaje=str(exc))

    def dashboard(request, catalogo, s, status=200, **extras):
        todos = catalogo.listar()
        filas = resumen_clientes(s, seguimiento(s), todos)
        registros = catalogo.busquedas.opciones_wasi() if catalogo.busquedas else wasi.opciones_iniciales()
        valores = {'id_pais': '1', 'id_dpto': '15', **(extras.get('fuente_valores') or {})}
        extras['fuente_valores'] = valores
        fr_opciones = catalogo.busquedas.opciones_fincaraiz() if catalogo.busquedas else fincaraiz.opciones_iniciales()
        return render(request, 'inicio06.html', status, recientes=[f for f in filas if f['activo']][:6],
            indicadores=indicadores(todos, catalogo.ultima_actualizacion()), fuentes=catalogo.listar_busquedas(),
            fr_opciones=fr_opciones, wasi_campos=wasi.SELECTS, wasi_numeros=wasi.INPUTS, wasi_labels=wasi.LABELS,
            wasi_registros=registros, wasi_opciones={c: wasi.opciones(c, valores, registros) for c in wasi.SELECTS},
            mensaje=request.query_params.get('mensaje'), **extras)

    @router.get('')
    def entrada():
        return RedirectResponse('/v0.6/', 307)

    @router.get('/')
    def inicio(request: Request, catalogo=Depends(proveedor), s=Depends(proveedor_oportunidades)):
        try:
            editar_fr = request.query_params.get('editar_fincaraiz')
            if editar_fr and catalogo.busquedas:
                c = catalogo.busquedas.configuracion_fincaraiz(editar_fr)
                b = next((b for b in catalogo.listar_busquedas() if b['fuente'] == 'fincaraiz' and b['id_busqueda'] == editar_fr), None)
                if not c or not b:
                    return error(request, 'Búsqueda Fincaraíz no encontrada', 404)
                return dashboard(request, catalogo, s, fuente_valores={'fuente': 'fincaraiz', 'nombre': b['nombre'], 'fr_url': c['url_original'], 'reemplazar_fr': editar_fr})
            editar = request.query_params.get('editar_wasi')
            if editar and catalogo.busquedas:
                config = catalogo.busquedas.configuracion_wasi(editar)
                registrada = next((b for b in catalogo.listar_busquedas() if b['fuente'] == 'wasi' and b['id_busqueda'] == editar), None)
                if not config or not registrada:
                    return error(request, 'Búsqueda Wasi no encontrada.', 404)
                return dashboard(request, catalogo, s, fuente_valores={**config['filtros'], 'fuente': 'wasi', 'nombre': registrada['nombre'], 'reemplazar': editar})
            return dashboard(request, catalogo, s)
        except (ErrorPersistencia, ErrorLecturaCatalogo, FileNotFoundError) as exc:
            return error(request, exc)

    @router.get('/clientes')
    def clientes(request: Request, vista: str = 'activos', catalogo=Depends(proveedor), s=Depends(proveedor_oportunidades)):
        if vista not in ('activos', 'inactivos'):
            raise HTTPException(422, 'Vista desconocida')
        try:
            filas = resumen_clientes(s, seguimiento(s), catalogo.listar())
            return render(request, 'clientes06.html', filas=[f for f in filas if f['activo'] == (vista == 'activos')], vista=vista)
        except (ErrorPersistencia, ErrorLecturaCatalogo, FileNotFoundError) as exc:
            return error(request, exc)

    @router.get('/nuevo')
    def nuevo(request: Request, catalogo=Depends(proveedor), s=Depends(proveedor_oportunidades)):
        try:
            contexto = contexto_captura(request, catalogo.listar(), servicio=s, calcular=False)
            return render(request, 'captura06.html', **contexto)
        except NoEncontrado as exc:
            return error(request, exc, 404)
        except (ErrorPersistencia, ErrorLecturaCatalogo, FileNotFoundError) as exc:
            return error(request, exc)

    @router.post('/ubicaciones')
    async def ubicaciones(request: Request, catalogo=Depends(proveedor), s=Depends(proveedor_oportunidades)):
        valores = await leer_formulario(request)
        try:
            todos = catalogo.listar()
            if valores.get('ubicaciones_ciudad') and valores['ubicaciones_ciudad'] != normalizar_ciudad(valores.get('ciudad', '')):
                actualizar_ciudad(todos, valores)
            return render(request, 'captura06.html', **contexto_captura(request, todos, valores, servicio=s, calcular=False))
        except (ErrorPersistencia, ErrorLecturaCatalogo, FileNotFoundError) as exc:
            return error(request, exc)

    @router.post('/oportunidades')
    async def guardar(request: Request, tareas: BackgroundTasks, catalogo=Depends(proveedor), s=Depends(proveedor_oportunidades)):
        valores = await leer_formulario(request)
        try:
            todos = catalogo.listar()
            if valores.get('ubicaciones_ciudad') and valores['ubicaciones_ciudad'] != normalizar_ciudad(valores.get('ciudad', '')):
                actualizar_ciudad(todos, valores)
            anterior = s.oportunidad(valores['oportunidad_id']) if valores.get('oportunidad_id') else None
            if anterior and anterior.cliente_id != valores.get('cliente_id'):
                raise NoEncontrado('La oportunidad no pertenece al cliente seleccionado')
            cliente = ClienteDatos(nombre=valores.get('nombre', ''), telefono=valores.get('telefono') or None)
            necesidades = Necesidades.model_validate({k: v for k, v in valores.items() if k in Necesidades.model_fields and v != ''})
            # Las zonas históricas siguen siendo legibles y editables. Las altas nuevas requieren barrios.
            if not necesidades.barrios and not (anterior and anterior.necesidades.zonas):
                raise ValueError('Selecciona al menos un barrio de interés')
            o = s.capturar(cliente, necesidades, valores.get('estado', 'abierta'), valores.get('cliente_id') or None, valores.get('oportunidad_id') or None)
            tareas.add_task(recalcular_seguro, s, catalogo, o.id)
            return RedirectResponse(f'/v0.6/clientes/{o.cliente_id}?oportunidad={o.id}&guardado=1', 303)
        except (ValidationError, ValueError) as exc:
            if isinstance(exc, NoEncontrado):
                return error(request, exc, 404)
            errores = mensajes_validacion(exc) if isinstance(exc, ValidationError) else [str(exc)]
            return render(request, 'captura06.html', 422, **contexto_captura(request, catalogo.listar(), valores, errores, s, calcular=False))
        except (ErrorPersistencia, ErrorLecturaCatalogo, FileNotFoundError) as exc:
            return error(request, exc)

    @router.get('/clientes/{identificador}')
    def ficha(request: Request, identificador: str, orden: str = 'coincidencia', oportunidad: str | None = None,
              catalogo=Depends(proveedor), s=Depends(proveedor_oportunidades)):
        if orden not in ('coincidencia', 'precio', 'precio_desc', 'area', 'habitaciones', 'revision', 'ia'):
            raise HTTPException(422, 'Orden desconocido')
        try:
            c = s.cliente(identificador)
            propias = [o for o in s.oportunidades() if o.cliente_id == c.id]
            o = next((x for x in propias if x.id == oportunidad), None) if oportunidad else next((x for x in propias if x.estado == 'abierta'), propias[0] if propias else None)
            if oportunidad and not o:
                raise NoEncontrado('Oportunidad no encontrada para este cliente')
            repo = seguimiento(s)
            decisiones = repo.decisiones(o.id) if o else {}
            ejecucion = repo.leer(o.id) if o else None
            resultados = buscar(o.necesidades, catalogo.listar()) if o else []
            if o and o.estado == 'abierta' and repo.activo(c.id):
                repo.registrar_resultados(o.id, resultados)
            novedades = repo.novedades(o.id) if o else {}
            plan = plan_gemini(o, resultados, repo) if o else None
            evaluacion = repo.ultima_gemini(o.id) if o else None
            desactualizada = evaluacion and evaluacion['datos'].get('huella') != plan['firma']
            filas = []
            for r in resultados:
                iid = r.inmueble.id_interno
                filas.append({'r': r, 'decision': decisiones.get(iid, {}).get('estado', 'pendiente'),
                    'ia': plan['evaluaciones'].get(iid), 'novedad': novedades.get(clave_novedad(r)),
                    'alternativas': [{'r': x, 'decision': decisiones.get(x.inmueble.id_interno, {}).get('estado', 'pendiente')} for x in r.alternativas],
                    'estados_publicaciones': {p.id_interno: decisiones.get(p.id_interno, {}).get('estado', 'pendiente') for p in (r.inmueble.publicaciones or (r.inmueble,))}})
            if orden in ('precio', 'precio_desc'):
                filas.sort(key=lambda f: (f['r'].oferta is None or f['r'].oferta.precio is None, (f['r'].oferta.precio or 0) * (-1 if orden == 'precio_desc' else 1) if f['r'].oferta else 0))
            elif orden in ('area', 'habitaciones'):
                campo = 'area_construida_m2' if orden == 'area' else 'habitaciones'
                filas.sort(key=lambda f: (getattr(f['r'].inmueble, campo) is None, getattr(f['r'].inmueble, campo) or 0))
            elif orden == 'revision':
                filas.sort(key=lambda f: ({'pendiente': 0, 'preseleccionado': 1, 'descartado': 2}[f['decision']], f['r'].inmueble.id_interno))
            elif orden == 'ia':
                filas.sort(key=lambda f: (f['ia'] is None, -f['ia']['puntuacion'] if f['ia'] else 0))
            actuales = {f['r'].inmueble.id_interno for f in filas}
            historicas = [d for iid, d in decisiones.items() if iid not in actuales]
            return render(request, 'cliente06.html', cliente=c, propias=propias, oportunidad=o,
                activo=repo.activo(c.id), filas=filas, historicas=historicas, orden=orden, ejecucion=ejecucion,
                plan=plan, evaluacion=evaluacion, desactualizada=desactualizada, solicitud=str(uuid4()),
                nuevas=sum(bool(f['novedad'] and f['novedad']['nueva']) for f in filas),
                conteos={estado: sum(f['decision'] == estado for f in filas) for estado in ('pendiente', 'preseleccionado', 'descartado')})
        except NoEncontrado as exc:
            return error(request, exc, 404)
        except (ErrorPersistencia, ErrorLecturaCatalogo, FileNotFoundError) as exc:
            return error(request, exc)

    @router.post('/clientes/{identificador}')
    async def editar_cliente(request: Request, identificador: str, tareas: BackgroundTasks,
                             catalogo=Depends(proveedor), s=Depends(proveedor_oportunidades)):
        valores = {k: v[-1] for k, v in parse_qs((await request.body()).decode(), keep_blank_values=True).items()}
        try:
            s.guardar_cliente(ClienteDatos(nombre=valores.get('nombre', ''), telefono=valores.get('telefono') or None), identificador)
            seguimiento(s).activar(identificador, valores.get('activo') == '1')
            for o in s.oportunidades():
                if o.cliente_id == identificador and o.estado == 'abierta':
                    tareas.add_task(recalcular_seguro, s, catalogo, o.id)
            return RedirectResponse('/v0.6/clientes/' + identificador + '?guardado=1', 303)
        except ValidationError as exc:
            return error(request, '; '.join(mensajes_validacion(exc)), 422)
        except NoEncontrado as exc:
            return error(request, exc, 404)
        except ErrorPersistencia as exc:
            return error(request, exc)

    @router.post('/oportunidades/{identificador}/recalcular')
    def manual(request: Request, identificador: str, tareas: BackgroundTasks, catalogo=Depends(proveedor), s=Depends(proveedor_oportunidades)):
        try:
            o = s.oportunidad(identificador)
            if o.estado != 'abierta' or not seguimiento(s).activo(o.cliente_id):
                return error(request, 'Activa el cliente y abre la oportunidad antes de recalcular.', 422)
            recalcular_seguro(s, catalogo, o.id, True)
            return RedirectResponse(f'/v0.6/clientes/{o.cliente_id}?oportunidad={o.id}&recalculando=1', 303)
        except NoEncontrado as exc:
            return error(request, exc, 404)
        except ErrorPersistencia as exc:
            return error(request, exc)

    @router.get('/oportunidades/{identificador}/estado')
    def estado(identificador: str, s=Depends(proveedor_oportunidades)):
        try:
            s.oportunidad(identificador)
            repo = seguimiento(s)
            return repo.ultima_gemini(identificador) or repo.leer(identificador) or {'estado': 'sin_calcular'}
        except NoEncontrado as exc:
            raise HTTPException(404, str(exc)) from exc
        except ErrorPersistencia as exc:
            raise HTTPException(503, str(exc)) from exc

    @router.post('/oportunidades/{identificador}/gemini')
    async def evaluar_manual(request: Request, identificador: str, tareas: BackgroundTasks,
                             catalogo=Depends(proveedor), s=Depends(proveedor_oportunidades)):
        valores = {k: v[-1] for k, v in parse_qs((await request.body()).decode(), keep_blank_values=True).items()}
        try:
            o = s.oportunidad(identificador)
            if not valores.get('huella'):
                raise ValueError('Revisa la vista previa antes de evaluar con Gemini.')
            tarea = solicitar_gemini(s, catalogo, identificador, valores.get('solicitud', ''), esperada=valores['huella'])
            if tarea:
                tareas.add_task(tarea)
            return RedirectResponse(f'/v0.6/clientes/{o.cliente_id}?oportunidad={o.id}&evaluando=1#candidatos', 303)
        except NoEncontrado as exc:
            return error(request, exc, 404)
        except ValueError as exc:
            return error(request, exc, 409)
        except (ErrorPersistencia, ErrorLecturaCatalogo, FileNotFoundError) as exc:
            return error(request, exc)

    @router.post('/oportunidades/{identificador}/novedades/vistas')
    async def marcar_novedades(request: Request, identificador: str, s=Depends(proveedor_oportunidades)):
        valores = parse_qs((await request.body()).decode(), keep_blank_values=True)
        try:
            o = s.oportunidad(identificador)
            tokens = set(valores.get('novedad', []))
            repo = seguimiento(s)
            # Solo tokens de esa oportunidad y de la aparición mostrada. Una
            # reaparición concurrente no se borra con un formulario anterior.
            mostradas = {(n['relacion'], n['ultima_deteccion']) for n in repo.novedades(o.id).values()
                         if n['presente'] and n['nueva'] and n['relacion'] + '|' + n['ultima_deteccion'] in tokens}
            repo.marcar_vistas(o.id, mostradas)
            return RedirectResponse(f'/v0.6/clientes/{o.cliente_id}?oportunidad={o.id}#candidatos', 303)
        except NoEncontrado as exc:
            return error(request, exc, 404)
        except ErrorPersistencia as exc:
            return error(request, exc)

    @router.post('/oportunidades/{identificador}/decision')
    async def decision(request: Request, identificador: str, catalogo=Depends(proveedor), s=Depends(proveedor_oportunidades)):
        valores = {k: v[-1] for k, v in parse_qs((await request.body()).decode(), keep_blank_values=True).items()}
        try:
            o = s.oportunidad(identificador)
            iid = valores.get('inmueble', '')
            repo = seguimiento(s)
            # Permite modificar decisiones históricas incluso si la ficha ya no existe.
            if iid not in repo.decisiones(o.id) and not any(iid in {p.id_interno for p in (r.inmueble.publicaciones or (r.inmueble,))} for r in buscar(o.necesidades, catalogo.listar())):
                raise NoEncontrado('Coincidencia no encontrada para esta oportunidad')
            repo.decision(o.id, iid, valores.get('estado'))
            return RedirectResponse(f'/v0.6/clientes/{o.cliente_id}?oportunidad={o.id}&guardado=1#candidatos', 303)
        except NoEncontrado as exc:
            return error(request, exc, 404)
        except ValueError as exc:
            return error(request, exc, 422)
        except (ErrorPersistencia, ErrorLecturaCatalogo, FileNotFoundError) as exc:
            return error(request, exc)

    @router.post('/fuentes')
    async def fuente(request: Request, catalogo=Depends(proveedor), s=Depends(proveedor_oportunidades)):
        valores = {k: v[-1] for k, v in parse_qs((await request.body()).decode(), keep_blank_values=True).items()}
        try:
            if valores.get('fuente') == 'fincaraiz':
                from fincaraiz.browser import verificar
                from playwright.async_api import Error as PortalError
                from metro.extraction import ExtractionError, Restricted
                if catalogo.busquedas is None:
                    raise ErrorLecturaCatalogo('Almacenamiento auxiliar no disponible')
                opciones = catalogo.busquedas.opciones_fincaraiz()
                url = fincaraiz.resolver(valores, opciones) if valores.get('fr_modo') == 'criterios' else valores.get('fr_url', '')
                try:
                    esperado = next((c['filtros'] for c in opciones if c['url_efectiva'] == url), None) if valores.get('fr_modo') == 'criterios' else None
                    config = await verificar(url, esperado)
                except (ExtractionError, Restricted, OSError, PortalError) as exc:
                    raise ValueError('No se pudo verificar la búsqueda en Fincaraíz. Revisa la URL o reintenta cuando el portal esté disponible. No se guardó ni se inició una extracción.') from exc
                catalogo.busquedas.guardar_fincaraiz(valores.get('nombre', ''), config, valores.get('reemplazar_fr'))
                return RedirectResponse('/v0.6/?mensaje=fuente_guardada#agregar-fuente', 303)
            if valores.get('fuente') == 'wasi':
                if catalogo.busquedas is None:
                    raise ErrorLecturaCatalogo('Almacenamiento auxiliar no disponible')
                config = wasi.configurar(valores, catalogo.busquedas.opciones_wasi())
                catalogo.busquedas.guardar_wasi(valores.get('nombre', ''), config, valores.get('reemplazar'))
                return RedirectResponse('/v0.6/?mensaje=fuente_guardada#agregar-fuente', 303)
            if valores.get('fuente', 'metrocuadrado') != 'metrocuadrado':
                raise ConsultaInvalida('Fuente no compatible')
            url = metrocuadrado.validar_url(valores.get('url', ''))
            identificador = catalogo.normalizar_busqueda(url)
            if any(b['id_busqueda'] == identificador for b in catalogo.listar_busquedas()):
                return RedirectResponse('/v0.6/?mensaje=fuente_duplicada#agregar-fuente', 303)
            catalogo.guardar_busqueda('metrocuadrado', identificador, valores.get('nombre', ''))
            return RedirectResponse('/v0.6/?mensaje=fuente_guardada#agregar-fuente', 303)
        except (ConsultaInvalida, ValueError, TypeError) as exc:
            try:
                return dashboard(request, catalogo, s, 422, fuente_error=str(exc), fuente_valores=valores)
            except (ErrorPersistencia, ErrorLecturaCatalogo, FileNotFoundError):
                return error(request, exc, 422)
        except (ErrorLecturaCatalogo, OSError, sqlite3.Error) as exc:
            return error(request, exc)

    @router.post('/fuentes/opciones')
    async def opciones_fuente(request: Request, catalogo=Depends(proveedor), s=Depends(proveedor_oportunidades)):
        valores = {k: v[-1] for k, v in parse_qs((await request.body()).decode(), keep_blank_values=True).items()}
        try:
            # Solo prepara el formulario desde opciones verificadas. No navega ni captura.
            registros = catalogo.busquedas.opciones_wasi() if catalogo.busquedas else wasi.opciones_iniciales()
            for campo in wasi.GEO:
                if valores.get(campo) and not any(o['value'] == valores[campo] for o in wasi.opciones(campo, valores, registros)):
                    valores[campo] = ''
            return dashboard(request, catalogo, s, fuente_valores=valores)
        except (ErrorLecturaCatalogo, ErrorPersistencia, FileNotFoundError) as exc:
            return error(request, exc)

    @router.post('/fuentes/wasi/opciones')
    async def sincronizar_wasi(request: Request, catalogo=Depends(proveedor), s=Depends(proveedor_oportunidades)):
        valores = {k: v[-1] for k, v in parse_qs((await request.body()).decode(), keep_blank_values=True).items()}
        try:
            from wasi.options import actualizar_opciones
            from wasi.__main__ import rutas
            from wasi.locking import bloqueo
            from metro.extraction import Restricted
            if catalogo.busquedas is None:
                raise ErrorLecturaCatalogo('Almacenamiento auxiliar no disponible')
            padres = {}
            for campo in wasi.GEO:
                if valores.get(campo):
                    padres[campo] = valores[campo]
                else:
                    break
            _, base_wasi, _ = rutas(crm=catalogo.busquedas.ruta)
            with bloqueo(base_wasi):
                # Acción separada de guardar: solo opciones, nunca capturas.
                await actualizar_opciones(catalogo.busquedas, padres)
            return dashboard(request, catalogo, s, fuente_valores=valores,
                             fuente_aviso='Opciones de Wasi actualizadas. Revisa los filtros y guarda la búsqueda cuando esté lista.')
        except (ValueError, OSError, ErrorLecturaCatalogo, Restricted) as exc:
            return dashboard(request, catalogo, s, 503, fuente_valores=valores,
                             fuente_error='No se pudieron actualizar las opciones de Wasi. Verifica el acceso configurado o reintenta cuando no haya una captura en curso.')

    @router.post('/fuentes/estado')
    async def estado_fuente(request: Request, catalogo=Depends(proveedor)):
        valores = {k: v[-1] for k, v in parse_qs((await request.body()).decode(), keep_blank_values=True).items()}
        try:
            if valores.get('fuente') != 'fincaraiz' or valores.get('activa') not in ('0', '1'):
                raise ValueError('Estado o fuente inválidos')
            catalogo.busquedas.cambiar_estado('fincaraiz', valores.get('id_busqueda'), valores['activa'] == '1')
            return RedirectResponse('/v0.6/#agregar-fuente', 303)
        except (ValueError, OSError, ErrorLecturaCatalogo) as exc:
            return error(request, exc, 422)

    @router.post('/fuentes/eliminar')
    async def eliminar_fuente(request: Request, catalogo=Depends(proveedor)):
        valores = {k: v[-1] for k, v in parse_qs((await request.body()).decode(), keep_blank_values=True).items()}
        try:
            if valores.get('confirmar') != '1':
                raise ConsultaInvalida('Confirma que quieres eliminar esta búsqueda.')
            if not catalogo.eliminar_busqueda(valores.get('fuente', ''), valores.get('id_busqueda', '')):
                return error(request, 'La búsqueda ya no está registrada.', 404)
            return RedirectResponse('/v0.6/?mensaje=fuente_eliminada#agregar-fuente', 303)
        except ConsultaInvalida as exc:
            return error(request, exc, 422)
        except (ErrorLecturaCatalogo, OSError, sqlite3.Error) as exc:
            return error(request, exc)

    router.routes.extend(router_identidad.routes)
    return router
