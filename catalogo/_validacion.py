"""Validaciones pequeñas compartidas por modelos y filtros."""

from datetime import datetime
from decimal import Decimal
from enum import Enum


def texto(valor, nombre):
    if valor is not None and (not isinstance(valor, str) or not valor.strip()):
        raise ValueError(f'{nombre} debe ser texto no vacío o None')


def decimal_no_negativo(valor, nombre):
    if valor is None:
        return
    if not isinstance(valor, Decimal):
        raise TypeError(f'{nombre} debe ser Decimal o None; no usar float')
    if not valor.is_finite() or valor < 0:
        raise ValueError(f'{nombre} debe ser finito y no negativo')


def entero_no_negativo(valor, nombre):
    if valor is not None and (type(valor) is not int or valor < 0):
        raise ValueError(f'{nombre} debe ser un entero no negativo o None')


def fecha(valor, nombre):
    if valor is not None and (
        not isinstance(valor, datetime) or valor.tzinfo is None or valor.utcoffset() is None
    ):
        raise ValueError(f'{nombre} debe ser datetime con zona horaria o None')


def enumeracion(valor, tipo: type[Enum], nombre, *, opcional=False):
    if opcional and valor is None:
        return
    if not isinstance(valor, tipo):
        raise ValueError(f'{nombre} debe ser {tipo.__name__}')


def tupla(valor, tipo, nombre):
    if not isinstance(valor, tuple) or any(not isinstance(item, tipo) for item in valor):
        raise TypeError(f'{nombre} debe ser una tupla de {tipo.__name__}')


def moneda(valor):
    if valor is not None and (
        not isinstance(valor, str) or len(valor) != 3 or not valor.isascii()
        or not valor.isalpha() or not valor.isupper()
    ):
        raise ValueError('moneda debe ser un código de tres letras mayúsculas o None')
