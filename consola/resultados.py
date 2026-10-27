"""Orden y página del matching; reutiliza paginación y formatos del catálogo."""
from urllib.parse import urlencode

from catalogo.consultas import paginar
from catalogo.filtros import FiltrosCatalogo
from .presentacion import area_disponible, tarjeta
from oportunidades.normalizacion import normalizar

COLUMNAS = (
    ('estado', 'Coincidencia'), ('ubicacion', 'Barrio / ubicación'), ('tipo', 'Tipo'),
    ('precio', 'Precio'), ('area', 'Área (m²)'), ('habitaciones', 'Hab.'),
    ('banos', 'Baños'), ('parqueaderos', 'Parq.'), ('fuente', 'Fuente'), ('publicacion', 'Publicación'),
)
ORDENES = {'coincidencia', 'precio'} | {c + '_' + d for c, _ in COLUMNAS for d in ('asc', 'desc')}


def ordenar_resultados(resultados, orden):
    if orden == 'coincidencia':
        return list(resultados)  # Ya ordenados por el motor, sin cambiar los requisitos.
    if orden == 'precio':
        orden = 'precio_asc'
    if orden not in ORDENES:
        raise ValueError('Orden de matching desconocido')
    campo, direccion = orden.rsplit('_', 1)

    def valor(r):
        i = r.inmueble
        if campo == 'estado':
            return not r.confirmada
        if campo == 'ubicacion':
            return normalizar(i.barrio or i.zona or i.ciudad) or None
        if campo == 'tipo':
            return i.tipo.value if i.tipo else None
        if campo == 'precio':
            return r.oferta.precio if r.oferta and r.oferta.moneda == 'COP' else None
        if campo == 'area':
            return area_disponible(i)[0]
        if campo == 'fuente':
            return normalizar(i.origen.fuente)
        if campo == 'publicacion':
            return i.origen.url
        return getattr(i, campo)

    items = sorted(resultados, key=lambda r: r.inmueble.id_interno)
    conocidos = [r for r in items if valor(r) is not None]
    desconocidos = [r for r in items if valor(r) is None]
    return sorted(conocidos, key=valor, reverse=direccion == 'desc') + desconocidos


def presentar_resultados(oportunidad, informe, query=None, independiente=False, orden=None):
    query = query or {}
    orden = orden or query.get('orden' if independiente else 'match_orden', 'coincidencia')
    if orden not in ORDENES:
        orden = 'coincidencia'
    if orden == 'precio':
        orden = 'precio_asc'
    try:
        limite = int(query.get('match_limit', 24))
        offset = int(query.get('match_offset', 0))
    except (ValueError, TypeError):
        limite, offset = 24, 0
    limite = limite if limite in (12, 24, 48) else 24
    items = ordenar_resultados(informe['resultados'], orden)
    maximo = max(0, (len(items) - 1) // limite * limite)
    offset = min(max(0, offset // limite * limite), maximo)
    pagina = paginar(items, limite, offset)
    pares = list(query.multi_items()) if hasattr(query, 'multi_items') else list(query.items())

    def url(**cambios):
        valores = {}
        if independiente:
            valores.update(orden=orden)
        else:
            valores.update(oportunidad=oportunidad.id, match_orden=orden)
        valores.update(match_limit=limite, match_offset=offset)
        valores.update(cambios)
        path = f'/consola/oportunidades/{oportunidad.id}/coincidencias' if independiente else '/consola/'
        existentes = [(k, v) for k, v in pares if k not in valores and k != 'guardada']
        return path + '?' + urlencode(existentes + list(valores.items())) + '#matching-resultados'

    orden_key = 'orden' if independiente else 'match_orden'
    # La ficha existente admite regreso a la Consola; mantiene la selección y la página.
    regreso = [(k, v) for k, v in pares if k not in {'oportunidad', 'match_orden', 'match_limit', 'match_offset', 'guardada'}
               and not (independiente and k == 'orden')]
    volver = '/consola/?' + urlencode(regreso + list(dict(oportunidad=oportunidad.id, match_orden=orden,
                                         match_limit=limite, match_offset=offset).items())) + '#matching-resultados'
    filtros = FiltrosCatalogo()
    columnas = []
    actual = 'precio_asc' if orden == 'precio' else orden
    for campo, nombre in COLUMNAS:
        activo = actual.startswith(campo + '_')
        direccion = 'desc' if actual == campo + '_asc' else 'asc'
        columnas.append(dict(campo=campo, nombre=nombre, activo=activo,
            aria_sort=('ascending' if actual.endswith('_asc') else 'descending') if activo else None,
            url=url(**{orden_key: campo + '_' + direccion, 'match_offset': 0})))
    return dict(orden=orden, columnas_match=columnas, pagina_match=pagina,
        resultados=[(r, tarjeta(r.inmueble, filtros, volver)) for r in pagina['items']],
        match_primero=offset + 1 if items else 0, match_ultimo=min(offset + limite, len(items)),
        match_pagina=offset // limite + 1, match_paginas=max(1, (len(items) + limite - 1) // limite),
        match_anterior=url(match_offset=offset - limite) if offset else None,
        match_siguiente=url(match_offset=offset + limite) if offset + limite < len(items) else None,
        match_orden_param=orden_key, match_form_action=f'/consola/oportunidades/{oportunidad.id}/coincidencias' if independiente else '/consola/',
        match_extras=[(k, v) for k, v in pares if k not in {orden_key, 'oportunidad', 'match_limit', 'match_offset', 'guardada'}],
        match_limite_urls={n: url(match_limit=n, match_offset=0) for n in (12, 24, 48)})
