"""Códigos fijos: nunca contienen HTML, valores de filtros ni errores de Playwright."""
from metro.extraction import ExtractionError

MESSAGES = {
    'wasi_search_overlay': 'Listado no obtenido: una ventana del portal bloqueó el botón Buscar.',
    'wasi_overlay_unclosable': 'Listado incompleto: el anuncio de ProductFruits o su fondo no pudieron despejarse de forma segura.',
    'wasi_search_unconfirmed': 'Listado no obtenido: no se pudo confirmar el botón Buscar.',
    'wasi_overlay_ambiguous': 'Listado incompleto: anuncio ProductFruits sin un único cierre visible y reconocido.',
    'wasi_overlay_limit': 'Listado incompleto: se alcanzó el límite de cierres o tiempo de anuncios ProductFruits.',
    'wasi_interaction_blocked': 'Listado incompleto: una ventana desconocida o un control no disponible impide continuar.',
    'wasi_interaction_uncertain': 'Listado incompleto: no se pudo confirmar si la interacción terminó; no se repitió para evitar duplicados.',
    'wasi_listing_unverified': 'Listado incompleto: no se pudieron confirmar los filtros o la cobertura del portal.',
}

class WasiListingError(ExtractionError):
    def __init__(self, code):
        self.wasi_code = code if code in MESSAGES else 'wasi_listing_unverified'
        super().__init__(MESSAGES[self.wasi_code])
