"""Contrato estructurado compartido por formularios, API y futuros capturadores."""
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from catalogo.modelos import TipoArea, TipoInmueble
from .normalizacion import normalizar

CRITERIOS = {
    'habitaciones_min': 'Habitaciones mínimas', 'banos_min': 'Baños mínimos',
    'parqueaderos_min': 'Parqueaderos mínimos', 'area_min_m2': 'Área mínima',
    'area_max_m2': 'Área máxima', 'antiguedad_max': 'Antigüedad máxima',
}
Criterio = Literal['habitaciones_min', 'banos_min', 'parqueaderos_min',
                   'area_min_m2', 'area_max_m2', 'antiguedad_max']


class Datos(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True, allow_inf_nan=False)


class ClienteDatos(Datos):
    nombre: str = Field(min_length=1, max_length=200)
    telefono: str | None = Field(default=None, max_length=80)


class Cliente(ClienteDatos):
    id: str
    creado_en: datetime
    actualizado_en: datetime


class Necesidades(Datos):
    operacion: Literal['compra', 'arriendo']
    tipo: TipoInmueble
    ciudad: str = Field(min_length=1, max_length=200)
    barrios: list[str] = Field(default_factory=list, max_length=100)
    zonas: list[str] = Field(default_factory=list, max_length=100)
    presupuesto_max: Decimal = Field(gt=0, max_digits=18, decimal_places=2)
    habitaciones_min: int | None = Field(default=None, ge=0, le=1000)
    banos_min: int | None = Field(default=None, ge=0, le=1000)
    parqueaderos_min: int | None = Field(default=None, ge=0, le=1000)
    tipo_area: TipoArea = TipoArea.CONSTRUIDA
    area_min_m2: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=2)
    area_max_m2: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=2)
    antiguedad_max: int | None = Field(default=None, ge=0, le=1000)
    preferencias: list[Criterio] = Field(default_factory=list)
    observaciones: str = Field(default='', max_length=5000)

    @field_validator('barrios', 'zonas')
    @classmethod
    def ubicaciones(cls, valores):
        if any(not v.strip() or len(v) > 200 for v in valores):
            raise ValueError('Cada barrio o zona debe tener entre 1 y 200 caracteres')
        unicos = {}
        for v in valores:
            unicos.setdefault(normalizar(v), ' '.join(v.split()))
        return list(unicos.values())

    @field_validator('presupuesto_max', 'habitaciones_min', 'banos_min', 'parqueaderos_min',
                     'area_min_m2', 'area_max_m2', 'antiguedad_max', mode='before')
    @classmethod
    def no_booleanos(cls, valor):
        if isinstance(valor, bool):
            raise ValueError('Ingresa un número, no un booleano')
        return valor

    @model_validator(mode='after')
    def criterios_validos(self):
        if not self.barrios and not self.zonas:
            raise ValueError('Selecciona al menos un barrio o zona de interés')
        if self.habitaciones_min is None and self.area_min_m2 is None:
            raise ValueError('Ingresa habitaciones mínimas o área mínima (puedes ingresar ambas)')
        if self.area_min_m2 is not None and self.area_max_m2 is not None and self.area_min_m2 > self.area_max_m2:
            raise ValueError('El área mínima no puede superar el área máxima')
        if any(getattr(self, campo) is None for campo in self.preferencias):
            raise ValueError('Una preferencia debe tener un valor diligenciado')
        return self


class OportunidadDatos(Datos):
    cliente_id: str = Field(min_length=1)
    necesidades: Necesidades
    estado: Literal['abierta', 'cerrada'] = 'abierta'


class Oportunidad(OportunidadDatos):
    id: str
    creado_en: datetime
    actualizado_en: datetime
