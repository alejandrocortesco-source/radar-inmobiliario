"""Casos de uso comunes, sin dependencia de HTTP ni del scraper."""
import os
from pathlib import Path

from catalogo.persistencia.sqlite import BASE_PREDETERMINADA
from .modelos import ClienteDatos, Necesidades, OportunidadDatos
from .persistencia import Repositorio, SQLite
from .matching import buscar, diagnosticar


class ServicioOportunidades:
    def __init__(self, repositorio: Repositorio):
        self.repositorio = repositorio

    def clientes(self):
        return self.repositorio.clientes()

    def cliente(self, identificador):
        return self.repositorio.cliente(identificador)

    def guardar_cliente(self, datos: ClienteDatos, identificador=None):
        return self.repositorio.guardar_cliente(datos, identificador)

    def oportunidades(self):
        return self.repositorio.oportunidades()

    def oportunidad(self, identificador):
        return self.repositorio.oportunidad(identificador)

    def guardar_oportunidad(self, datos: OportunidadDatos, identificador=None):
        return self.repositorio.guardar_oportunidad(datos, identificador)

    def capturar(self, cliente: ClienteDatos, necesidades: Necesidades, estado='abierta',
                 cliente_id=None, oportunidad_id=None):
        # También valida entradas desde capturadores ajenos a HTTP antes de escribir.
        validado = OportunidadDatos(cliente_id=cliente_id or 'nuevo', necesidades=necesidades, estado=estado)
        return self.repositorio.capturar(cliente, validado.necesidades, validado.estado, cliente_id, oportunidad_id)

    def coincidencias(self, identificador, catalogo, orden='coincidencia'):
        return buscar(self.oportunidad(identificador).necesidades, catalogo.listar(), orden)

    def diagnostico(self, identificador, catalogo, orden='coincidencia'):
        informe = diagnosticar(self.oportunidad(identificador).necesidades, catalogo.listar(), orden)
        informe['almacenamiento'] = {
            'catalogo': str(getattr(getattr(catalogo, 'repositorio', None), 'ruta', 'Repositorio inyectado')),
            'clientes_oportunidades': str(getattr(self.repositorio, 'ruta', 'Repositorio inyectado')),
        }
        return informe


def servicio_oportunidades():
    catalogo = Path(os.getenv('METRO_DB', str(BASE_PREDETERMINADA))).resolve()
    ruta = Path(os.getenv('RADAR_CRM_DB', str(catalogo.with_name(catalogo.stem + '-consola.sqlite')))).resolve()
    if ruta == catalogo:
        from .persistencia import ErrorPersistencia
        raise ErrorPersistencia('RADAR_CRM_DB debe ser diferente de la base del catálogo')
    return ServicioOportunidades(SQLite(ruta))
