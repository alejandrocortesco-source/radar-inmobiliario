"""Consultas comunes y proyección compatible de la API de revisión existente."""

import json
from collections.abc import Callable
from dataclasses import replace

from .consultas import ofertas_compatibles, paginar, seleccionar
from .filtros import FiltrosCatalogo

from .modelos import Inmueble
from .persistencia.contrato import RepositorioCatalogo, RepositorioRevision


class ConsultaInvalida(ValueError):
    pass


class InmuebleNoEncontrado(LookupError):
    pass


class ServicioCatalogo:
    def __init__(self, repositorio: RepositorioCatalogo, *,
                 revision: RepositorioRevision | None = None,
                 normalizar_busqueda: Callable[[str], str] = lambda valor: valor):
        self.repositorio = repositorio
        self.revision = revision
        self.normalizar_busqueda = normalizar_busqueda

    def listar(self) -> tuple[Inmueble, ...]:
        return self.repositorio.listar()

    def consultar(self, filtros: FiltrosCatalogo | None = None):
        filtros = filtros if filtros is not None else FiltrosCatalogo()
        items = seleccionar(self.repositorio.listar(), filtros)
        return paginar(items, filtros.limite, filtros.desplazamiento)

    def obtener(self, id_interno: str) -> Inmueble | None:
        return self.repositorio.obtener(id_interno)

    def _revision(self):
        if self.revision is None:
            raise RuntimeError('No se ha configurado la lectura de revisión del catálogo')
        return self.revision

    def catalogo_compatible(self, *, state=None, search_url=None, limit=100, offset=0,
                            filtros: FiltrosCatalogo | None = None):
        """Filtra el modelo común y conserva el formato y parámetros HTTP anteriores."""
        busqueda = self.normalizar_busqueda(search_url) if search_url else None
        filtros = filtros if filtros is not None else FiltrosCatalogo()
        if busqueda:
            if filtros.id_busqueda is not None and filtros.id_busqueda != busqueda:
                raise ConsultaInvalida('search_url e id_busqueda deben identificar la misma búsqueda')
            filtros = replace(filtros, id_busqueda=busqueda,
                              fuente=filtros.fuente or 'metrocuadrado')
        elif filtros.id_busqueda is not None:
            busqueda = filtros.id_busqueda
        items = {}
        modelos = []
        for registro in self._revision().listar_registros():
            presencias = [p for p in registro.presencias
                          if busqueda is None or p['search_url'] == busqueda]
            # El endpoint original excluye anuncios sin pertenencia a búsquedas.
            if not presencias:
                continue
            estados = {p['state'] for p in presencias}
            estado = ('active' if 'active' in estados else
                      'possibly_removed' if 'possibly_removed' in estados else 'removed')
            if state and estado != state:
                continue
            fechas = [p['last_verified_at'] for p in presencias if p['last_verified_at'] is not None]
            modelos.append(registro.inmueble)
            items[registro.inmueble.id_interno] = {
                **registro.resumen,
                'last_verified_at': max(fechas, default=None),
                'state': estado,
                'id_interno': registro.inmueble.id_interno,
            }
        seleccionados = seleccionar(modelos, filtros, id_original_primero=True)
        resultado = []
        for inmueble in seleccionados:
            item = items[inmueble.id_interno]
            if filtros.operacion is not None or filtros.moneda is not None:
                ofertas = ofertas_compatibles(inmueble, filtros)
                item['ofertas'] = [
                    {'operation': o.operacion.value, 'price': o.precio, 'currency': o.moneda}
                    for o in ofertas
                ]
                if filtros.operacion is not None:
                    oferta = ofertas[0]
                    item.update(price=oferta.precio, operation=oferta.operacion.value,
                                currency=oferta.moneda)
            resultado.append(item)
        return paginar(resultado, limit, offset)

    def ficha_compatible(self, identificador, run_id=None):
        """Admite ID original o interno y mantiene las instantáneas por ejecución."""
        revision = self._revision().obtener_revision(identificador)
        if revision is None:
            raise InmuebleNoEncontrado(identificador)
        registro = revision.registro
        job = next((j for j in revision.trabajos
                    if run_id is None or j['run_id'] == run_id), None)
        seleccionado = (json.loads(job['data_json'])
                        if job and job['data_json'] and
                        (run_id is not None or job['status'] in ('success', 'unchanged'))
                        else revision.documento)
        return {
            'id': registro.resumen['id'], 'url': registro.resumen['url'],
            'id_interno': registro.inmueble.id_interno,
            'job': job, 'data': seleccionado, 'catalog_data': revision.documento,
            'needs_refresh': registro.inmueble.requiere_revision,
            'appearances': list(revision.apariciones),
            'memberships': list(registro.presencias),
            'price_history': list(revision.historial),
        }
