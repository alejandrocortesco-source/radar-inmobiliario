"""Ciclo v0.3, reglas de negocio, datos desconocidos y aislamiento del scraper."""
from dataclasses import replace
from decimal import Decimal
import hashlib
import sqlite3

from bs4 import BeautifulSoup
from fastapi.testclient import TestClient
import pytest
from pydantic import ValidationError

from catalogo.modelos import Inmueble, Oferta, Operacion, Origen, TipoInmueble
from metro.web import app, servicio
from oportunidades.matching import buscar, comparar
from oportunidades.modelos import ClienteDatos, Necesidades, OportunidadDatos
from oportunidades.persistencia import SQLite, NoEncontrado, ErrorPersistencia
from oportunidades.servicio import ServicioOportunidades, servicio_oportunidades


def necesidades(**cambios):
    return Necesidades.model_validate(dict(operacion='compra', tipo='casa', ciudad='Bogotá',
        barrios=['La Carolina'], presupuesto_max='110000000', habitaciones_min=3, **cambios))


def inmueble(**cambios):
    base = Inmueble(origen=Origen(fuente='portal', id_original='1'), tipo=TipoInmueble.CASA,
        ciudad='Bogotá', barrio='La Carolina', zona='Norte', habitaciones=3, banos=2,
        parqueaderos=0, area_construida_m2=Decimal('85'),
        ofertas=(Oferta(operacion=Operacion.VENTA, precio=Decimal('105000000'), moneda='COP'),))
    return replace(base, **cambios)


@pytest.mark.parametrize('campo', ['operacion', 'tipo', 'ciudad', 'presupuesto_max'])
def test_obligatorios(campo):
    datos = necesidades().model_dump()
    datos.pop(campo)
    with pytest.raises(ValidationError):
        Necesidades.model_validate(datos)


@pytest.mark.parametrize('datos', [
    {'ciudad': '  '}, {'barrios': [], 'zonas': []}, {'barrios': ['  ']},
    {'presupuesto_max': 0}, {'presupuesto_max': -1}, {'presupuesto_max': 'NaN'},
    {'presupuesto_max': 'Infinity'}, {'presupuesto_max': True},
    {'habitaciones_min': -1}, {'habitaciones_min': 2.5}, {'habitaciones_min': True},
    {'banos_min': -1}, {'parqueaderos_min': 'abc'}, {'area_min_m2': 0},
    {'area_min_m2': 'NaN'}, {'area_min_m2': 100, 'area_max_m2': 50},
    {'antiguedad_max': -1}, {'antiguedad_max': 2.5},
    {'preferencias': ['inventado']}, {'preferencias': ['banos_min'], 'banos_min': None},
])
def test_validacion_numerica_y_ubicaciones(datos):
    base = necesidades().model_dump()
    with pytest.raises(ValidationError):
        Necesidades.model_validate(base | datos)


def test_habitaciones_o_area_y_nombre():
    base = necesidades().model_dump()
    with pytest.raises(ValidationError, match='habitaciones mínimas o área mínima'):
        Necesidades.model_validate(base | {'habitaciones_min': None})
    assert Necesidades.model_validate(base | {'habitaciones_min': None, 'area_min_m2': 80})
    assert Necesidades.model_validate(base | {'area_min_m2': 80})
    with pytest.raises(ValidationError):
        ClienteDatos(nombre='   ')


def test_persistencia_edicion_multiples_y_migracion_segura(tmp_path):
    ruta = tmp_path / 'crm.sqlite'
    # Datos preexistentes ajenos a la Consola y user_version conservados.
    with sqlite3.connect(ruta) as db:
        db.execute('CREATE TABLE legado (valor TEXT)')
        db.execute("INSERT INTO legado VALUES ('conservar')")
        db.execute('PRAGMA user_version=7')
    s = ServicioOportunidades(SQLite(ruta))
    assert s.clientes() == []
    c = s.guardar_cliente(ClienteDatos(nombre='Mónica', telefono='300123'))
    primera = s.guardar_oportunidad(OportunidadDatos(cliente_id=c.id, necesidades=necesidades()))
    segunda = s.guardar_oportunidad(OportunidadDatos(cliente_id=c.id, necesidades=necesidades()))
    s = ServicioOportunidades(SQLite(ruta))
    nuevo_cliente = s.guardar_cliente(ClienteDatos(nombre='Ana'), c.id)
    cerrada = s.guardar_oportunidad(OportunidadDatos(cliente_id=c.id, necesidades=necesidades(), estado='cerrada'), primera.id)
    assert nuevo_cliente.id == c.id and nuevo_cliente.creado_en == c.creado_en
    assert nuevo_cliente.actualizado_en >= c.actualizado_en
    assert cerrada.creado_en == primera.creado_en and cerrada.actualizado_en >= primera.actualizado_en
    assert s.oportunidad(cerrada.id).estado == 'cerrada'
    assert segunda.id != primera.id and len(s.oportunidades()) == 2 and len(s.clientes()) == 1
    with sqlite3.connect(ruta) as db:
        assert db.execute('SELECT * FROM legado').fetchone()[0] == 'conservar'
        assert db.execute('PRAGMA user_version').fetchone()[0] == 7
        assert db.execute('SELECT version FROM consola_migraciones').fetchall() == [(1,)]
        assert db.execute('PRAGMA foreign_key_check').fetchall() == []


def test_lectura_sin_escritura_y_rollback_atomico(tmp_path):
    ruta = tmp_path / 'crm.sqlite'
    s = ServicioOportunidades(SQLite(ruta))
    assert s.clientes() == [] and s.oportunidades() == [] and not ruta.exists()
    c = s.guardar_cliente(ClienteDatos(nombre='Original'))
    antes = hashlib.sha256(ruta.read_bytes()).hexdigest()
    assert s.cliente(c.id).nombre == 'Original'
    assert hashlib.sha256(ruta.read_bytes()).hexdigest() == antes
    with pytest.raises(NoEncontrado):
        s.capturar(ClienteDatos(nombre='Cambio'), necesidades(), cliente_id=c.id, oportunidad_id='no-existe')
    assert s.cliente(c.id).nombre == 'Original'
    with pytest.raises(NoEncontrado):
        s.capturar(ClienteDatos(nombre='Huérfano'), necesidades(), oportunidad_id='no-existe')
    assert len(s.clientes()) == 1
    with pytest.raises(NoEncontrado):
        s.guardar_oportunidad(OportunidadDatos(cliente_id='no-existe', necesidades=necesidades()))
    with pytest.raises(ValidationError):
        s.capturar(ClienteDatos(nombre='Inválido'), necesidades(), estado='desconocida')
    assert len(s.clientes()) == 1


@pytest.mark.parametrize('cambios', [
    {'tipo': TipoInmueble.APARTAMENTO}, {'ciudad': 'Medellín'}, {'barrio': 'Country Club'},
    {'habitaciones': 2},
    {'ofertas': (Oferta(operacion=Operacion.VENTA, precio=Decimal('111000000'), moneda='COP'),)},
    {'ofertas': (Oferta(operacion=Operacion.ARRIENDO, precio=Decimal('1000'), moneda='COP'),)},
    {'ofertas': (Oferta(operacion=Operacion.VENTA, precio=Decimal('1000'), moneda='USD'),)},
    {'ofertas': (Oferta(operacion=Operacion.VENTA, moneda='USD'),)},
])
def test_matching_excluye_incumplimientos_conocidos(cambios):
    assert comparar(necesidades(), inmueble(**cambios)) is None


@pytest.mark.parametrize('cambios,pendiente', [
    ({'tipo': None}, 'Tipo'), ({'ciudad': None}, 'Ciudad'),
    ({'barrio': None}, 'Barrio'), ({'barrio': 'Nombre no verificado'}, 'Barrio'), ({'habitaciones': None}, 'Habitaciones'),
    ({'ofertas': ()}, 'Operación'),
    ({'ofertas': (Oferta(operacion=Operacion.VENTA, precio=Decimal('1000')), )}, 'Presupuesto'),
    ({'ofertas': (Oferta(operacion=Operacion.VENTA, moneda='COP'), )}, 'Presupuesto'),
])
def test_datos_faltantes_no_confirman(cambios, pendiente):
    r = comparar(necesidades(), inmueble(**cambios))
    assert r is not None and not r.confirmada
    assert any(pendiente in p for p in r.pendientes)


def test_minimos_preferencias_areas_antiguedad_y_normalizacion():
    n = necesidades(banos_min=2, parqueaderos_min=1, area_min_m2=80, area_max_m2=90)
    assert comparar(n, inmueble()) is None
    assert comparar(n.model_copy(update={'preferencias': ['parqueaderos_min']}), inmueble()).confirmada
    assert comparar(n, inmueble(parqueaderos=None)) is not None
    n = necesidades(area_min_m2=80, antiguedad_max=10)
    r = comparar(n, inmueble(area_construida_m2=None, area_privada_m2=Decimal('90')))
    assert not r.confirmada and len(r.pendientes) == 2
    assert any('Antigüedad' in v for v in r.pendientes)
    assert comparar(necesidades(), inmueble(ciudad='  BOGOTA ', barrio='la carolina')).confirmada
    assert comparar(necesidades(zonas=['Norte']), inmueble(barrio='Otro')).confirmada
    assert not comparar(necesidades(zonas=['Norte']), inmueble(barrio='Otro', zona=None)).confirmada
    assert comparar(necesidades(area_min_m2=80, area_max_m2=85), inmueble()).confirmada


def test_orden_explicable_y_doble_oferta():
    n = necesidades(banos_min=3, preferencias=['banos_min'])
    a = inmueble(origen=Origen(fuente='portal', id_original='a'))
    b = inmueble(origen=Origen(fuente='portal', id_original='b'), banos=3)
    c = inmueble(origen=Origen(fuente='portal', id_original='c'), habitaciones=None, banos=3)
    assert [r.inmueble for r in buscar(n, [c, a, b])] == [b, a, c]
    dual = inmueble(ofertas=(Oferta(operacion=Operacion.VENTA, precio=Decimal('999000000'), moneda='COP'),
                            Oferta(operacion=Operacion.ARRIENDO, precio=Decimal('1000000'), moneda='COP')))
    compra = necesidades()
    arriendo = Necesidades.model_validate(compra.model_dump() | {'operacion': 'arriendo', 'presupuesto_max': '1100000'})
    assert comparar(compra, dual) is None
    assert comparar(arriendo, dual).oferta.precio == Decimal('1000000')
    assert comparar(n, inmueble(banos=None)).preferencias_pendientes
    with pytest.raises(ValueError):
        buscar(n, [], 'inventado')


def test_api_ciclo_completo_preserva_catalogo_y_edita(escenario_consola):
    ruta = escenario_consola['ruta']
    antes = hashlib.sha256(ruta.read_bytes()).hexdigest()
    client = TestClient(app)
    c = client.post('/api/clientes', json={'nombre': 'Ana', 'telefono': '300123'}).json()
    datos = {'cliente_id': c['id'], 'necesidades': necesidades().model_dump(mode='json')}
    response = client.post('/api/oportunidades', json=datos)
    assert response.status_code == 201
    o = response.json()
    assert client.get('/api/clientes/' + c['id']).json()['nombre'] == 'Ana'
    assert client.put('/api/clientes/' + c['id'], json={'nombre': 'Ana María'}).status_code == 200
    assert client.post('/api/oportunidades', json=datos).status_code == 201
    assert len(client.get('/api/oportunidades').json()) == 2
    assert len(client.get('/api/clientes').json()) == 1
    matches = client.get('/api/oportunidades/' + o['id'] + '/coincidencias').json()
    assert len(matches) == 10  # Catálogo global, sin filtros de URL de scraper.
    assert all(not r['pendientes'] for r in matches)
    datos['necesidades']['presupuesto_max'] = '103000000'
    datos['estado'] = 'cerrada'
    editada = client.put('/api/oportunidades/' + o['id'], json=datos)
    assert editada.status_code == 200 and editada.json()['creado_en'] == o['creado_en']
    assert len(client.get('/api/oportunidades/' + o['id'] + '/coincidencias').json()) == 3
    assert client.get('/api/catalog').status_code == 200
    assert client.get('/consola/').status_code == 200
    assert client.get('/health').status_code == 200
    assert hashlib.sha256(ruta.read_bytes()).hexdigest() == antes
    assert ruta.with_name(ruta.stem + '-consola.sqlite').is_file()


def test_api_errores_no_guardan(escenario_consola):
    client = TestClient(app)
    assert client.post('/api/clientes', json={'nombre': '  '}).status_code == 422
    assert client.get('/api/clientes/no-existe').status_code == 404
    assert client.get('/api/oportunidades/no-existe').status_code == 404
    assert client.get('/api/oportunidades/no-existe/coincidencias').status_code == 404
    assert client.get('/api/oportunidades/x/coincidencias?orden=x').status_code == 422
    assert client.get('/consola/?oportunidad=no-existe').status_code == 404
    datos = {'cliente_id': 'no-existe', 'necesidades': necesidades().model_dump(mode='json')}
    assert client.post('/api/oportunidades', json=datos).status_code == 404
    datos['necesidades']['habitaciones_min'] = None
    assert client.post('/api/oportunidades', json=datos).status_code == 422
    assert client.get('/api/clientes').json() == []


def test_formulario_errores_edicion_cliente_y_resultados(escenario_consola):
    client = TestClient(app)
    datos = {'nombre': 'Cliente <script>alert(1)</script>', 'operacion': 'compra', 'tipo': 'casa',
             'ciudad': 'Bogotá', 'ubicaciones': ['barrio:La Carolina', 'zona:Norte'], 'presupuesto_max': '110000000'}
    mal = client.post('/consola/oportunidades', data=datos)
    assert mal.status_code == 422 and 'Ingresa habitaciones mínimas o área mínima' in mal.text
    assert '<script>alert(1)</script>' not in mal.text
    assert client.get('/api/clientes').json() == []
    datos['habitaciones_min'] = '3'
    bien = client.post('/consola/oportunidades', data=datos)
    assert bien.status_code == 200 and 'Guardado correctamente' in bien.text
    o = client.get('/api/oportunidades').json()[0]
    assert o['necesidades']['zonas'] == ['Norte']
    pagina = BeautifulSoup(bien.text, 'html.parser')
    assert pagina.select_one('#crm_nombre')['value'] == datos['nombre']
    assert client.get('/consola/oportunidades/' + o['id'] + '/coincidencias').status_code == 200
    assert client.get('/consola/oportunidades/' + o['id'] + '/coincidencias?orden=precio').status_code == 200
    assert client.get('/consola/oportunidades/' + o['id'] + '/coincidencias?orden=x').status_code == 422
    c_id = o['cliente_id']
    assert client.get('/consola/clientes/' + c_id).status_code == 200
    assert client.post('/consola/clientes/' + c_id, data={'nombre': ''}).status_code == 422
    assert client.post('/consola/clientes/' + c_id, data={'nombre': 'Nuevo nombre'}).status_code == 200
    datos.update(oportunidad_id=o['id'], cliente_id=c_id, estado='cerrada', area_min_m2='82')
    assert client.post('/consola/oportunidades', data=datos).status_code == 200
    assert len(client.get('/api/oportunidades').json()) == 1
    assert client.get('/api/oportunidades/' + o['id']).json()['estado'] == 'cerrada'


def test_matching_global_no_depende_de_membresia(escenario_consola):
    # Quita la pertenencia de un anuncio sin borrar el inmueble consolidado.
    with escenario_consola['store'].connect() as db:
        db.execute("DELETE FROM search_memberships WHERE property_id='1-M1'")
    s = servicio_oportunidades()
    o = s.capturar(ClienteDatos(nombre='Global'), necesidades())
    resultados = s.coincidencias(o.id, servicio())
    assert any(r.inmueble.origen.id_original == '1-M1' for r in resultados)


def test_esquema_futuro_no_se_sobrescribe_y_crm_falla_sin_romper_catalogo(escenario_consola):
    s = servicio_oportunidades()
    s.guardar_cliente(ClienteDatos(nombre='Conservar'))
    with sqlite3.connect(s.repositorio.ruta) as db:
        db.execute('INSERT INTO consola_migraciones VALUES (2)')
    with pytest.raises(ErrorPersistencia):
        s.guardar_cliente(ClienteDatos(nombre='No guardar'))
    response = TestClient(app).get('/consola/')
    assert response.status_code == 200 and 'El catálogo sigue disponible' in response.text
    assert TestClient(app).get('/api/clientes').status_code == 503


def test_configuracion_no_permite_escribir_en_catalogo(escenario_consola, monkeypatch):
    ruta = escenario_consola['ruta']
    antes = hashlib.sha256(ruta.read_bytes()).hexdigest()
    monkeypatch.setenv('RADAR_CRM_DB', str(ruta))
    client = TestClient(app)
    assert client.post('/api/clientes', json={'nombre': 'No escribir'}).status_code == 503
    assert client.get('/consola/').status_code == 200
    assert hashlib.sha256(ruta.read_bytes()).hexdigest() == antes


def test_presupuesto_limite_y_orden_precio_con_desconocidos():
    a = inmueble(ofertas=(Oferta(operacion=Operacion.VENTA, precio=Decimal('110000000'), moneda='COP'),))
    b = inmueble(origen=Origen(fuente='portal', id_original='b'), ofertas=())
    c = inmueble(origen=Origen(fuente='portal', id_original='c'))
    assert comparar(necesidades(), a).confirmada
    assert [r.inmueble for r in buscar(necesidades(), [a, b, c], 'precio')] == [c, a, b]


def test_formulario_ubicaciones_manuales_y_preferencias(escenario_consola):
    client = TestClient(app)
    datos = {'nombre': 'Manual', 'operacion': 'arriendo', 'tipo': 'otro', 'ciudad': 'Otra ciudad',
             'otros_barrios': 'Barrio uno, Barrio dos', 'otros_zonas': 'Centro',
             'presupuesto_max': '1500000', 'area_min_m2': '40', 'parqueaderos_min': '1',
             'preferencias': ['parqueaderos_min'], 'observaciones': 'Texto libre'}
    assert client.post('/consola/oportunidades', data=datos).status_code == 200
    o = client.get('/api/oportunidades').json()[0]
    assert o['necesidades']['barrios'] == ['Barrio uno', 'Barrio dos']
    assert o['necesidades']['zonas'] == ['Centro']
    assert o['necesidades']['preferencias'] == ['parqueaderos_min']
    assert o['necesidades']['observaciones'] == 'Texto libre'
