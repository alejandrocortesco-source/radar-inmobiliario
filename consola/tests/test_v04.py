"""Paridad entre interfaces, identidad del comentario y compatibilidad real SQLite."""
import hashlib
from urllib.parse import urlsplit
from bs4 import BeautifulSoup
from fastapi.testclient import TestClient
import pytest
from metro.web import app, servicio
from consola.comentarios import Comentarios
from oportunidades.persistencia import ErrorPersistencia
from oportunidades.servicio import servicio_oportunidades
from oportunidades.modelos import ClienteDatos
from test_v03 import necesidades


@pytest.fixture
def escenario04(escenario_consola):
    s = servicio_oportunidades()
    o = s.capturar(ClienteDatos(nombre='Mónica'), necesidades())
    otro = s.capturar(ClienteDatos(nombre='Otro'), necesidades())
    return TestClient(app), s, o, otro


def ids(response):
    return [r['data-match-id'] for r in BeautifulSoup(response.text, 'html.parser').select('[data-match-id]')]


@pytest.mark.parametrize('orden', ['coincidencia','precio_asc','precio_desc','area_asc','area_desc','ubicacion_desc','habitaciones_asc','estado_desc'])
def test_mismos_ids_orden_paginas_y_contadores(escenario04, orden):
    c, s, o, _ = escenario04
    for offset in [0,12,24]:
        query=f'?oportunidad={o.id}&match_orden={orden}&match_limit=12&match_offset={offset}'
        anterior=c.get('/consola/'+query); nueva=c.get('/v0.4/'+query)
        assert anterior.status_code == nueva.status_code == 200
        assert ids(anterior) == ids(nueva)
        assert len(BeautifulSoup(nueva.text,'html.parser').select('main table.catalog-table')) == 1
    directo=c.get(f'/v0.4/oportunidades/{o.id}/coincidencias?orden={orden}')
    assert directo.status_code==200
    assert ids(directo)==ids(c.get(f'/consola/oportunidades/{o.id}/coincidencias?orden={orden}'))


def test_catalogo_exportacion_completa_y_enlaces(escenario04):
    c,s,o,_=escenario04
    for query in ['', '?limit=12&offset=12', '?texto=26-M26','?tipo_area=privada&orden=area_desc']:
        old=c.get('/consola/'+query);new=c.get('/v0.4/'+query)
        a=BeautifulSoup(old.text,'html.parser');b=BeautifulSoup(new.text,'html.parser')
        assert [urlsplit(x['href']).path.split('/')[-1] for x in a.select('.property-link')]==[urlsplit(x['href']).path.split('/')[-1] for x in b.select('.property-link')]
        assert c.get('/consola/exportar.csv'+query).content==c.get('/v0.4/exportar.csv'+query).content
    assert 'opportunity-summary' not in c.get('/v0.4/').text
    assert 'Selecciona una oportunidad' in c.get('/v0.4/?contexto=matching').text
    html=c.get(f'/v0.4/?oportunidad={o.id}').text
    assert '/consola/?' not in html
    soup=BeautifulSoup(html,'html.parser')
    link=soup.select_one('.match-property-link')['href']
    detalle=c.get(link)
    assert detalle.status_code==200
    assert 'Evidencia de coincidencia' in detalle.text
    assert f'oportunidad={o.id}' in BeautifulSoup(detalle.text,'html.parser').select_one('.back-link')['href']


def test_comentario_unico_recarga_dos_oportunidades_y_v03(escenario04, escenario_consola):
    c,s,o,otro=escenario04
    huella=hashlib.sha256(escenario_consola['ruta'].read_bytes()).hexdigest()
    i=s.coincidencias(o.id,servicio())[0].inmueble.id_interno
    endpoint='/v0.4/comentarios/'+i
    antes=c.get('/api/oportunidades/'+o.id+'/coincidencias').json()
    texto='<script>alert(1)</script> Buena luz /consola/ literal'
    assert c.post(endpoint,json={'texto':texto}).json()['guardado']
    assert c.get(endpoint).json()['texto']==texto
    for oid in [o.id,otro.id]:
        html=c.get(f'/v0.4/inmuebles/{i}?oportunidad={oid}').text
        assert BeautifulSoup(html,'html.parser').select_one('#comment-text').text==texto
        assert '<script>alert(1)</script>' not in html
    assert 'Ver comentario' in c.get('/v0.4/').text
    assert 'data-comment-form' not in c.get('/consola/inmuebles/'+i).text
    assert c.post('/consola/clientes/'+o.cliente_id,data={'nombre':'Nombre compartido'}).status_code==200
    assert c.post('/consola/oportunidades',data={'nombre':'Nombre compartido','cliente_id':o.cliente_id,'oportunidad_id':o.id,'operacion':'compra','tipo':'casa','ciudad':'Bogotá','ubicaciones':'barrio:La Carolina','presupuesto_max':'110000000','habitaciones_min':'3','estado':'abierta'}).status_code==200
    assert c.get(endpoint).json()['texto']==texto
    assert Comentarios(s.repositorio.ruta).leer(i)==texto
    assert c.get('/api/oportunidades/'+o.id+'/coincidencias').json()==antes
    assert hashlib.sha256(escenario_consola['ruta'].read_bytes()).hexdigest()==huella
    assert c.post(endpoint,json={'texto':'Habitaciones oscuras'}).status_code==200
    assert c.get(endpoint).json()['texto']=='Habitaciones oscuras'
    assert c.post('/v0.4/comentarios/no-existe',json={'texto':'otro'}).status_code==404


def test_guardar_sin_buscar_errores_y_error_comentario(escenario04,monkeypatch):
    c,s,o,_=escenario04
    datos={'nombre':'Mónica','cliente_id':o.cliente_id,'oportunidad_id':o.id,'operacion':'compra','tipo':'casa','ciudad':'Bogotá','ubicaciones':'barrio:La Carolina','presupuesto_max':'110000000','habitaciones_min':'3','estado':'abierta','accion':'guardar'}
    r=c.post('/v0.4/oportunidades',data=datos)
    assert 'sin_buscar=1' in str(r.url)
    assert 'criterios anteriores' in r.text
    assert not ids(r)
    datos['accion']='buscar'
    assert ids(c.post('/v0.4/oportunidades',data=datos))
    datos['nombre']=''
    r=c.post('/v0.4/oportunidades',data=datos)
    assert r.status_code==422 and 'dialog' in r.text
    i=servicio().listar()[0].id_interno
    def fallo(*args):raise ErrorPersistencia('Error simulado')
    monkeypatch.setattr(Comentarios,'guardar',fallo)
    assert c.post('/v0.4/comentarios/'+i,json={'texto':'conservar'}).status_code==503
    assert c.post('/v0.4/comentarios/'+i,json={'texto':4}).status_code==422


def test_guardar_no_ejecuta_matching(escenario04,monkeypatch):
    c,s,o,_=escenario04
    import consola.oportunidades as adaptador
    def prohibido(*args,**kwargs):raise AssertionError('Guardar no debe calcular')
    monkeypatch.setattr(adaptador,'diagnosticar',prohibido)
    assert c.get('/v0.4/?oportunidad='+o.id+'&sin_buscar=1').status_code==200


def test_comentario_antes_de_crear_crm_y_escritura_v03(escenario_consola):
    c=TestClient(app);s=servicio_oportunidades();i=servicio().listar()[0].id_interno
    assert not s.repositorio.ruta.exists()
    endpoint='/v0.4/comentarios/'+i
    assert c.post(endpoint,json={'texto':'Buena luz'}).status_code==200
    cliente=c.post('/api/clientes',json={'nombre':'Compatible'})
    assert cliente.status_code==201
    # El scraper sigue escribiendo su propia base; el comentario es independiente.
    datos=escenario_consola
    datos['store'].result(datos['run'],'1-M1','success',datos['documentos']['1-M1'])
    assert c.get(endpoint).json()['texto']=='Buena luz'
