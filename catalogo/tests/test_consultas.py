"""Consultas de negocio sobre modelos en memoria, sin almacenamiento ni HTTP."""

from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal as D

import pytest

from catalogo.consultas import seleccionar
from catalogo.filtros import FiltrosCatalogo, OrdenCatalogo
from catalogo.modelos import (
    Disponibilidad as Estado, Inmueble, Oferta, Operacion as Op, Origen,
    PresenciaBusqueda, TipoArea, TipoInmueble as Tipo,
)
from catalogo.servicio import ServicioCatalogo


T1 = datetime(2026, 10, 20, tzinfo=timezone.utc)
T2 = datetime(2026, 10, 21, tzinfo=timezone.utc)
T3 = datetime(2026, 10, 24, tzinfo=timezone.utc)


@pytest.fixture
def fichas():
    def origen(id, extraida=None, verificada=None, estados=(Estado.ACTIVO, Estado.RETIRADO)):
        return Origen(
            fuente='portal', id_original=id, ultima_extraccion=extraida,
            ultima_verificacion=verificada,
            busquedas=(
                PresenciaBusqueda(id_busqueda='norte', disponibilidad=estados[0], ultima_verificacion=T1),
                PresenciaBusqueda(id_busqueda='centro', disponibilidad=estados[1], ultima_verificacion=T3),
            ),
        )
    return (
        Inmueble(
            origen=origen('a', T1, T3), titulo='Casa con TERRAZA', descripcion='Jardín amplio',
            tipo=Tipo.CASA, ciudad='Bogotá', zona='Norte', barrio='Usaquén',
            ofertas=(Oferta(operacion=Op.VENTA, precio=D('1000'), moneda='COP'),
                     Oferta(operacion=Op.ARRIENDO, precio=D('10'), moneda='USD')),
            area_publicada_m2=D('80'), area_construida_m2=D('90'), area_privada_m2=D('70'),
            habitaciones=0, banos=2, parqueaderos=1, estrato=5,
        ),
        Inmueble(
            origen=origen('b', T3, T1, (Estado.RETIRADO, Estado.ACTIVO)),
            tipo=Tipo.APARTAMENTO, ciudad='Medellín', zona='Sur', barrio='El Poblado',
            ofertas=(Oferta(operacion=Op.VENTA, precio=D('2000'), moneda='COP'),),
            area_publicada_m2=D('100'), habitaciones=3, banos=1, parqueaderos=0, estrato=4,
            requiere_revision=True,
        ),
        Inmueble(
            origen=origen('c', None, T2), tipo=Tipo.CASA,
            ofertas=(Oferta(operacion=Op.VENTA, precio=D('1000'), moneda='COP'),),
        ),
        Inmueble(
            origen=origen('d'), ciudad='Bogotá',
            ofertas=(Oferta(operacion=Op.VENTA, precio=D('500'), moneda='USD'),),
            area_publicada_m2=D('80'),
        ),
        Inmueble(origen=Origen(fuente='otro', id_original='e')),
        Inmueble(
            origen=origen('f'), ofertas=(Oferta(operacion=Op.VENTA, moneda='COP'),),
            area_publicada_m2=D('80'),
        ),
    )


def ids(fichas, **parametros):
    return [f.origen.id_original for f in seleccionar(fichas, FiltrosCatalogo(**parametros))]


@pytest.mark.parametrize('parametros,esperados', [
    ({'texto': 'terraza'}, {'a'}),
    ({'texto': 'JARDIN'}, {'a'}),
    ({'ciudad': ' BOGOTA '}, {'a', 'd'}),
    ({'zonas': ('sur', 'NORTE')}, {'a', 'b'}),
    ({'barrios': ('USAQUEN',)}, {'a'}),
    ({'tipos': (Tipo.CASA,)}, {'a', 'c'}),
    ({'habitaciones_min': 0, 'habitaciones_max': 0}, {'a'}),
    ({'habitaciones_min': 3}, {'b'}),
    ({'banos_min': 2}, {'a'}),
    ({'parqueaderos_min': 0}, {'a', 'b'}),
    ({'parqueaderos_min': 1}, {'a'}),
    ({'estratos': (4,)}, {'b'}),
    ({'requiere_revision': True}, {'b'}),
    ({'fuente': 'OTRO'}, {'e'}),
    ({'disponibilidad': Estado.DESCONOCIDA}, {'e'}),
    ({'disponibilidad': Estado.ACTIVO}, {'a', 'b', 'c', 'd', 'f'}),
    ({'fuente': 'portal', 'id_busqueda': 'norte', 'disponibilidad': Estado.RETIRADO}, {'b'}),
    ({'fuente': 'portal', 'id_busqueda': 'sin-busqueda'}, set()),
])
def test_filtros_individuales_y_desconocidos(fichas, parametros, esperados):
    assert set(ids(fichas, **parametros)) == esperados


def test_campos_en_and_listas_en_or_y_limites_inclusivos(fichas):
    assert ids(
        fichas, texto='terraza', ciudad='Bogotá', tipos=(Tipo.CASA, Tipo.OFICINA),
        zonas=('Norte', 'Sur'), operacion=Op.VENTA, moneda='COP',
        precio_min=D('1000'), precio_max=D('1000'),
        tipo_area=TipoArea.PRIVADA, area_min_m2=D('70'), area_max_m2=D('70'),
        habitaciones_min=0, habitaciones_max=0, banos_min=2, parqueaderos_min=1,
        disponibilidad=Estado.ACTIVO,
    ) == ['a']
    assert ids(fichas, ciudad='Bogotá', habitaciones_min=1) == []


def test_doble_oferta_no_mezcla_precio_operacion_ni_moneda(fichas):
    assert ids(fichas, operacion=Op.ARRIENDO, moneda='USD', precio_max=D('10')) == ['a']
    assert ids(fichas, operacion=Op.ARRIENDO, moneda='COP', precio_max=D('10')) == []
    assert ids(fichas, operacion=Op.VENTA, moneda='USD', precio_max=D('10')) == []
    assert set(ids(fichas, moneda='USD')) == {'a', 'd'}
    assert ids(fichas, operacion=Op.VENTA, moneda='COP', precio_max=D('0')) == []


def test_area_no_sustituye_una_clase_por_otra(fichas):
    assert ids(fichas, tipo_area=TipoArea.CONSTRUIDA, area_min_m2=D('90')) == ['a']
    assert ids(fichas, tipo_area=TipoArea.PRIVADA, area_min_m2=D('80')) == []


@pytest.mark.parametrize('orden', [OrdenCatalogo.PRECIO_ASC, OrdenCatalogo.PRECIO_DESC])
def test_precio_ordenado_con_empates_y_desconocidos_al_final(fichas, orden):
    iguales = sorted((fichas[0], fichas[2]), key=lambda f: f.id_interno)
    esperados = iguales + [fichas[1], fichas[5]]
    if orden == OrdenCatalogo.PRECIO_DESC:
        esperados = [fichas[1]] + iguales + [fichas[5]]
    resultado = seleccionar(fichas, FiltrosCatalogo(operacion=Op.VENTA, moneda='COP', orden=orden))
    assert resultado == esperados
    assert seleccionar(tuple(reversed(fichas)), FiltrosCatalogo(
        operacion=Op.VENTA, moneda='COP', orden=orden)) == resultado


@pytest.mark.parametrize('orden', [OrdenCatalogo.AREA_ASC, OrdenCatalogo.AREA_DESC])
def test_area_ordenada_con_empates_y_desconocidos_al_final(fichas, orden):
    ochenta = sorted((fichas[0], fichas[3], fichas[5]), key=lambda f: f.id_interno)
    desconocidos = sorted((fichas[2], fichas[4]), key=lambda f: f.id_interno)
    conocidos = ochenta + [fichas[1]] if orden == OrdenCatalogo.AREA_ASC else [fichas[1]] + ochenta
    assert seleccionar(fichas, FiltrosCatalogo(orden=orden)) == conocidos + desconocidos


def test_actualizacion_y_verificacion_no_son_la_misma_fecha(fichas):
    actualizacion = ids(fichas, orden=OrdenCatalogo.ACTUALIZACION_DESC)
    verificacion = ids(fichas, orden=OrdenCatalogo.ULTIMA_VERIFICACION)
    assert actualizacion[:2] == ['b', 'a']
    assert verificacion[:3] == ['a', 'c', 'b']
    assert ids(fichas, orden=OrdenCatalogo.ACTUALIZACION_ASC)[:2] == ['a', 'b']


def test_verificacion_en_busqueda_seleccionada(fichas):
    cambiada = replace(fichas[1], origen=replace(
        fichas[1].origen, busquedas=(PresenciaBusqueda(
            id_busqueda='norte', disponibilidad=Estado.RETIRADO, ultima_verificacion=T2),),
    ))
    assert ids((fichas[0], cambiada), fuente='portal', id_busqueda='norte',
               orden=OrdenCatalogo.ULTIMA_VERIFICACION) == ['b', 'a']


def test_paginacion_consistente_total_y_deduplicacion_por_identidad(fichas):
    class Repositorio:
        def listar(self):
            return fichas + (fichas[0], fichas[0])
    servicio = ServicioCatalogo(Repositorio())
    paginas = [servicio.consultar(FiltrosCatalogo(limite=2, desplazamiento=offset))
               for offset in (0, 2, 4, 6)]
    assert all(p['total'] == 6 for p in paginas)
    resultado = [f.id_interno for p in paginas for f in p['items']]
    assert resultado == sorted(f.id_interno for f in fichas)
    assert len(set(resultado)) == 6
    assert paginas[-1]['items'] == []
    assert servicio.consultar(FiltrosCatalogo(ciudad='sin coincidencias'))['total'] == 0


def test_orden_descendente_no_invierte_desempates(fichas):
    ordenadas = seleccionar(fichas, FiltrosCatalogo(
        tipo_area=TipoArea.PRIVADA, orden=OrdenCatalogo.AREA_DESC))
    assert ordenadas[0] == fichas[0]
    assert [f.id_interno for f in ordenadas[1:]] == sorted(f.id_interno for f in fichas[1:])
