"""Router de consulta reutilizable; la aplicación inyecta el servicio y su backend."""

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query

from .filtros import FiltrosCatalogo, OrdenCatalogo
from .modelos import Disponibilidad, Operacion, TipoArea, TipoInmueble
from .persistencia.contrato import ErrorLecturaCatalogo
from .servicio import ConsultaInvalida, InmuebleNoEncontrado, ServicioCatalogo


def _consultar(operacion, **parametros):
    try:
        return operacion(**parametros)
    except ConsultaInvalida as exc:
        raise HTTPException(422, str(exc)) from exc
    except InmuebleNoEncontrado as exc:
        raise HTTPException(404, 'Inmueble no encontrado') from exc
    except (FileNotFoundError, ErrorLecturaCatalogo) as exc:
        raise HTTPException(503, 'El catálogo no está disponible; compruebe la base de datos') from exc


def consultar_ficha(servicio, property_id, run_id=None):
    return _consultar(servicio.ficha_compatible, identificador=property_id, run_id=run_id)


def consultar_catalogo(servicio, **parametros):
    return _consultar(servicio.catalogo_compatible, **parametros)


def filtros_desde_query(
    texto: str | None = Query(None), ciudad: str | None = Query(None),
    zonas: list[str] | None = Query(None), barrios: list[str] | None = Query(None),
    tipos: list[TipoInmueble] | None = Query(None),
    operacion: Operacion | None = Query(None), moneda: str | None = Query(None),
    precio_min: Decimal | None = Query(None), precio_max: Decimal | None = Query(None),
    tipo_area: TipoArea = Query(TipoArea.PUBLICADA),
    area_min_m2: Decimal | None = Query(None), area_max_m2: Decimal | None = Query(None),
    habitaciones_min: int | None = Query(None), habitaciones_max: int | None = Query(None),
    banos_min: int | None = Query(None), parqueaderos_min: int | None = Query(None),
    estratos: list[int] | None = Query(None), fuente: str | None = Query(None),
    id_busqueda: str | None = Query(None),
    disponibilidad: Disponibilidad | None = Query(None),
    requiere_revision: bool | None = Query(None),
    orden: OrdenCatalogo = Query(OrdenCatalogo.ID),
) -> FiltrosCatalogo:
    # limit/offset mantienen su contrato HTTP antiguo; el modelo común conserva
    # su paginación propia (30 por defecto, hasta 200) para Servicio.consultar.
    try:
        return FiltrosCatalogo(
            texto=texto, ciudad=ciudad, zonas=tuple(zonas or ()), barrios=tuple(barrios or ()),
            tipos=tuple(tipos or ()), operacion=operacion, moneda=moneda,
            precio_min=precio_min, precio_max=precio_max, tipo_area=tipo_area,
            area_min_m2=area_min_m2, area_max_m2=area_max_m2,
            habitaciones_min=habitaciones_min, habitaciones_max=habitaciones_max,
            banos_min=banos_min, parqueaderos_min=parqueaderos_min,
            estratos=tuple(estratos or ()), fuente=fuente, id_busqueda=id_busqueda,
            disponibilidad=disponibilidad, requiere_revision=requiere_revision, orden=orden,
        )
    except (ValueError, TypeError) as exc:
        raise HTTPException(422, str(exc)) from exc


def crear_router(proveedor_servicio):
    """Registra las dos rutas una sola vez sobre cualquier aplicación FastAPI."""
    router = APIRouter()

    @router.get('/api/catalog')
    def catalog_api(state: str | None = None, search_url: str | None = None,
                    limit: int = Query(100, ge=1, le=1000),
                    offset: int = Query(0, ge=0),
                    filtros: FiltrosCatalogo = Depends(filtros_desde_query),
                    servicio: ServicioCatalogo = Depends(proveedor_servicio)):
        return consultar_catalogo(servicio, state=state, search_url=search_url,
                                  limit=limit, offset=offset, filtros=filtros)

    @router.get('/api/properties/{property_id}')
    def property_api(property_id: str, run_id: int | None = None,
                     servicio: ServicioCatalogo = Depends(proveedor_servicio)):
        return consultar_ficha(servicio, property_id, run_id)

    return router
