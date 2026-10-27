"""API JSON de captura reutilizable, sin integraciones externas."""
from fastapi import APIRouter, Depends, HTTPException, Query

from catalogo.persistencia.contrato import ErrorLecturaCatalogo
from .modelos import ClienteDatos, OportunidadDatos
from .persistencia import NoEncontrado, ErrorPersistencia
from .servicio import servicio_oportunidades


def ejecutar(funcion, *args):
    try:
        return funcion(*args)
    except NoEncontrado as exc:
        raise HTTPException(404, str(exc)) from exc
    except (ErrorPersistencia, ErrorLecturaCatalogo, FileNotFoundError) as exc:
        raise HTTPException(503, 'El almacenamiento no está disponible') from exc


def proveedor_oportunidades():
    return ejecutar(servicio_oportunidades)


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
    def crear_oportunidad(datos: OportunidadDatos, s=Depends(proveedor_oportunidades)):
        return ejecutar(s.guardar_oportunidad, datos)

    @router.put('/oportunidades/{identificador}')
    def editar_oportunidad(identificador: str, datos: OportunidadDatos, s=Depends(proveedor_oportunidades)):
        return ejecutar(s.guardar_oportunidad, datos, identificador)

    @router.get('/oportunidades/{identificador}/coincidencias')
    def coincidencias(identificador: str, orden: str = Query('coincidencia', pattern='^(coincidencia|precio)$'),
                      s=Depends(proveedor_oportunidades), catalogo=Depends(proveedor_catalogo)):
        return ejecutar(s.coincidencias, identificador, catalogo, orden)

    @router.get('/oportunidades/{identificador}/diagnostico')
    def diagnostico(identificador: str, orden: str = Query('coincidencia', pattern='^(coincidencia|precio)$'),
                    s=Depends(proveedor_oportunidades), catalogo=Depends(proveedor_catalogo)):
        return ejecutar(s.diagnostico, identificador, catalogo, orden)

    return router
