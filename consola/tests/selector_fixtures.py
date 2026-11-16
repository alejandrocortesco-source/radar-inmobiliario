"""Registro auxiliar sintético de tres portales; nunca consulta portales."""
def seed_searches(repo):
    for source, name in [('metrocuadrado','Metrocuadrado'),('wasi','Wasi'),('fincaraiz','Fincaraíz')]:
        for key in ('compartida','segunda'):
            repo.guardar(source,key,'https://synthetic.invalid/'+source+'/'+key,name+' · '+key)
    repo.guardar('wasi','inactiva','https://synthetic.invalid/inactiva','Wasi · inactiva')
    repo.cambiar_estado('wasi','inactiva',False)
