from decimal import Decimal

import pytest

from catalogo.filtros import FiltrosCatalogo, OrdenCatalogo
from catalogo.modelos import Disponibilidad, Operacion, TipoArea, TipoInmueble


def test_filtros_vacios_no_imponen_disponibilidad_ni_operacion():
    filtros = FiltrosCatalogo()
    assert filtros.disponibilidad is None
    assert filtros.operacion is None
    assert filtros.limite == 30
    assert filtros.desplazamiento == 0
    assert filtros.orden == OrdenCatalogo.ID


def test_consulta_completa_de_v01():
    filtros = FiltrosCatalogo(
        texto='terraza', ciudad='Bogotá', zonas=('Norte',), barrios=('La Carolina', 'Usaquén'),
        tipos=(TipoInmueble.APARTAMENTO, TipoInmueble.CASA),
        operacion=Operacion.VENTA, moneda='COP',
        precio_min=Decimal('300000000'), precio_max=Decimal('600000000'),
        tipo_area=TipoArea.PRIVADA, area_min_m2=Decimal('80'), area_max_m2=Decimal('150'),
        habitaciones_min=2, habitaciones_max=4, banos_min=2, parqueaderos_min=1,
        estratos=(4, 5, 6), fuente=' PORTAL ', id_busqueda='norte',
        disponibilidad=Disponibilidad.ACTIVO, requiere_revision=False,
        orden=OrdenCatalogo.PRECIO_ASC, limite=50, desplazamiento=50,
    )
    assert filtros.fuente == 'portal'
    assert filtros.tipo_area == TipoArea.PRIVADA
    assert filtros.precio_min == Decimal('300000000')


@pytest.mark.parametrize('valores', [
    {'precio_min': Decimal('100')},
    {'precio_max': Decimal('100'), 'moneda': 'COP'},
    {'precio_min': Decimal('100'), 'operacion': Operacion.ARRIENDO},
    {'orden': OrdenCatalogo.PRECIO_ASC},
    {'orden': OrdenCatalogo.PRECIO_DESC, 'moneda': 'COP'},
])
def test_precio_requiere_operacion_y_moneda_para_no_mezclar_ofertas(valores):
    with pytest.raises(ValueError):
        FiltrosCatalogo(**valores)


def test_limites_inclusivos_iguales_y_cero_son_validos():
    filtros = FiltrosCatalogo(
        operacion=Operacion.ARRIENDO, moneda='COP', precio_min=Decimal('0'),
        precio_max=Decimal('0'), area_min_m2=Decimal('50'), area_max_m2=Decimal('50'),
        habitaciones_min=0, habitaciones_max=0, parqueaderos_min=0,
    )
    assert filtros.precio_min == filtros.precio_max


@pytest.mark.parametrize('valores', [
    {'precio_min': Decimal('200'), 'precio_max': Decimal('100'), 'operacion': Operacion.VENTA, 'moneda': 'COP'},
    {'area_min_m2': Decimal('100'), 'area_max_m2': Decimal('50')},
    {'habitaciones_min': 3, 'habitaciones_max': 1},
    {'area_min_m2': Decimal('-1')}, {'area_max_m2': Decimal('Infinity')},
    {'precio_min': Decimal('NaN')}, {'area_min_m2': 50.5},
    {'habitaciones_min': True}, {'banos_min': -1}, {'parqueaderos_min': 0.5},
    {'limite': 0}, {'limite': 201}, {'limite': True},
    {'desplazamiento': -1}, {'desplazamiento': None},
    {'moneda': 'cop'}, {'id_busqueda': 'norte'},
    {'tipos': ('apartamento',)}, {'zonas': ('',)}, {'barrios': ['Norte']},
    {'operacion': 'venta'}, {'tipo_area': 'privada'}, {'orden': 'precio'},
    {'disponibilidad': 'activo'}, {'estratos': (True,)}, {'estratos': (7,)},
    {'requiere_revision': 1}, {'texto': '   '},
])
def test_rechaza_consultas_ambiguas_o_invalidas(valores):
    with pytest.raises((ValueError, TypeError)):
        FiltrosCatalogo(**valores)
