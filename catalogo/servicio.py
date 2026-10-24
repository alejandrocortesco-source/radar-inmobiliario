"""Consultas comunes y proyección compatible de la API de revisión existente."""

import json
from collections.abc import Callable

from .modelos import Inmueble
from .persistencia.contrato import RepositorioCatalogo, RepositorioRevision


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

    def obtener(self, id_interno: str) -> Inmueble | None:
        return self.repositorio.obtener(id_interno)

    def _revision(self):
        if self.revision is None:
            raise RuntimeError('No se ha configurado la lectura de revisión del catálogo')
        return self.revision

    def catalogo_compatible(self, *, state=None, search_url=None, limit=100, offset=0):
        """Conserva filtros, orden y paginación antiguos; no ejecuta FiltrosCatalogo."""
        busqueda = self.normalizar_busqueda(search_url) if search_url else None
        items = []
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
            items.append({
                **registro.resumen,
                'last_verified_at': max(fechas, default=None),
                'state': estado,
                'id_interno': registro.inmueble.id_interno,
            })
        items.sort(key=lambda item: item['id'])
        inicio = max(0, offset)
        pagina = items[inicio:] if limit < 0 else items[inicio:inicio + limit]
        return {'total': len(items), 'items': pagina, 'limit': limit, 'offset': offset}

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
