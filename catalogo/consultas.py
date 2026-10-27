"""Filtrado en memoria del modelo común, sin HTTP ni conocimiento de SQLite."""

import unicodedata
from .geografia import normalizar_ciudad, resolver_barrio

from .filtros import FiltrosCatalogo, OrdenCatalogo
from .modelos import TipoArea


def _texto(valor):
    limpio = unicodedata.normalize('NFD', (valor or '').strip().casefold())
    return ''.join(c for c in limpio if not unicodedata.combining(c))


def _en_rango(valor, minimo, maximo):
    if minimo is None and maximo is None:
        return True
    return valor is not None and (minimo is None or valor >= minimo) and (maximo is None or valor <= maximo)


def ofertas_compatibles(inmueble, filtros):
    return tuple(o for o in inmueble.ofertas
                 if (filtros.operacion is None or o.operacion == filtros.operacion)
                 and (filtros.moneda is None or o.moneda == filtros.moneda)
                 and _en_rango(o.precio, filtros.precio_min, filtros.precio_max))


def _area(inmueble, filtros):
    return getattr(inmueble, {
        TipoArea.PUBLICADA: 'area_publicada_m2',
        TipoArea.CONSTRUIDA: 'area_construida_m2',
        TipoArea.PRIVADA: 'area_privada_m2',
    }[filtros.tipo_area])


def _presencia(inmueble, filtros):
    return next((p for p in inmueble.origen.busquedas if p.id_busqueda == filtros.id_busqueda), None)


def _coincide(inmueble, filtros):
    if filtros.texto and not any(
        _texto(filtros.texto) in _texto(v)
        for v in (inmueble.titulo, inmueble.descripcion, inmueble.origen.id_original)
    ):
        return False
    if filtros.ciudad and normalizar_ciudad(filtros.ciudad) != normalizar_ciudad(inmueble.ciudad):
        return False
    for campo, opciones in (('zona', filtros.zonas), ('barrio', filtros.barrios)):
        if campo == 'barrio' and opciones and inmueble.geografia:
            ids = {b['id'] for o in opciones if (b := resolver_barrio(inmueble.ciudad, o)[0])}
            if inmueble.geografia.barrio_id not in ids:
                return False
            continue
        if opciones and _texto(getattr(inmueble, campo)) not in {_texto(o) for o in opciones}:
            return False
    if filtros.tipos and inmueble.tipo not in filtros.tipos:
        return False
    if filtros.fuente and inmueble.origen.fuente != filtros.fuente:
        return False
    presencia = _presencia(inmueble, filtros) if filtros.id_busqueda is not None else None
    if filtros.id_busqueda is not None and presencia is None:
        return False
    estado = presencia.disponibilidad if presencia else inmueble.disponibilidad
    if filtros.disponibilidad is not None and estado != filtros.disponibilidad:
        return False
    if filtros.requiere_revision is not None and inmueble.requiere_revision != filtros.requiere_revision:
        return False
    usa_oferta = (filtros.operacion is not None or filtros.moneda is not None
                  or filtros.precio_min is not None or filtros.precio_max is not None)
    if usa_oferta and not ofertas_compatibles(inmueble, filtros):
        return False
    if not _en_rango(_area(inmueble, filtros), filtros.area_min_m2, filtros.area_max_m2):
        return False
    if not _en_rango(inmueble.habitaciones, filtros.habitaciones_min, filtros.habitaciones_max):
        return False
    if not _en_rango(inmueble.banos, filtros.banos_min, None):
        return False
    if not _en_rango(inmueble.parqueaderos, filtros.parqueaderos_min, None):
        return False
    return not filtros.estratos or inmueble.estrato in filtros.estratos


def _valor_orden(inmueble, filtros):
    if filtros.orden in (OrdenCatalogo.PRECIO_ASC, OrdenCatalogo.PRECIO_DESC):
        ofertas = ofertas_compatibles(inmueble, filtros)
        return ofertas[0].precio if ofertas else None
    if filtros.orden in (OrdenCatalogo.AREA_ASC, OrdenCatalogo.AREA_DESC):
        return _area(inmueble, filtros)
    if filtros.orden == OrdenCatalogo.ULTIMA_VERIFICACION:
        if filtros.id_busqueda is not None:
            presencia = _presencia(inmueble, filtros)
            return presencia.ultima_verificacion if presencia else None
        return inmueble.origen.ultima_verificacion
    return inmueble.origen.ultima_extraccion


def seleccionar(inmuebles, filtros: FiltrosCatalogo, *, id_original_primero=False):
    """Una fila por UUID; empates por UUID ascendente y desconocidos al final."""
    unicos = {}
    for inmueble in inmuebles:
        unicos.setdefault(inmueble.id_interno, inmueble)
    coincidentes = [i for i in unicos.values() if _coincide(i, filtros)]
    coincidentes.sort(key=lambda i: i.id_interno)
    if filtros.orden == OrdenCatalogo.ID:
        if id_original_primero:
            coincidentes.sort(key=lambda i: (i.origen.id_original, i.id_interno))
        return coincidentes
    conocidos, desconocidos = [], []
    for inmueble in coincidentes:
        valor = _valor_orden(inmueble, filtros)
        if valor is None:
            desconocidos.append(inmueble)
        else:
            conocidos.append((inmueble, valor))
    descendente = filtros.orden in (
        OrdenCatalogo.PRECIO_DESC, OrdenCatalogo.AREA_DESC,
        OrdenCatalogo.ACTUALIZACION_DESC, OrdenCatalogo.ULTIMA_VERIFICACION,
    )
    conocidos.sort(key=lambda par: par[1], reverse=descendente)
    return [i for i, _ in conocidos] + desconocidos


def paginar(items, limite, desplazamiento):
    inicio = max(0, desplazamiento)
    pagina = items[inicio:] if limite < 0 else items[inicio:inicio + limite]
    return {'total': len(items), 'items': pagina, 'limit': limite, 'offset': desplazamiento}
