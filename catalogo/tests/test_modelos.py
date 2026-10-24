from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from catalogo.modelos import (
    Calidad, Disponibilidad, Inmueble, Oferta, Operacion, Origen,
    PresenciaBusqueda, TipoInmueble,
)


def origen(**valores):
    return Origen(fuente='portal', id_original='001', **valores)


def test_ficha_minima_preserva_desconocidos():
    ficha = Inmueble(origen=origen())
    assert ficha.titulo is None
    assert ficha.tipo is None
    assert ficha.habitaciones is None
    assert ficha.area_publicada_m2 is None
    assert ficha.ofertas == ()
    assert ficha.fotos == ()
    assert ficha.calidad == Calidad.DESCONOCIDA
    assert ficha.disponibilidad == Disponibilidad.DESCONOCIDA
    assert ficha.origen.ultima_extraccion is None


def test_oferta_dual_conserva_precios_y_monedas_independientes():
    venta = Oferta(operacion=Operacion.VENTA, precio=Decimal('500000000'), moneda='COP')
    arriendo = Oferta(operacion=Operacion.ARRIENDO, precio=Decimal('1500.50'), moneda='USD')
    ficha = Inmueble(origen=origen(), ofertas=(venta, arriendo))
    assert ficha.ofertas == (venta, arriendo)
    assert ficha.ofertas[1].precio == Decimal('1500.50')


def test_operacion_con_precio_o_moneda_desconocidos_no_infiere_valores():
    assert Oferta(operacion=Operacion.VENTA).precio is None
    assert Oferta(operacion=Operacion.ARRIENDO, precio=Decimal('1000')).moneda is None
    assert Oferta(operacion=Operacion.VENTA, moneda='COP').precio is None


def test_ficha_completa_con_procedencia_y_fechas_distintas():
    extraccion = datetime(2026, 10, 23, 8, tzinfo=timezone(timedelta(hours=-5)))
    verificacion = datetime(2026, 10, 24, 13, tzinfo=timezone.utc)
    ficha = Inmueble(
        origen=origen(
            tipo_original='Apartaestudio', operacion_original='Venta y Arriendo',
            ultima_extraccion=extraccion, ultima_verificacion=verificacion,
            busquedas=(PresenciaBusqueda(
                id_busqueda='zona-norte', nombre='Zona norte', url='https://portal.test/busqueda',
                disponibilidad=Disponibilidad.ACTIVO, ultima_verificacion=verificacion,
            ),),
        ),
        titulo='Apartaestudio', tipo=TipoInmueble.APARTAMENTO,
        descripcion='Descripción\ncompleta', ciudad='Bogotá', barrio='La Carolina',
        area_construida_m2=Decimal('55.5'), area_privada_m2=Decimal('50'),
        habitaciones=0, banos=1, parqueaderos=0, estrato=4,
        fotos=('https://portal.test/foto.jpg',), caracteristicas=('Ascensor',),
        calidad=Calidad.COMPLETA, requiere_revision=True,
    )
    assert ficha.origen.ultima_extraccion != ficha.origen.ultima_verificacion
    assert ficha.origen.actualizado_en_fuente is None
    assert ficha.origen.tipo_original == 'Apartaestudio'
    assert ficha.parqueaderos == 0
    assert ficha.requiere_revision


@pytest.mark.parametrize('campo', [
    'primera_observacion', 'ultima_verificacion', 'ultima_extraccion', 'actualizado_en_fuente',
])
def test_rechaza_fechas_sin_zona_horaria(campo):
    with pytest.raises(ValueError):
        origen(**{campo: datetime(2026, 10, 24)})


def test_verificacion_por_busqueda_exige_zona_horaria():
    with pytest.raises(ValueError):
        PresenciaBusqueda(id_busqueda='zona', ultima_verificacion=datetime(2026, 10, 24))


@pytest.mark.parametrize('estados,esperado', [
    ((), Disponibilidad.DESCONOCIDA),
    ((Disponibilidad.RETIRADO,), Disponibilidad.RETIRADO),
    ((Disponibilidad.RETIRADO, Disponibilidad.ACTIVO), Disponibilidad.ACTIVO),
    ((Disponibilidad.RETIRADO, Disponibilidad.POSIBLEMENTE_RETIRADO), Disponibilidad.POSIBLEMENTE_RETIRADO),
    ((Disponibilidad.RETIRADO, Disponibilidad.DESCONOCIDA), Disponibilidad.DESCONOCIDA),
])
def test_disponibilidad_agregada_no_confunde_ausencia_con_venta(estados, esperado):
    busquedas = tuple(PresenciaBusqueda(id_busqueda=str(i), disponibilidad=e) for i, e in enumerate(estados))
    assert Inmueble(origen=origen(busquedas=busquedas)).disponibilidad == esperado


def test_rechaza_busquedas_y_operaciones_repetidas():
    presencia = PresenciaBusqueda(id_busqueda='zona')
    with pytest.raises(ValueError):
        origen(busquedas=(presencia, presencia))
    oferta = Oferta(operacion=Operacion.VENTA)
    with pytest.raises(ValueError):
        Inmueble(origen=origen(), ofertas=(oferta, oferta))


@pytest.mark.parametrize('valor', ['-1', '0', 'NaN', 'Infinity', '-Infinity'])
def test_precio_rechaza_cero_negativos_y_no_finitos(valor):
    with pytest.raises(ValueError):
        Oferta(operacion=Operacion.VENTA, precio=Decimal(valor))


def test_precio_no_acepta_float_ni_moneda_ambigua():
    with pytest.raises(TypeError):
        Oferta(operacion=Operacion.VENTA, precio=1.1)
    with pytest.raises(ValueError):
        Oferta(operacion=Operacion.VENTA, moneda='$')


@pytest.mark.parametrize('valores', [
    {'area_publicada_m2': Decimal('0')}, {'area_privada_m2': Decimal('-1')},
    {'area_construida_m2': Decimal('NaN')}, {'habitaciones': -1}, {'banos': True},
    {'parqueaderos': 1.5}, {'estrato': 0}, {'estrato': 7}, {'titulo': ''},
    {'tipo': 'apartamento'}, {'calidad': 'completa'}, {'requiere_revision': 1},
    {'fotos': ['https://portal.test/foto.jpg']}, {'caracteristicas': ('',)},
    {'ofertas': ('venta',)},
])
def test_rechaza_atributos_invalidos(valores):
    with pytest.raises((TypeError, ValueError)):
        Inmueble(origen=origen(), **valores)


def test_modelo_y_colecciones_son_inmutables():
    ficha = Inmueble(origen=origen())
    with pytest.raises(FrozenInstanceError):
        ficha.titulo = 'Cambio'
    with pytest.raises(FrozenInstanceError):
        ficha.origen.fuente = 'otro'
