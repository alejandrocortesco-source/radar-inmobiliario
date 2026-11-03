"""Presupuesto COP inclusivo: reglas, registros históricos y recorrido HTML real."""
from dataclasses import replace
from decimal import Decimal
import hashlib

from bs4 import BeautifulSoup
from fastapi.testclient import TestClient
from playwright.sync_api import expect
import pytest

from catalogo.modelos import Oferta, Operacion
from metro.web import app, servicio
from oportunidades.matching import comparar, diagnosticar, buscar
from oportunidades.modelos import Necesidades
from oportunidades.automatizacion import candidato
from consola.resultados import ordenar_resultados
from test_v03 import inmueble, necesidades
from test_browser import servidor, pagina, seleccionar_barrio

PRECIOS = (770_000_000, 800_000_000, 880_000_000, 769_000_000, 881_000_000, 8_000_000_000, 7_500_000_000)


def necesidad_cop():
    return Necesidades.model_validate(necesidades().model_dump() | {
        'presupuesto_min': '770000000', 'presupuesto_max': '880000000'})


@pytest.mark.parametrize('moneda', [None, 'COP', 'USD'])
@pytest.mark.parametrize('precio', PRECIOS)
def test_presupuesto_compara_precio_sin_condicion_de_moneda(precio, moneda):
    i = inmueble(ofertas=(Oferta(operacion=Operacion.VENTA, precio=Decimal(precio), moneda=moneda),))
    r = comparar(necesidad_cop(), i)
    if 770_000_000 <= precio <= 880_000_000:
        assert r is not None and r.confirmada
        assert not any('moneda' in p.lower() for p in r.cumple + r.pendientes)
        assert candidato(r)['hechos']['moneda'] == 'COP'
    else:
        assert r is None


@pytest.mark.parametrize('dato_faltante', ['ciudad', 'tipo', 'habitaciones'])
def test_incumplimiento_de_precio_excluye_aunque_falte_otro_dato(dato_faltante):
    i = replace(inmueble(ofertas=(Oferta(operacion=Operacion.VENTA, precio=Decimal('8000000000')),)),
                **{dato_faltante: None})
    d = diagnosticar(necesidad_cop(), [i])
    assert d['total_resultados'] == 0 and d['incompatibles'] == 1
    assert any(m['codigo'] == 'presupuesto' for m in d['motivos'])


@pytest.mark.parametrize('precio', [None, '', 'sin precio', 0, -1, True, 'NaN', 'Infinity'])
def test_precio_historico_ausente_o_invalido_sigue_pendiente(escenario_consola, precio):
    with escenario_consola['store'].connect() as db:
        db.execute("UPDATE runs SET config_json=json_remove(config_json,'$.listing_currency')")
    doc = escenario_consola['documentos']['1-M1']
    doc['normalized'].update(price=precio, currency=None)
    escenario_consola['store'].result(escenario_consola['run'], '1-M1', 'success', doc)
    i = next(i for i in servicio().listar() if i.origen.id_original == '1-M1')
    assert i.ofertas[0].moneda is None
    r = comparar(necesidad_cop(), i)
    assert r is not None and not r.confirmada
    assert r.oferta.precio is None  # No se reemplaza por cero.
    assert any('precio ausente o inválido' in p for p in r.pendientes)
    assert not any('moneda' in p.lower() for p in r.pendientes)
    assert comparar(necesidad_cop(), replace(i, ciudad='Medellín')) is None


def test_orden_precio_numerico_independiente_de_moneda():
    a = inmueble()
    items = [replace(a, origen=replace(a.origen, id_original=str(k)),
        ofertas=(Oferta(operacion=Operacion.VENTA, precio=p, moneda=m),))
        for k, (p, m) in enumerate([(Decimal('880000000'), 'COP'),
            (Decimal('770000000'), None), (Decimal('800000000'), 'USD'), (None, None)])]
    r = buscar(necesidad_cop(), items, 'precio')
    esperados = [Decimal('770000000'), Decimal('800000000'), Decimal('880000000'), None]
    assert [v.oferta.precio for v in r] == esperados
    assert [v.oferta.precio for v in ordenar_resultados(r, 'precio_asc')] == esperados
    assert [v.oferta.precio for v in ordenar_resultados(r, 'precio_desc')] == list(reversed(esperados[:-1])) + [None]


def preparar(escenario, moneda):
    # Históricos sin ninguna configuración que pueda completar la moneda ausente.
    with escenario['store'].connect() as db:
        db.execute("UPDATE runs SET config_json=json_remove(config_json,'$.listing_currency')")
    for n, (iid, doc) in enumerate(escenario['documentos'].items(), 1):
        doc['normalized'].update(price=PRECIOS[n-1] if n <= 7 else None if n == 8 else 'inválido' if n == 9 else 9_000_000_000,
                                 currency=moneda)
        if n == 6:
            doc['normalized']['city'] = None
        escenario['store'].result(escenario['run'], iid, 'success', doc)


@pytest.mark.parametrize('moneda', ['COP', None, '', 'USD'])
def test_confirmar_oportunidad_historica_y_vistas_sin_verificar_moneda(escenario_consola, moneda):
    preparar(escenario_consola, moneda)
    if moneda in (None, ''):
        assert all(o.moneda is None for i in servicio().listar() for o in i.ofertas)
    antes = hashlib.sha256(escenario_consola['ruta'].read_bytes()).hexdigest()
    c = TestClient(app)
    r = c.post('/v0.6/oportunidades', data={'nombre': 'Cliente COP sintético', 'operacion':'compra', 'tipo':'casa',
        'ciudad':'Bogotá', 'ubicaciones':['barrio:La Carolina'], 'presupuesto_min':'770000000', 'presupuesto_max':'880000000'})
    assert r.status_code == 200
    o = c.get('/api/oportunidades').json()[0]
    resultados = c.get(f"/api/oportunidades/{o['id']}/coincidencias").json()
    assert {v['inmueble']['origen']['id_original'] for v in resultados} == {'1-M1', '2-M2', '3-M3', '8-M8', '9-M9'}
    soup = BeautifulSoup(r.text, 'html.parser')
    assert len(soup.select('[data-candidate]')) == 5
    assert '$770.000.000' in r.text and '$880.000.000' in r.text
    assert '$8.000.000.000' not in r.text and '$7.500.000.000' not in r.text
    for url in [str(r.url), f"/consola/oportunidades/{o['id']}/coincidencias", f"/v0.4/oportunidades/{o['id']}/coincidencias"]:
        html = c.get(url).text
        assert 'Moneda sin verificar' not in html and 'Moneda por verificar' not in html
    assert hashlib.sha256(escenario_consola['ruta'].read_bytes()).hexdigest() == antes


@pytest.mark.parametrize('width', [1440, 390])
def test_presupuesto_cop_en_navegador_sin_selector_de_moneda(escenario_consola, servidor, pagina, width):
    preparar(escenario_consola, None)
    pagina.set_viewport_size({'width':width, 'height':900})
    pagina.goto(servidor + '/v0.6/nuevo')
    pagina.locator('#crm_nombre').fill('Cliente COP navegador')
    pagina.locator('#crm_tipo').select_option('casa')
    pagina.locator('#crm_ciudad').select_option(label='Bogotá')
    pagina.locator('#crm_presupuesto_min').fill('770000000')
    pagina.locator('#crm_presupuesto').fill('880000000')
    seleccionar_barrio(pagina, True)
    pagina.get_by_role('button', name='Confirmar y guardar oportunidad').click()
    expect(pagina.locator('[data-candidate]')).to_have_count(5)
    expect(pagina.locator('.candidate-table')).to_contain_text('$770.000.000')
    expect(pagina.locator('.candidate-table')).not_to_contain_text('$8.000.000.000')
    expect(pagina.locator('.candidate-table')).not_to_contain_text('Moneda sin verificar')
    pagina.wait_for_load_state('load')
    assert pagina.evaluate('document.documentElement.scrollWidth <= innerWidth')
    pagina.goto(servidor + '/v0.4/?operacion=venta&precio_min=770000000&precio_max=880000000&orden=precio_asc')
    expect(pagina.locator('.property-link')).to_have_count(3)
    expect(pagina.locator('#moneda')).to_have_count(0)
