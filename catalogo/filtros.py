"""Contrato de consulta v0.1; no ejecuta búsquedas ni conoce almacenamiento."""

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from . import _validacion as validar
from .identidad import normalizar_fuente
from .modelos import Disponibilidad, Operacion, TipoArea, TipoInmueble


class OrdenCatalogo(StrEnum):
    ID = 'id'
    PRECIO_ASC = 'precio_asc'
    PRECIO_DESC = 'precio_desc'
    ULTIMA_VERIFICACION = 'ultima_verificacion_desc'


@dataclass(frozen=True, slots=True, kw_only=True)
class FiltrosCatalogo:
    texto: str | None = None
    ciudad: str | None = None
    zonas: tuple[str, ...] = ()
    barrios: tuple[str, ...] = ()
    tipos: tuple[TipoInmueble, ...] = ()
    operacion: Operacion | None = None
    moneda: str | None = None
    precio_min: Decimal | None = None
    precio_max: Decimal | None = None
    tipo_area: TipoArea = TipoArea.PUBLICADA
    area_min_m2: Decimal | None = None
    area_max_m2: Decimal | None = None
    habitaciones_min: int | None = None
    habitaciones_max: int | None = None
    banos_min: int | None = None
    parqueaderos_min: int | None = None
    estratos: tuple[int, ...] = ()
    fuente: str | None = None
    id_busqueda: str | None = None
    disponibilidad: Disponibilidad | None = None
    requiere_revision: bool | None = None
    orden: OrdenCatalogo = OrdenCatalogo.ID
    limite: int = 30
    desplazamiento: int = 0

    def __post_init__(self):
        for nombre in ('texto', 'ciudad', 'id_busqueda'):
            validar.texto(getattr(self, nombre), nombre)
        for nombre in ('zonas', 'barrios'):
            validar.tupla(getattr(self, nombre), str, nombre)
            for valor in getattr(self, nombre):
                validar.texto(valor, nombre)
        validar.tupla(self.tipos, TipoInmueble, 'tipos')
        validar.enumeracion(self.operacion, Operacion, 'operacion', opcional=True)
        validar.enumeracion(self.tipo_area, TipoArea, 'tipo_area')
        validar.enumeracion(self.disponibilidad, Disponibilidad, 'disponibilidad', opcional=True)
        validar.enumeracion(self.orden, OrdenCatalogo, 'orden')
        validar.moneda(self.moneda)
        for minimo, maximo in (('precio_min', 'precio_max'), ('area_min_m2', 'area_max_m2')):
            bajo, alto = getattr(self, minimo), getattr(self, maximo)
            validar.decimal_no_negativo(bajo, minimo)
            validar.decimal_no_negativo(alto, maximo)
            if bajo is not None and alto is not None and bajo > alto:
                raise ValueError(f'{minimo} no puede superar {maximo}')
        usa_precio = self.precio_min is not None or self.precio_max is not None
        ordena_precio = self.orden in (OrdenCatalogo.PRECIO_ASC, OrdenCatalogo.PRECIO_DESC)
        if (usa_precio or ordena_precio) and (self.operacion is None or self.moneda is None):
            raise ValueError('filtrar u ordenar por precio requiere operación y moneda')
        for nombre in ('habitaciones_min', 'habitaciones_max', 'banos_min', 'parqueaderos_min',
                       'desplazamiento'):
            validar.entero_no_negativo(getattr(self, nombre), nombre)
        if self.desplazamiento is None:
            raise ValueError('desplazamiento no puede ser None')
        if (self.habitaciones_min is not None and self.habitaciones_max is not None
                and self.habitaciones_min > self.habitaciones_max):
            raise ValueError('habitaciones_min no puede superar habitaciones_max')
        validar.tupla(self.estratos, int, 'estratos')
        if any(type(e) is not int or not 1 <= e <= 6 for e in self.estratos):
            raise ValueError('estratos debe contener enteros entre 1 y 6')
        if self.fuente is not None:
            object.__setattr__(self, 'fuente', normalizar_fuente(self.fuente))
        if self.id_busqueda is not None and self.fuente is None:
            raise ValueError('id_busqueda requiere fuente para identificar su ámbito')
        if self.requiere_revision is not None and type(self.requiere_revision) is not bool:
            raise TypeError('requiere_revision debe ser bool o None')
        if type(self.limite) is not int or not 1 <= self.limite <= 200:
            raise ValueError('limite debe estar entre 1 y 200')
