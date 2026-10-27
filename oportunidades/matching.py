"""Comparaciones determinísticas sobre Inmueble, sin acceso a captura o SQLite."""
from dataclasses import dataclass
from collections import Counter

from catalogo.modelos import Inmueble, Oferta, Operacion
from catalogo.geografia import resolver_barrio, normalizar_geografia
from .modelos import CRITERIOS, Necesidades
from .normalizacion import normalizar, normalizar_ciudad


@dataclass(frozen=True)
class Comprobacion:
    codigo: str
    criterio: str
    cumple: bool | None
    preferencia: bool = False


@dataclass(frozen=True)
class Coincidencia:
    inmueble: Inmueble
    oferta: Oferta | None
    cumple: tuple[str, ...]
    pendientes: tuple[str, ...]
    preferencias_cumplidas: tuple[str, ...]
    preferencias_pendientes: tuple[str, ...]
    preferencias_no_cumplidas: tuple[str, ...]

    @property
    def confirmada(self):
        return not self.pendientes


def evaluar(n: Necesidades, i: Inmueble):
    cumple, pendientes, preferidas, pref_pendientes, pref_no = [], [], [], [], []
    excluido = False
    comprobaciones = []

    def criterio(codigo, nombre, condicion, preferencia=False):
        nonlocal excluido
        comprobaciones.append(Comprobacion(codigo, nombre, condicion, preferencia))
        if preferencia:
            (pref_pendientes if condicion is None else preferidas if condicion else pref_no).append(nombre)
        elif condicion is None:
            pendientes.append(nombre)
        elif condicion:
            cumple.append(nombre)
        else:
            excluido = True

    operacion = Operacion.VENTA if n.operacion == 'compra' else Operacion.ARRIENDO
    oferta = next((o for o in i.ofertas if o.operacion == operacion), None)
    criterio('operacion', 'Operación: ' + n.operacion, True if oferta else False if i.ofertas else None)
    if oferta and oferta.moneda is not None and oferta.moneda != 'COP':
        criterio('presupuesto', 'Presupuesto máximo en COP: moneda incompatible', False)
    elif oferta is None or oferta.moneda is None or oferta.precio is None:
        criterio('presupuesto', 'Presupuesto máximo en COP (precio y moneda)', None)
    else:
        criterio('presupuesto', 'Presupuesto máximo en COP', oferta.precio <= n.presupuesto_max)
    criterio('tipo', 'Tipo: ' + n.tipo.value, i.tipo == n.tipo if i.tipo is not None else None)
    criterio('ciudad', 'Ciudad: ' + n.ciudad, normalizar_ciudad(i.ciudad) == normalizar_ciudad(n.ciudad) if i.ciudad else None)
    ubicaciones = []
    solicitudes_sin_resolver = []
    geo = i.geografia or normalizar_geografia(ciudad=i.ciudad, barrio=i.barrio, zona=i.zona)
    for campo, deseados, observado in (('barrio', n.barrios, i.barrio), ('zona', n.zonas, i.zona)):
        if deseados:
            if campo == 'barrio':
                entradas = [resolver_barrio(n.ciudad, v)[0] for v in deseados]
                solicitudes_sin_resolver.extend(v for v, b in zip(deseados, entradas) if b is None)
                ids = {b['id'] for b in entradas if b}
                condicion = (geo.barrio_id in ids if geo.barrio_id else None)
                # Una solicitud histórica desconocida tampoco confirma ni descarta.
                if condicion is False and any(b is None for b in entradas):
                    condicion = None
                ubicaciones.append(condicion)
            else:
                ubicaciones.append(normalizar(observado) in {normalizar(v) for v in deseados} if observado else None)
    ubicacion = True if True in ubicaciones else None if None in ubicaciones else False
    etiqueta_ubicacion = 'Barrio o zona de interés'
    if ubicacion is None and geo.motivos:
        etiqueta_ubicacion += ': ' + '; '.join(geo.motivos)
    if ubicacion is None and solicitudes_sin_resolver:
        etiqueta_ubicacion += '; solicitud sin equivalencia controlada: ' + ', '.join(solicitudes_sin_resolver)
    criterio('ubicacion', etiqueta_ubicacion, ubicacion)
    area = getattr(i, f'area_{n.tipo_area.value}_m2')
    valores = {'habitaciones_min': i.habitaciones, 'banos_min': i.banos,
               'parqueaderos_min': i.parqueaderos, 'area_min_m2': area,
               'area_max_m2': area, 'antiguedad_max': None}
    for campo, nombre in CRITERIOS.items():
        limite = getattr(n, campo)
        if limite is None:
            continue
        valor = valores[campo]
        condicion = None if valor is None else valor <= limite if campo in ('area_max_m2', 'antiguedad_max') else valor >= limite
        etiqueta = f'{nombre}: {limite}' + (f' m² ({n.tipo_area.value})' if campo.startswith('area_') else ' años' if campo == 'antiguedad_max' else '')
        criterio(campo, etiqueta, condicion, campo in n.preferencias)
    resultado = None if excluido else Coincidencia(i, oferta, tuple(cumple), tuple(pendientes), tuple(preferidas), tuple(pref_pendientes), tuple(pref_no))
    return resultado, tuple(comprobaciones)


def comparar(n: Necesidades, i: Inmueble) -> Coincidencia | None:
    return evaluar(n, i)[0]


def buscar(necesidades: Necesidades, catalogo, orden='coincidencia'):
    resultados = [r for i in catalogo if (r := comparar(necesidades, i)) is not None]
    return ordenar(resultados, orden)


def ordenar(resultados, orden):
    if orden == 'precio':
        return sorted(resultados, key=lambda r: (r.oferta is None or r.oferta.precio is None or r.oferta.moneda != 'COP',
                      r.oferta.precio if r.oferta and r.oferta.precio is not None and r.oferta.moneda == 'COP' else 0, r.inmueble.id_interno))
    if orden != 'coincidencia':
        raise ValueError('Orden desconocido')
    return sorted(resultados, key=lambda r: (not r.confirmada, len(r.pendientes),
                  -len(r.preferencias_cumplidas), r.inmueble.id_interno))


def diagnosticar(necesidades: Necesidades, catalogo, orden='coincidencia'):
    """Una evaluación por anuncio; desconocido conserva el candidato, fallo conocido excluye.

    Las etapas son acumulativas en orden fijo. Los motivos cuentan sobre todo
    el catálogo, y pueden solaparse: no se deben sumar como descartes únicos.
    """
    evaluaciones = [(i, *evaluar(necesidades, i)) for i in catalogo]
    resultados = ordenar([r for _, r, _ in evaluaciones if r is not None], orden)
    codigos = ['operacion', 'tipo', 'ciudad', 'ubicacion', 'presupuesto', *CRITERIOS]
    etiquetas = dict(operacion='Operación', tipo='Tipo de inmueble', ciudad='Ciudad',
                     ubicacion='Barrio o zona', presupuesto='Presupuesto en COP', **CRITERIOS)
    vivos = {i.id_interno for i, _, _ in evaluaciones}
    motivos, faltantes, descartes, etapas = Counter(), Counter(), [], []
    por_codigo = {codigo: {} for codigo in codigos}
    for i, _, pruebas in evaluaciones:
        fallos = []
        for p in pruebas:
            por_codigo[p.codigo][i.id_interno] = p
            if p.preferencia:
                continue
            if p.cumple is False:
                motivos[p.codigo] += 1
                fallos.append(p.criterio)
            elif p.cumple is None:
                faltantes[p.codigo] += 1
        if fallos:
            descartes.append({'id_interno': i.id_interno, 'id_original': i.origen.id_original, 'motivos': fallos})
    for codigo in codigos:
        pruebas = por_codigo[codigo]
        obligatorias = {k: p for k, p in pruebas.items() if not p.preferencia}
        # No hay criterios activos en un catálogo vacío; conservar los principales.
        if not obligatorias and (evaluaciones or codigo in CRITERIOS and getattr(necesidades, codigo) is None):
            continue
        if codigo in necesidades.preferencias:
            continue
        antes = len(vivos)
        vivos -= {k for k, p in obligatorias.items() if p.cumple is False}
        etapas.append({'codigo': codigo, 'criterio': etiquetas[codigo], 'antes': antes,
                       'descartados': antes - len(vivos), 'restantes': len(vivos),
                       'sin_dato': sum(obligatorias[k].cumple is None for k in vivos if k in obligatorias)})
    confirmadas = sum(r.confirmada for r in resultados)
    return {
        'total_catalogo': len(evaluaciones), 'compatibles': confirmadas,
        'pendientes': len(resultados) - confirmadas, 'total_resultados': len(resultados),
        'incompatibles': len(evaluaciones) - len(resultados), 'etapas': etapas,
        'motivos': [{'codigo': c, 'criterio': etiquetas[c], 'cantidad': motivos[c]} for c in codigos if motivos[c]],
        'datos_faltantes': [{'codigo': c, 'criterio': etiquetas[c], 'cantidad': faltantes[c]} for c in codigos if faltantes[c]],
        'descartes': descartes, 'resultados': resultados,
    }
