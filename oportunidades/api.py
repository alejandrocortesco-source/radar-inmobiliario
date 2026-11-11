"""API JSON reutilizable; Gemini solo mediante su solicitud manual dedicada."""
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from uuid import UUID
from pydantic import BaseModel, Field
from .automatizacion import recalcular_seguro, plan_gemini, solicitar_gemini
from .seguimiento import SeguimientoSQLite

from catalogo.persistencia.contrato import ErrorLecturaCatalogo
from .modelos import ClienteDatos, OportunidadDatos
from .persistencia import NoEncontrado, ErrorPersistencia
from .servicio import servicio_oportunidades


def ejecutar(funcion, *args, **kwargs):
    try:
        return funcion(*args, **kwargs)
    except NoEncontrado as exc:
        raise HTTPException(404, str(exc)) from exc
    except (ErrorPersistencia, ErrorLecturaCatalogo, FileNotFoundError) as exc:
        raise HTTPException(503, 'El almacenamiento no está disponible') from exc


def proveedor_oportunidades():
    return ejecutar(servicio_oportunidades)


class SolicitudGemini(BaseModel):
    solicitud: UUID
    huella: str = Field(pattern=r'^[a-f0-9]{64}$')


def crear_router(proveedor_catalogo):
    router = APIRouter(prefix='/api', tags=['Consola v0.3'])

    @router.get('/clientes')
    def clientes(s=Depends(proveedor_oportunidades)):
        return ejecutar(s.clientes)

    @router.get('/clientes/{identificador}')
    def cliente(identificador: str, s=Depends(proveedor_oportunidades)):
        return ejecutar(s.cliente, identificador)

    @router.post('/clientes', status_code=201)
    def crear_cliente(datos: ClienteDatos, s=Depends(proveedor_oportunidades)):
        return ejecutar(s.guardar_cliente, datos)

    @router.put('/clientes/{identificador}')
    def editar_cliente(identificador: str, datos: ClienteDatos, s=Depends(proveedor_oportunidades)):
        return ejecutar(s.guardar_cliente, datos, identificador)

    @router.get('/oportunidades')
    def oportunidades(s=Depends(proveedor_oportunidades)):
        return ejecutar(s.oportunidades)

    @router.get('/oportunidades/{identificador}')
    def oportunidad(identificador: str, s=Depends(proveedor_oportunidades)):
        return ejecutar(s.oportunidad, identificador)

    @router.post('/oportunidades', status_code=201)
    def crear_oportunidad(datos: OportunidadDatos, tareas: BackgroundTasks,
                          s=Depends(proveedor_oportunidades), catalogo=Depends(proveedor_catalogo)):
        o = ejecutar(s.guardar_oportunidad, datos)
        tareas.add_task(recalcular_seguro, s, catalogo, o.id)
        return o

    @router.put('/oportunidades/{identificador}')
    def editar_oportunidad(identificador: str, datos: OportunidadDatos, tareas: BackgroundTasks,
                           s=Depends(proveedor_oportunidades), catalogo=Depends(proveedor_catalogo)):
        o = ejecutar(s.guardar_oportunidad, datos, identificador)
        tareas.add_task(recalcular_seguro, s, catalogo, o.id)
        return o

    @router.get('/oportunidades/{identificador}/coincidencias')
    def coincidencias(identificador: str, orden: str = Query('coincidencia', pattern='^(coincidencia|precio)$'),
                      s=Depends(proveedor_oportunidades), catalogo=Depends(proveedor_catalogo)):
        return ejecutar(s.coincidencias, identificador, catalogo, orden)

    @router.get('/oportunidades/{identificador}/diagnostico')
    def diagnostico(identificador: str, orden: str = Query('coincidencia', pattern='^(coincidencia|precio)$'),
                    s=Depends(proveedor_oportunidades), catalogo=Depends(proveedor_catalogo)):
        return ejecutar(s.diagnostico, identificador, catalogo, orden)

    @router.post('/oportunidades/{identificador}/buscar')
    def buscar_manual(identificador: str, s=Depends(proveedor_oportunidades), catalogo=Depends(proveedor_catalogo)):
        o = ejecutar(s.oportunidad, identificador)
        if o.estado != 'abierta' or not SeguimientoSQLite(s.repositorio.ruta).activo(o.cliente_id):
            raise HTTPException(409, 'Activa el cliente y abre la oportunidad antes de buscar.')
        ejecutar(recalcular_seguro, s, catalogo, identificador, True)
        return ejecutar(s.coincidencias, identificador, catalogo)

    @router.get('/oportunidades/{identificador}/gemini')
    def vista_previa(identificador: str, s=Depends(proveedor_oportunidades), catalogo=Depends(proveedor_catalogo)):
        o = ejecutar(s.oportunidad, identificador)
        plan = ejecutar(plan_gemini, o, ejecutar(s.coincidencias, identificador, catalogo), SeguimientoSQLite(s.repositorio.ruta))
        return {'huella': plan['firma'], 'total': len(plan['entradas']), 'seleccionados': len(plan['seleccion']),
                'limite': plan['limite'], 'necesitan_evaluacion': len(plan['faltantes']),
                'reutilizadas': len(plan['evaluaciones']), 'aviso': plan['aviso'],
                'consumo': 'Una solicitud explícita puede generar consumo en Google.'}

    @router.post('/oportunidades/{identificador}/gemini', status_code=202)
    def evaluar_manual(identificador: str, datos: SolicitudGemini, tareas: BackgroundTasks,
                       s=Depends(proveedor_oportunidades), catalogo=Depends(proveedor_catalogo)):
        try:
            tarea = ejecutar(solicitar_gemini, s, catalogo, identificador, str(datos.solicitud), esperada=datos.huella)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        if tarea:
            tareas.add_task(tarea)
        return {'solicitud': str(datos.solicitud), 'aceptada': tarea is not None}

    return router
