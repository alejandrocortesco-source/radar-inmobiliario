"""Códigos fijos: nunca contienen HTML, valores de filtros ni errores de Playwright."""
from metro.extraction import ExtractionError

MESSAGES = {
    'wasi_search_overlay': 'Listado no obtenido: una ventana del portal bloqueó el botón Buscar.',
    'wasi_overlay_unclosable': 'Listado no obtenido: la ventana del portal no pudo cerrarse de forma segura.',
    'wasi_search_unconfirmed': 'Listado no obtenido: no se pudo confirmar el botón Buscar.',
    'wasi_listing_unverified': 'Listado incompleto: no se pudieron confirmar los filtros o la cobertura del portal.',
}

class WasiListingError(ExtractionError):
    def __init__(self, code):
        self.wasi_code = code if code in MESSAGES else 'wasi_listing_unverified'
        super().__init__(MESSAGES[self.wasi_code])
