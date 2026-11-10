"""Composición de fuentes: un catálogo, sin fusionar inmuebles físicos."""
import os
from pathlib import Path

from .sqlite import CatalogoSQLite, BASE_PREDETERMINADA
from .contrato import ErrorLecturaCatalogo, IdentificadorAmbiguo


class CatalogoIntegrado:
    def __init__(self, repositorios):
        self.repositorios = tuple(repositorios)
        self.ruta = self.repositorios[0].ruta if len(self.repositorios) == 1 else ' | '.join(str(r.ruta) for r in self.repositorios)

    def listar(self):
        return tuple(sorted((i for r in self.repositorios for i in r.listar()), key=lambda i: i.id_interno))

    def listar_registros(self):
        return tuple(i for r in self.repositorios for i in r.listar_registros())

    def obtener(self, identificador):
        return next((i for r in self.repositorios if (i := r.obtener(identificador)) is not None), None)

    def ultima_actualizacion(self):
        return max((f for r in self.repositorios if (f := r.ultima_actualizacion()) is not None), default=None)

    def obtener_revision(self, identificador):
        # Los UUID son inequívocos. La API histórica conserva IDs simples solo
        # cuando no son ambiguos; fuente:ID permite consultar un código compartido.
        fuente, sep, codigo = identificador.partition(':')
        repos = [r for r in self.repositorios if r.fuente == fuente] if sep else self.repositorios
        encontrados = [i for r in repos if (i := r.obtener_revision(codigo if sep else identificador)) is not None]
        if len(encontrados) > 1:
            raise IdentificadorAmbiguo('Código compartido por varias fuentes; usa UUID o fuente:ID')
        return encontrados[0] if encontrados else None


def catalogo_configurado(metro=None):
    metro = Path(metro or os.getenv('METRO_DB', str(BASE_PREDETERMINADA))).resolve()
    rutas = [('metrocuadrado', metro),
             ('wasi', Path(os.getenv('WASI_DB', str(metro.with_name('wasi.sqlite')))).resolve()),
             ('fincaraiz', Path(os.getenv('FINCARAIZ_DB', str(metro.with_name('fincaraiz.sqlite')))).resolve())]
    if len({ruta for _, ruta in rutas}) != 3:
        raise ErrorLecturaCatalogo('METRO_DB, WASI_DB y FINCARAIZ_DB deben ser distintas')
    repos = [CatalogoSQLite(ruta, fuente=fuente) for fuente, ruta in rutas if ruta.exists()]
    if not repos:
        repos = [CatalogoSQLite(metro)]
    return CatalogoIntegrado(repos)
