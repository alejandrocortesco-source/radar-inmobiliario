"""Sustituye solo la captura; conserva trabajador, métricas, SQLite y GCS reales."""
from metro.storage import Store
from .entorno import settings

class SyntheticScraper:
    def __init__(self,folder,search):
        if not settings().isolated:raise ValueError('Datos sintéticos requieren aislamiento')
        self.search=search;self.run_id=None
        self.store=Store(folder/{'metrocuadrado':'metro.sqlite','wasi':'wasi.sqlite','fincaraiz':'fincaraiz.sqlite'}[search['fuente']],normalizar_busqueda=lambda x:x)
    async def run(self):
        key=self.search['id_busqueda']
        if key.endswith('error'):raise ValueError('Fallo sintético solicitado')
        self.run_id=self.store.new_run(key,{'urls':[key]})
        self.store.save_page(self.run_id,1,'1',key,'fixture',[{'id':'synthetic','url':'https://synthetic.invalid/item','raw':{}}],None,search_url=key)
        self.store.plan_incremental(self.run_id)
        self.store.result(self.run_id,'synthetic','success',{'normalized':{'price':1000000},'quality':'success'})
        self.store.update_run(self.run_id,status='completed',listing_complete=1)
        return {'status':'completed'}
