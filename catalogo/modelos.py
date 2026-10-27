"""Datos comunes; None significa desconocido, nunca cero ni una inferencia."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from . import _validacion as validar
from .identidad import identificar_inmueble, normalizar_fuente, normalizar_id_original
from .geografia import Geografia


class Operacion(StrEnum):
    VENTA = 'venta'
    ARRIENDO = 'arriendo'


class TipoInmueble(StrEnum):
    APARTAMENTO = 'apartamento'
    CASA = 'casa'
    OFICINA = 'oficina'
    CONSULTORIO = 'consultorio'
    LOCAL = 'local'
    BODEGA = 'bodega'
    LOTE = 'lote'
    FINCA = 'finca'
    OTRO = 'otro'


class Disponibilidad(StrEnum):
    ACTIVO = 'activo'
    POSIBLEMENTE_RETIRADO = 'posiblemente_retirado'
    RETIRADO = 'retirado'
    DESCONOCIDA = 'desconocida'


class Calidad(StrEnum):
    COMPLETA = 'completa'
    PARCIAL = 'parcial'
    DESCONOCIDA = 'desconocida'


class TipoArea(StrEnum):
    PUBLICADA = 'publicada'
    CONSTRUIDA = 'construida'
    PRIVADA = 'privada'


@dataclass(frozen=True, slots=True, kw_only=True)
class Oferta:
    operacion: Operacion
    precio: Decimal | None = None
    moneda: str | None = None

    def __post_init__(self):
        validar.enumeracion(self.operacion, Operacion, 'operacion')
        validar.decimal_no_negativo(self.precio, 'precio')
        if self.precio is not None and self.precio == 0:
            raise ValueError('precio debe ser positivo o None')
        validar.moneda(self.moneda)


@dataclass(frozen=True, slots=True, kw_only=True)
class PresenciaBusqueda:
    """Disponibilidad de un anuncio en una búsqueda; retirado no significa vendido."""

    id_busqueda: str
    nombre: str | None = None
    url: str | None = None
    disponibilidad: Disponibilidad = Disponibilidad.DESCONOCIDA
    ultima_verificacion: datetime | None = None

    def __post_init__(self):
        if not isinstance(self.id_busqueda, str) or not self.id_busqueda.strip():
            raise ValueError('id_busqueda debe ser texto no vacío')
        validar.texto(self.nombre, 'nombre')
        validar.texto(self.url, 'url')
        validar.enumeracion(self.disponibilidad, Disponibilidad, 'disponibilidad')
        validar.fecha(self.ultima_verificacion, 'ultima_verificacion')


@dataclass(frozen=True, slots=True, kw_only=True)
class Origen:
    fuente: str
    id_original: str
    url: str | None = None
    tipo_original: str | None = None
    operacion_original: str | None = None
    primera_observacion: datetime | None = None
    ultima_verificacion: datetime | None = None
    ultima_extraccion: datetime | None = None
    actualizado_en_fuente: datetime | None = None
    busquedas: tuple[PresenciaBusqueda, ...] = ()

    def __post_init__(self):
        object.__setattr__(self, 'fuente', normalizar_fuente(self.fuente))
        object.__setattr__(self, 'id_original', normalizar_id_original(self.id_original))
        for nombre in ('url', 'tipo_original', 'operacion_original'):
            validar.texto(getattr(self, nombre), nombre)
        for nombre in ('primera_observacion', 'ultima_verificacion', 'ultima_extraccion',
                       'actualizado_en_fuente'):
            validar.fecha(getattr(self, nombre), nombre)
        validar.tupla(self.busquedas, PresenciaBusqueda, 'busquedas')
        if len({b.id_busqueda for b in self.busquedas}) != len(self.busquedas):
            raise ValueError('busquedas contiene identificadores repetidos')


@dataclass(frozen=True, slots=True, kw_only=True)
class Inmueble:
    """Un anuncio por origen; no presupone equivalencia física entre anuncios.

    Las áreas se expresan en m² según la convención del mercado local.
    El adaptador no modifica los valores ni las unidades de la captura original.
    ofertas=() indica operación desconocida. Una oferta dual tiene dos Oferta.
    Los adaptadores geográficos aportan barrio canónico confirmado o None,
    edificio independiente y originales/evidencias en geografia.
    """

    origen: Origen
    titulo: str | None = None
    descripcion: str | None = None
    tipo: TipoInmueble | None = None
    ofertas: tuple[Oferta, ...] = ()
    ciudad: str | None = None
    zona: str | None = None
    barrio: str | None = None
    geografia: Geografia | None = None
    edificio: str | None = None
    direccion: str | None = None
    latitud: Decimal | None = None
    longitud: Decimal | None = None
    ubicacion_aproximada: bool | None = None
    portal_map_url: str | None = None
    map_url: str | None = None
    area_publicada_m2: Decimal | None = None
    area_construida_m2: Decimal | None = None
    area_privada_m2: Decimal | None = None
    habitaciones: int | None = None
    banos: int | None = None
    parqueaderos: int | None = None
    estrato: int | None = None
    fotos: tuple[str, ...] = ()
    caracteristicas: tuple[str, ...] = ()
    calidad: Calidad = Calidad.DESCONOCIDA
    requiere_revision: bool = False

    def __post_init__(self):
        if not isinstance(self.origen, Origen):
            raise TypeError('origen debe ser Origen')
        if self.geografia is not None and not isinstance(self.geografia, Geografia):
            raise TypeError('geografia debe ser Geografia o None')
        for nombre in ('titulo', 'descripcion', 'ciudad', 'zona', 'barrio', 'edificio', 'direccion',
                       'portal_map_url', 'map_url'):
            validar.texto(getattr(self, nombre), nombre)
        for nombre, limite in (('latitud', 90), ('longitud', 180)):
            valor = getattr(self, nombre)
            if valor is not None:
                if not isinstance(valor, Decimal):
                    raise TypeError(f'{nombre} debe ser Decimal o None')
                if not valor.is_finite() or not -limite <= valor <= limite:
                    raise ValueError(f'{nombre} fuera del intervalo válido')
        if self.ubicacion_aproximada is not None and not isinstance(self.ubicacion_aproximada, bool):
            raise TypeError('ubicacion_aproximada debe ser bool o None')
        validar.enumeracion(self.tipo, TipoInmueble, 'tipo', opcional=True)
        validar.enumeracion(self.calidad, Calidad, 'calidad')
        validar.tupla(self.ofertas, Oferta, 'ofertas')
        if len({o.operacion for o in self.ofertas}) != len(self.ofertas):
            raise ValueError('solo se admite una oferta por operación')
        for nombre in ('area_publicada_m2', 'area_construida_m2', 'area_privada_m2'):
            valor = getattr(self, nombre)
            validar.decimal_no_negativo(valor, nombre)
            if valor is not None and valor == 0:
                raise ValueError(f'{nombre} debe ser positivo o None')
        for nombre in ('habitaciones', 'banos', 'parqueaderos'):
            validar.entero_no_negativo(getattr(self, nombre), nombre)
        if self.estrato is not None and (type(self.estrato) is not int or not 1 <= self.estrato <= 6):
            raise ValueError('estrato debe estar entre 1 y 6 o ser None')
        for nombre in ('fotos', 'caracteristicas'):
            valores = getattr(self, nombre)
            validar.tupla(valores, str, nombre)
            for valor in valores:
                validar.texto(valor, nombre)
        if type(self.requiere_revision) is not bool:
            raise TypeError('requiere_revision debe ser bool')

    @property
    def id_interno(self) -> str:
        return identificar_inmueble(self.origen.fuente, self.origen.id_original)

    @property
    def disponibilidad(self) -> Disponibilidad:
        estados = {b.disponibilidad for b in self.origen.busquedas}
        for estado in (Disponibilidad.ACTIVO, Disponibilidad.POSIBLEMENTE_RETIRADO,
                       Disponibilidad.DESCONOCIDA):
            if estado in estados:
                return estado
        return Disponibilidad.RETIRADO if estados else Disponibilidad.DESCONOCIDA
