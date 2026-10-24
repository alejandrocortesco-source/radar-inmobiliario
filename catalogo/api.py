"""Router de consulta reutilizable; la aplicación inyecta el servicio y su backend."""

from fastapi import APIRouter, Depends, HTTPException, Query

from .persistencia.contrato import ErrorLecturaCatalogo
from .servicio import InmuebleNoEncontrado, ServicioCatalogo


def _consultar(operacion, **parametros):
    try:
        return operacion(**parametros)
    except InmuebleNoEncontrado as exc:
        raise HTTPException(404, 'Inmueble no encontrado') from exc
    except (FileNotFoundError, ErrorLecturaCatalogo) as exc:
        raise HTTPException(503, 'El catálogo no está disponible; compruebe la base de datos') from exc


def consultar_ficha(servicio, property_id, run_id=None):
    return _consultar(servicio.ficha_compatible, identificador=property_id, run_id=run_id)


def consultar_catalogo(servicio, **parametros):
    return _consultar(servicio.catalogo_compatible, **parametros)


def crear_router(proveedor_servicio):
    """Registra las dos rutas una sola vez sobre cualquier aplicación FastAPI."""
    router = APIRouter()

    @router.get('/api/catalog')
    def catalog_api(state: str | None = None, search_url: str | None = None,
                    limit: int = Query(100, ge=1, le=1000),
                    offset: int = Query(0, ge=0),
                    servicio: ServicioCatalogo = Depends(proveedor_servicio)):
        return consultar_catalogo(servicio, state=state, search_url=search_url,
                                  limit=limit, offset=offset)

    @router.get('/api/properties/{property_id}')
    def property_api(property_id: str, run_id: int | None = None,
                     servicio: ServicioCatalogo = Depends(proveedor_servicio)):
        return consultar_ficha(servicio, property_id, run_id)

    return router
