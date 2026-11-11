"""Publicaciones sintéticas; ninguna asociación ni captura operativa."""
from dataclasses import replace
from decimal import Decimal as D
from datetime import datetime, timezone
import sqlite3

import pytest
from catalogo.modelos import Inmueble, Origen, Oferta, Operacion, TipoInmueble
from catalogo.identificacion import comparar, candidatos
from catalogo.persistencia.asociaciones import AsociacionesSQLite, DecisionInvalida
from catalogo.consultas import seleccionar, contar_categorias, paginar
from catalogo.filtros import FiltrosCatalogo
from oportunidades.matching import buscar
from oportunidades.modelos import Necesidades
from oportunidades.seguimiento import SeguimientoSQLite


def anuncio(fuente, codigo='42', **kw):
    return Inmueble(origen=Origen(fuente=fuente, id_original=codigo),
                    ciudad='Bogotá', tipo=TipoInmueble.APARTAMENTO, barrio='La Carolina',
                    direccion='Calle 100 # 10-20 Apto 301', area_construida_m2=D(100),
                    habitaciones=3, banos=2, parqueaderos=1,
                    ofertas=(Oferta(operacion=Operacion.VENTA, precio=D(800)),), **kw)


@pytest.fixture
def trio():
    return tuple(anuncio(f) for f in ('metrocuadrado','wasi','fincaraiz'))


def decidir(repo, a, b, items, accion='confirmado', aceptar=True):
    r = repo.revisar(a.id_interno,b.id_interno,items)
    repo.decidir(a.id_interno,b.id_interno,accion,items,r['firma'],aceptar)


def test_tres_pares_sin_autoagrupar_y_codigos_ambiguos(tmp_path,trio):
    repo = AsociacionesSQLite(tmp_path/'crm.sqlite')
    assert len(list(candidatos(trio, {i.id_interno for i in trio}))) == 3
    assert repo.analizar(trio) == 3
    assert len(repo.pares()) == 3
    assert repo.miembros() == {}
    assert all('id_original' not in p['evidencia']['favor'] for p in repo.pares())
    assert repo.analizar(trio) == 0
    assert len(repo.pares()) == 3


def test_faltantes_area_incompatible_unidad_y_precio(trio):
    a,b,_ = trio
    b = replace(b,area_construida_m2=None,area_privada_m2=D(100), habitaciones=None,
                direccion='Calle 100 # 10-20 Apto 302')
    e = comparar(a,b)
    assert 'area' in e['faltantes'] and 'habitaciones' in e['faltantes']
    assert 'unidad' in e['contradicciones']
    assert 'precio' in e['favor']
    assert e['puntuacion'] < 100
    assert 'area' in comparar(a,replace(b,area_construida_m2=D(120)))['contradicciones']


def test_bloques_descartan_otras_ciudades_tipos_operaciones(trio):
    a,b,c = trio
    assert not list(candidatos((a,replace(b,ciudad='Cali'),replace(c,tipo=TipoInmueble.CASA)), {a.id_interno}))
    assert not list(candidatos((a,replace(b,ofertas=(Oferta(operacion=Operacion.ARRIENDO,precio=D(10)),))), {a.id_interno}))
    assert not list(candidatos((a,replace(b,ciudad=None)), {a.id_interno}))


def test_decisiones_confirmacion_idempotencia_nuevos_scrapes_y_reversion(tmp_path,trio):
    a,b,c = trio
    repo = AsociacionesSQLite(tmp_path/'crm.sqlite')
    repo.analizar(trio)
    decidir(repo,a,b,trio)
    gid = repo.miembros()[a.id_interno]
    decidir(repo,a,b,trio)
    assert repo.miembros()[b.id_interno] == gid
    cambiado = (a,replace(b,habitaciones=2),c)
    repo.analizar(cambiado)
    par = next(p for p in repo.pares() if {p['a'],p['b']} == {a.id_interno,b.id_interno})
    assert par['estado'] == 'confirmado'
    assert par['firma_decision'] != par['evidencia']['huella']
    assert repo.miembros()[a.id_interno] == gid
    decidir(repo,a,b,cambiado,'deshacer')
    assert not repo.miembros()
    with sqlite3.connect(repo.ruta) as db:
        assert db.execute('SELECT count(*) FROM radar_identificacion_historial').fetchone()[0] == 3


def test_descartes_persisten_y_bloquean_transitividad(tmp_path,trio):
    a,b,c = trio
    repo = AsociacionesSQLite(tmp_path/'crm.sqlite')
    repo.analizar(trio)
    decidir(repo,a,c,trio,'descartado')
    decidir(repo,a,b,trio)
    assert c.id_interno not in repo.miembros()
    r = repo.revisar(b.id_interno,c.id_interno,trio)
    assert len(r['relaciones']) == 3
    with pytest.raises(DecisionInvalida, match='descartada'):
        decidir(repo,b,c,trio)
    assert c.id_interno not in repo.miembros()
    repo.analizar(trio,completo=True)
    assert next(p for p in repo.pares() if {p['a'],p['b']}=={a.id_interno,c.id_interno})['estado']=='descartado'
    decidir(repo,a,c,trio,'despues')
    with pytest.raises(DecisionInvalida, match='Confirma'):
        decidir(repo,b,c,trio,aceptar=False)
    decidir(repo,b,c,trio)
    assert len(set(repo.miembros().values())) == 1
    assert all(p['estado']=='confirmado' for p in repo.pares())
    decidir(repo,a,b,trio,'deshacer')
    assert not repo.miembros()
    assert all(p['estado']=='pendiente' for p in repo.pares())


def test_rechaza_revision_obsoleta_y_grupo_cambiado(tmp_path,trio):
    a,b,c = trio
    repo = AsociacionesSQLite(tmp_path/'crm.sqlite')
    r = repo.revisar(a.id_interno,b.id_interno,trio)
    with pytest.raises(DecisionInvalida,match='cambiaron'):
        repo.decidir(a.id_interno,b.id_interno,'confirmado',(replace(a,banos=1),b,c),r['firma'],True)
    decidir(repo,a,c,trio)
    with pytest.raises(DecisionInvalida,match='cambiaron'):
        repo.decidir(a.id_interno,b.id_interno,'confirmado',trio,r['firma'],True)


def test_catalogo_filtra_publicacion_completa_antes_de_agrupar(tmp_path,trio):
    a,b,c = trio
    b = replace(b, ofertas=(Oferta(operacion=Operacion.VENTA,precio=D(600)),), habitaciones=2)
    items = (a,b,c)
    repo = AsociacionesSQLite(tmp_path/'crm.sqlite')
    decidir(repo,a,b,items)
    proyectados = repo.proyectar(items)
    assert len(seleccionar(proyectados,FiltrosCatalogo())) == 2
    assert contar_categorias(proyectados,FiltrosCatalogo())['todos']==2
    f = FiltrosCatalogo(operacion=Operacion.VENTA,precio_max=D(700),habitaciones_min=3)
    assert seleccionar(proyectados,f)==[]
    f = replace(f,habitaciones_min=2)
    rs = seleccionar(proyectados,f)
    assert [i.id_interno for i in rs]==[b.id_interno]
    assert len(rs[0].publicaciones)==2
    assert paginar(seleccionar(proyectados,FiltrosCatalogo()),1,1)['total']==2


def test_matching_no_mezcla_precios_atributos_y_conserva_decisiones(tmp_path,trio):
    a,b,c = trio
    a=replace(a,ofertas=(Oferta(operacion=Operacion.VENTA,precio=D(900)),))
    b=replace(b,habitaciones=2,ofertas=(Oferta(operacion=Operacion.VENTA,precio=D(600)),))
    items=(a,b,c)
    repo=AsociacionesSQLite(tmp_path/'crm.sqlite')
    decidir(repo,a,b,items)
    decidir(repo,b,c,items)
    n=Necesidades(operacion='compra',tipo='apartamento',ciudad='Bogotá',barrios=['La Carolina'],presupuesto_max=700,habitaciones_min=3)
    assert buscar(n,repo.proyectar(items))==[]
    rs=buscar(n.model_copy(update={'presupuesto_max':D(1000)}),repo.proyectar(items))
    assert len(rs)==1 and rs[0].inmueble.id_interno in {a.id_interno,c.id_interno}
    assert len(rs[0].alternativas)==1
    seguimiento=SeguimientoSQLite(repo.ruta)
    seguimiento.decision('op',a.id_interno,'descartado')
    seguimiento.decision('op',b.id_interno,'preseleccionado')
    decidir(repo,a,b,items,'deshacer')
    assert len(seguimiento.decisiones('op'))==2


def test_migracion_aditiva_lectura_no_crea_base_y_fallo_recuperable(tmp_path,trio,monkeypatch):
    repo=AsociacionesSQLite(tmp_path/'crm.sqlite')
    assert not repo.miembros() and not repo.pares() and not repo.ruta.exists()
    with sqlite3.connect(repo.ruta) as db:
        db.execute('CREATE TABLE anterior (dato TEXT)')
        db.execute("INSERT INTO anterior VALUES ('conservar')")
        db.execute('PRAGMA user_version=1')
    repo.analizar(trio)
    with sqlite3.connect(repo.ruta) as db:
        assert db.execute('SELECT dato FROM anterior').fetchone()[0]=='conservar'
        assert db.execute('PRAGMA user_version').fetchone()[0]==1
    import catalogo.persistencia.asociaciones as modulo
    with monkeypatch.context() as m:
        m.setattr(modulo,'candidatos',lambda *args: (_ for _ in ()).throw(RuntimeError('sintético')))
        with pytest.raises(RuntimeError):
            repo.analizar(trio,completo=True)
    assert repo.ejecucion()['estado']=='error'
    repo.analizar(trio,completo=True)
    assert repo.ejecucion()['estado']=='correcto'


def test_cambio_solo_fecha_no_reprocesa(tmp_path,trio):
    repo=AsociacionesSQLite(tmp_path/'crm.sqlite')
    repo.analizar(trio)
    a,b,c=trio
    a=replace(a,origen=replace(a.origen,ultima_verificacion=datetime.now(timezone.utc)))
    assert repo.analizar((a,b,c))==0


@pytest.mark.parametrize('direccion,esperada', [('Calle 1 apartamento no 301','301'), ('Calle 1 apto. 302','302'), ('Carrera 3 unidad A-204','a-204'), ('Edificio 301',None), ('Apartamento sin identificar',None)])
def test_unidad_explicita_no_confunde_calificador(direccion,esperada):
    from catalogo.identificacion import unidad, PESOS
    assert unidad(direccion)==esperada
    assert sum(PESOS.values())==100


@pytest.mark.parametrize('area,cumple', [('97',True),('96.999',False)])
def test_tolerancia_area_inclusiva(trio,area,cumple):
    a,b,_=trio
    e=comparar(a,replace(b,area_construida_m2=D(area)))
    assert ('area' in e['favor']) is cumple


@pytest.mark.parametrize('precio,cumple', [('760',True),('759.99',False)])
def test_tolerancia_precio_inclusiva(trio,precio,cumple):
    a,b,_=trio
    e=comparar(a,replace(b,ofertas=(Oferta(operacion=Operacion.VENTA,precio=D(precio)),)))
    assert ('precio' in e['favor']) is cumple
