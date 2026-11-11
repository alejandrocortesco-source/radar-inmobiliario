"""Similitud explicable entre publicaciones; nunca decide identidad física."""
from dataclasses import asdict, replace
from hashlib import sha256
from decimal import Decimal
import json
import re
from collections import defaultdict

from .geografia import normalizar, normalizar_ciudad

VERSION = 'identificacion-1'
PESOS = {'ciudad': 5, 'operacion': 5, 'tipo': 5, 'barrio': 10,
         'direccion': 10, 'edificio': 5, 'unidad': 15, 'ubicacion': 5,
         'area': 15, 'habitaciones': 7, 'banos': 5, 'parqueaderos': 5,
         'estrato': 3, 'precio': 3, 'anunciante': 2}
TOLERANCIA_AREA = Decimal('0.03')
TOLERANCIA_PRECIO = Decimal('0.05')
TOLERANCIA_COORDENADAS = Decimal('0.0005')
UMBRAL = 35


def huella(datos):
    return sha256(json.dumps(datos, default=str, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def hechos(i):
    d = asdict(replace(i, inmueble_id=None, publicaciones=()))
    for k in ('inmueble_id', 'publicaciones'):
        d.pop(k, None)
    # Fechas de presencia y categorías de ejecución no alteran similitud.
    d['origen'] = {k: d['origen'][k] for k in ('fuente', 'id_original', 'url')}
    return d


def unidad(direccion):
    m = re.search(r'\b(?:apartamento|apto|unidad|interior)\.?\s*(?:(?:no|nro|numero)\.?\s*)?[:#-]?\s*([a-z0-9-]*\d[a-z0-9-]*)\b', normalizar(direccion))
    return m.group(1) if m else None


def comparar(a, b):
    favor, contra, falta = [], [], []
    puntos = 0

    def dato(campo, x, y, igual=None):
        nonlocal puntos
        if x is None or y is None or x == '' or y == '':
            falta.append(campo)
        elif (x == y if igual is None else igual):
            favor.append(campo)
            puntos += PESOS[campo]
        else:
            contra.append(campo)

    dato('ciudad', normalizar_ciudad(a.ciudad), normalizar_ciudad(b.ciudad))
    oa, ob = {o.operacion for o in a.ofertas}, {o.operacion for o in b.ofertas}
    dato('operacion', oa or None, ob or None, bool(oa & ob))
    for k in ('tipo', 'habitaciones', 'banos', 'parqueaderos', 'estrato'):
        dato(k, getattr(a, k), getattr(b, k))
    for k in ('barrio', 'edificio', 'direccion', 'anunciante'):
        dato(k, normalizar(getattr(a, k)), normalizar(getattr(b, k)))
    dato('unidad', unidad(a.direccion), unidad(b.direccion))
    areas = [(getattr(a, f'area_{t}_m2'), getattr(b, f'area_{t}_m2')) for t in ('construida', 'privada', 'publicada')]
    comunes = [(x, y) for x, y in areas if x is not None and y is not None]
    dato('area', comunes or None, comunes or None,
         all(abs(x-y)/max(x,y) <= TOLERANCIA_AREA for x,y in comunes))
    precisas = (a.ubicacion_aproximada is False and b.ubicacion_aproximada is False
                and all(v is not None for v in (a.latitud, a.longitud, b.latitud, b.longitud)))
    dato('ubicacion', True if precisas else None, True if precisas else None,
         bool(precisas and abs(a.latitud-b.latitud) <= TOLERANCIA_COORDENADAS and abs(a.longitud-b.longitud) <= TOLERANCIA_COORDENADAS))
    precios = [(x.precio, y.precio) for x in a.ofertas for y in b.ofertas
               if x.operacion == y.operacion and x.precio is not None and y.precio is not None]
    dato('precio', precios or None, precios or None,
         all(abs(x-y)/max(x,y) <= TOLERANCIA_PRECIO for x,y in precios))
    return {'version': VERSION, 'a': a.id_interno, 'b': b.id_interno,
            'huella': huella([VERSION, hechos(a), hechos(b)]),
            'datos': [hechos(a), hechos(b)], 'puntuacion': puntos,
            'favor': favor, 'contradicciones': contra, 'faltantes': falta,
            'advertencias': ['Similitud, no probabilidad. Dirección o coordenadas pueden identificar solo el edificio.',
                             'Los códigos de portales no se comparan. Sin identificación de unidad, verificar apartamentos similares.']}


def candidatos(items, modificados):
    """Bloques ciudad/tipo/operación y barrio, edificio, dirección o área vecina.

    Nunca producto cartesiano del catálogo. Desconocidos sin bloqueo quedan fuera.
    """
    indice = defaultdict(set)
    por_id = {i.id_interno: i for i in items}
    claves = {}
    for i in items:
        ks = []
        if i.ciudad and i.tipo and i.ofertas:
            for o in i.ofertas:
                base = (normalizar_ciudad(i.ciudad), i.tipo, o.operacion)
                ks.extend(base + (k, normalizar(getattr(i, k))) for k in ('barrio', 'edificio', 'direccion') if getattr(i, k))
                for t in ('construida', 'privada', 'publicada'):
                    v = getattr(i, f'area_{t}_m2')
                    if v:
                        ks.extend(base + (t, n) for n in range(int(v // 10)-1, int(v // 10)+2))
        claves[i.id_interno] = ks
        for k in ks:
            indice[k].add(i.id_interno)
    vistos = set()
    for iid in sorted(modificados):
        for otro in sorted(set().union(*(indice[k] for k in claves.get(iid, ())))):
            par = tuple(sorted((iid, otro)))
            if iid == otro or par in vistos or por_id[iid].origen.fuente == por_id[otro].origen.fuente:
                continue
            vistos.add(par)
            yield comparar(*(por_id[k] for k in par))


def agrupar(items):
    """Representante estable: menor UUID entre los elegibles, sin mezclar fichas."""
    grupos = {}
    for i in sorted(items, key=lambda i: i.id_interno):
        grupos.setdefault(i.inmueble_id or i.id_interno, i)
    return list(grupos.values())
