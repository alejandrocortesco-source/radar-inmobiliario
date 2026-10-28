"""Adaptador HTML de captura; las reglas y escrituras residen en oportunidades/."""
from urllib.parse import parse_qs

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from pydantic import ValidationError

from catalogo.modelos import TipoInmueble
from catalogo.persistencia.contrato import ErrorLecturaCatalogo
from oportunidades.api import crear_router as crear_api, proveedor_oportunidades
from oportunidades.modelos import ClienteDatos, Necesidades, CRITERIOS
from oportunidades.matching import diagnosticar
from oportunidades.persistencia import ErrorPersistencia, NoEncontrado
from oportunidades.servicio import servicio_oportunidades
from .ubicaciones import opciones_ubicacion, actualizar_ciudad
from .resultados import presentar_resultados, ORDENES as ORDENES_MATCH
from oportunidades.normalizacion import normalizar_ciudad


def contexto_captura(request, todos, valores=None, errores=None, servicio=None, calcular=True):
    s = servicio or servicio_oportunidades()
    clientes = s.clientes()
    oportunidades = s.oportunidades()
    nombres = {c.id: c.nombre for c in clientes}
    seleccionado = None
    if valores is None:
        valores = {'operacion': 'compra', 'tipo_area': 'construida', 'estado': 'abierta'}
        if request.query_params.get('oportunidad'):
            seleccionado = s.oportunidad(request.query_params['oportunidad'])
            valores.update(seleccionado.necesidades.model_dump(mode='json'))
            valores.update(oportunidad_id=seleccionado.id, cliente_id=seleccionado.cliente_id, estado=seleccionado.estado)
        elif request.query_params.get('cliente'):
            valores['cliente_id'] = s.cliente(request.query_params['cliente']).id
        if valores.get('cliente_id'):
            c = s.cliente(valores['cliente_id'])
            valores.update(nombre=c.nombre, telefono=c.telefono or '')
    ubicaciones = opciones_ubicacion(todos, valores)
    contexto = dict(captura=valores, errores_captura=errores or [], clientes_crm=clientes,
                oportunidades_crm=oportunidades, nombres_clientes=nombres,
                **ubicaciones,
                criterios_crm=CRITERIOS, tipos_crm=tuple(TipoInmueble), seleccionada_crm=seleccionado,
                guardada=request.query_params.get('guardada') == '1', match_total=len(todos), informe=None,
                aviso_ubicaciones=valores.get('aviso_ubicaciones', ''))
    if seleccionado and calcular:
        contexto.update(contexto_matching(seleccionado, todos, query=request.query_params))
    elif seleccionado:
        contexto['oportunidad'] = seleccionado
    return contexto


def contexto_matching(oportunidad, todos, orden=None, query=None, independiente=False):
    informe = diagnosticar(oportunidad.necesidades, todos)
    return dict(informe=informe, oportunidad=oportunidad, match_total=len(todos),
                **presentar_resultados(oportunidad, informe, query, independiente, orden))


async def leer_formulario(request):
    # URL-encoded estándar: no requiere python-multipart ni otra dependencia.
    datos = parse_qs((await request.body()).decode('utf-8'), keep_blank_values=True)
    valores = {k: v[-1].strip() for k, v in datos.items()}
    valores['preferencias'] = datos.get('preferencias', [])
    valores['barrios'] = [v[7:] for v in datos.get('ubicaciones', []) if v.startswith('barrio:')]
    valores['zonas'] = [v[5:] for v in datos.get('ubicaciones', []) if v.startswith('zona:')]
    for campo in ('barrios', 'zonas'):
        valores[campo] += [v.strip() for v in valores.get('otros_' + campo, '').split(',') if v.strip()]
    return valores


def mensajes_validacion(exc):
    etiquetas = {**CRITERIOS, 'nombre': 'Nombre del cliente', 'telefono': 'Teléfono',
                 'operacion': 'Operación', 'tipo': 'Tipo de inmueble', 'ciudad': 'Ciudad',
                 'presupuesto_max': 'Presupuesto máximo', 'estado': 'Estado', 'observaciones': 'Observaciones'}
    mensajes = []
    for e in exc.errors():
        campo = '.'.join(str(v) for v in e['loc'])
        texto = e['msg'].removeprefix('Value error, ')
        if e['type'] in ('missing', 'string_too_short'):
            texto = 'Este campo es obligatorio.'
        elif e['type'].startswith(('int_', 'decimal_', 'greater_than', 'less_than', 'finite_number')):
            texto = 'Ingresa un número válido dentro del rango permitido; usa enteros para cantidades y valores positivos para presupuesto y áreas.'
        mensajes.append(f'{etiquetas.get(campo, campo)}: {texto}' if campo else texto)
    return mensajes


def crear_router(proveedor_catalogo, templates):
    router = APIRouter()
    router.include_router(crear_api(proveedor_catalogo))

    def estado(request, exc, status):
        return templates.TemplateResponse(request=request, name='estado.html', status_code=status,
            context={'titulo': 'No pudimos completar la solicitud', 'mensaje': str(exc), 'reintentar': '/consola/'})

    @router.post('/consola/ubicaciones', include_in_schema=False)
    async def refrescar_ubicaciones(request: Request, catalogo=Depends(proveedor_catalogo), s=Depends(proveedor_oportunidades)):
        valores = await leer_formulario(request)
        try:
            todos = catalogo.listar()
            quitadas = actualizar_ciudad(todos, valores)
            contexto = contexto_captura(request, todos, valores, servicio=s)
            contexto['aviso_ubicaciones'] = ('Se retiraron ubicaciones que no corresponden a la ciudad: ' + ', '.join(quitadas)) if quitadas else 'Barrios actualizados para la ciudad seleccionada. El borrador no se ha guardado.'
            return templates.TemplateResponse(request=request, name='captura.html', context=contexto)
        except (ErrorPersistencia, ErrorLecturaCatalogo, FileNotFoundError) as exc:
            return estado(request, exc, 503)

    @router.post('/consola/oportunidades', include_in_schema=False)
    async def guardar(request: Request, catalogo=Depends(proveedor_catalogo), s=Depends(proveedor_oportunidades)):
        valores = await leer_formulario(request)
        try:
            if valores.get('ubicaciones_ciudad') and valores['ubicaciones_ciudad'] != normalizar_ciudad(valores.get('ciudad', '')):
                quitadas = actualizar_ciudad(catalogo.listar(), valores)
                if quitadas:
                    valores['aviso_ubicaciones'] = 'Se retiraron ubicaciones que no corresponden a la ciudad: ' + ', '.join(quitadas)
            cliente = ClienteDatos(nombre=valores.get('nombre', ''), telefono=valores.get('telefono') or None)
            campos = {k: v for k, v in valores.items() if k in Necesidades.model_fields and v != ''}
            necesidades = Necesidades.model_validate(campos)
            o = s.capturar(cliente, necesidades, valores.get('estado', 'abierta'),
                           valores.get('cliente_id') or None, valores.get('oportunidad_id') or None)
            destino = '/consola/?oportunidad=' + o.id + '&guardada=1'
            if valores.get('accion') == 'buscar':
                destino += '#matching-resumen'
            return RedirectResponse(destino, status_code=303)
        except ValidationError as exc:
            try:
                contexto = contexto_captura(request, catalogo.listar(), valores, mensajes_validacion(exc), s)
            except (ErrorLecturaCatalogo, FileNotFoundError):
                contexto = contexto_captura(request, (), valores, mensajes_validacion(exc), s)
            return templates.TemplateResponse(request=request, name='captura.html', context=contexto, status_code=422)
        except NoEncontrado as exc:
            return estado(request, exc, 404)
        except ErrorPersistencia as exc:
            return estado(request, exc, 503)

    @router.get('/consola/clientes/{identificador}', include_in_schema=False)
    def editar_cliente(request: Request, identificador: str, s=Depends(proveedor_oportunidades)):
        try:
            c = s.cliente(identificador)
            return templates.TemplateResponse(request=request, name='cliente.html', context={'cliente': c, 'errores': []})
        except NoEncontrado as exc:
            return estado(request, exc, 404)
        except ErrorPersistencia as exc:
            return estado(request, exc, 503)

    @router.post('/consola/clientes/{identificador}', include_in_schema=False)
    async def guardar_cliente(request: Request, identificador: str, s=Depends(proveedor_oportunidades)):
        valores = parse_qs((await request.body()).decode('utf-8'), keep_blank_values=True)
        datos = {'id': identificador, 'nombre': valores.get('nombre', [''])[-1], 'telefono': valores.get('telefono', [''])[-1]}
        try:
            s.guardar_cliente(ClienteDatos(nombre=datos['nombre'], telefono=datos['telefono'] or None), identificador)
            return RedirectResponse('/consola/?cliente=' + identificador + '&guardada=1', status_code=303)
        except ValidationError as exc:
            return templates.TemplateResponse(request=request, name='cliente.html', context={'cliente': datos, 'errores': mensajes_validacion(exc)}, status_code=422)
        except NoEncontrado as exc:
            return estado(request, exc, 404)
        except ErrorPersistencia as exc:
            return estado(request, exc, 503)

    @router.get('/consola/oportunidades/{identificador}/coincidencias', include_in_schema=False)
    def coincidencias(request: Request, identificador: str, orden: str = 'coincidencia',
                      catalogo=Depends(proveedor_catalogo), s=Depends(proveedor_oportunidades)):
        if orden not in ORDENES_MATCH:
            return estado(request, 'Orden desconocido', 422)
        try:
            o = s.oportunidad(identificador)
            contexto = contexto_matching(o, catalogo.listar(), orden, request.query_params, True)
            return templates.TemplateResponse(request=request, name='coincidencias.html', context={
                **contexto, 'cliente': s.cliente(o.cliente_id), 'matching_independiente': True,
            })
        except NoEncontrado as exc:
            return estado(request, exc, 404)
        except (ErrorPersistencia, ErrorLecturaCatalogo, FileNotFoundError):
            return estado(request, 'No se pudo leer el almacenamiento. Vuelve a intentar.', 503)

    return router
