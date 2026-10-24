from urllib.parse import parse_qs, urlsplit
import hashlib
from bs4 import BeautifulSoup
from fastapi.testclient import TestClient
from starlette.datastructures import QueryParams
from catalogo.identidad import identificar_inmueble
from consola.presentacion import leer_filtros, regreso_seguro, enlace_publico
from metro.web import app

def soup(response):
    return BeautifulSoup(response.text, 'html.parser')

def test_catalogo_consolidado_sin_ids_tecnicos(escenario_consola):
    r = TestClient(app).get('/consola/')
    assert r.status_code == 200
    pagina = soup(r)
    assert pagina.select_one('[data-total]').text == '26'
    assert len(pagina.select('.property-card')) == 12
    assert 'Radar Inmobiliario' in pagina.get_text(' ', strip=True)
    assert '1-M1' not in pagina.get_text()
    assert identificar_inmueble('metrocuadrado', '1-M1') not in pagina.get_text()
    assert 'Ficha consultada' in pagina.get_text() and 'Metrocuadrado' in pagina.get_text()
    assert all(i.get('loading') == 'lazy' for i in pagina.select('img'))
    assert len({a['href'] for a in pagina.select('.property-card h3 a')}) == 12

def test_filtros_y_parametros_reales_del_servicio(escenario_consola):
    params = {'ciudad': 'Bogotá', 'operacion': 'venta', 'moneda': 'COP',
              'precio_min': '101000000', 'precio_max': '105000000',
              'tipo_area': 'construida', 'area_min_m2': '81', 'area_max_m2': '85',
              'habitaciones_min': 3, 'banos_min': 2, 'parqueaderos_min': 0,
              'orden': 'precio_desc', 'limit': 2}
    pagina = soup(TestClient(app).get('/consola/', params=params))
    assert pagina.select_one('[data-total]').text == '5'
    assert len(pagina.select('.property-card')) == 2
    assert pagina.select_one('.property-card h3').get_text(strip=True) == 'Casa con jardín 05'
    assert pagina.select_one('#precio_max')['value'] == '105000000'
    assert pagina.select_one('#ciudad option[selected]')['value'] == 'Bogotá'
    assert '0 parq.' in pagina.get_text()

def test_pagina_ficha_y_regreso_conservan_estado(escenario_consola):
    client = TestClient(app)
    params = {'ciudad': 'Bogotá', 'tipos': 'casa', 'orden': 'id', 'limit': 2, 'offset': 2}
    pagina = soup(client.get('/consola/', params=params))
    ficha = soup(client.get(pagina.select_one('.property-card h3 a')['href']))
    volver = ficha.select_one('.back-link')['href']
    assert parse_qs(urlsplit(volver).query) == {k: [str(v)] for k, v in params.items()}
    repetida = soup(client.get(volver))
    assert [a['href'] for a in repetida.select('.property-card h3 a')] == [
        a['href'] for a in pagina.select('.property-card h3 a')]
    segunda = soup(client.get(pagina.select_one('a[rel=next]')['href']))
    assert not ({a['href'].split('?')[0] for a in segunda.select('.property-card h3 a')} &
                {a['href'].split('?')[0] for a in pagina.select('.property-card h3 a')})

def test_ficha_doble_oferta_procedencia_fechas_y_galeria(escenario_consola):
    id = identificar_inmueble('metrocuadrado', '1-M1')
    pagina = soup(TestClient(app).get('/consola/inmuebles/' + id))
    texto = pagina.get_text(' ', strip=True)
    assert '101.000.000' in texto and '1.000.000' in texto
    assert 'Venta' in texto and 'Arriendo' in texto
    assert 'Última extracción de la ficha' in texto and 'Última presencia en listados' in texto
    assert '20/10/2026 · 10:00' in texto and '24/10/2026 · 11:00' in texto
    assert len(pagina.select('.search-presences li')) == 2
    assert len(pagina.select('[data-index]')) == 3
    assert 'Terraza' in texto and 'Cocina integral' in texto
    assert 'Ver publicación original' in texto and 'no confirma una venta' in texto
    assert id not in texto and 'data_json' not in texto and 'normalized' not in texto

def test_estados_vacios_y_pagina_fuera_de_rango(escenario_consola):
    client = TestClient(app)
    assert 'No encontramos inmuebles con estos filtros' in soup(client.get('/consola/?texto=inexistente')).get_text()
    assert 'Esta página ya no tiene inmuebles' in soup(client.get('/consola/?offset=999')).get_text()

def test_filtros_invalidos_se_explican_en_html(escenario_consola):
    r = TestClient(app).get('/consola/?precio_min=100')
    assert r.status_code == 422 and 'text/html' in r.headers['content-type']
    assert 'Elige una operación y una moneda' in r.text
    r = TestClient(app).get('/consola/?area_min_m2=100&area_max_m2=50')
    assert r.status_code == 422 and 'El área mínima no puede superar' in r.text

def test_base_ausente_no_se_crea_y_error_es_claro(tmp_path, monkeypatch):
    ruta = tmp_path / 'ausente.sqlite'
    monkeypatch.setenv('METRO_DB', str(ruta))
    client = TestClient(app)
    assert client.get('/consola/').status_code == 503
    r = client.get('/consola/inmuebles/no-existe')
    assert r.status_code == 503 and 'No pudimos abrir esta ficha' in r.text
    assert not ruta.exists() and str(ruta) not in r.text

def test_ficha_ausente_y_regreso_seguro(escenario_consola):
    r = TestClient(app).get('/consola/inmuebles/no-existe?volver=https://externo.test')
    assert r.status_code == 404 and 'No encontramos este inmueble' in r.text
    for valor in ('https://externo.test', '//externo.test', '/api/runs', 'javascript:alert(1)'):
        assert regreso_seguro(valor) == '/consola/'
    assert enlace_publico('javascript:alert(1)') is None

def test_titulos_publicos_se_escapan(escenario_consola):
    datos = escenario_consola
    doc = datos['documentos']['1-M1']
    doc['normalized']['title'] = '<script>alert("ejecutado")</script>'
    datos['store'].result(datos['run'], '1-M1', 'success', doc)
    id = identificar_inmueble('metrocuadrado', '1-M1')
    r = TestClient(app).get('/consola/inmuebles/' + id)
    assert '<script>alert' not in r.text and '&lt;script&gt;' in r.text

def test_consultas_no_escriben_y_rutas_anteriores_siguen(escenario_consola):
    ruta = escenario_consola['ruta']
    antes = hashlib.sha256(ruta.read_bytes()).hexdigest()
    client = TestClient(app)
    for destino in ('/consola/', '/api/catalog', '/api/runs', '/', '/catalog',
                    '/consola/static/consola.css', '/consola/static/consola.js'):
        assert client.get(destino).status_code == 200
    assert hashlib.sha256(ruta.read_bytes()).hexdigest() == antes

def test_formulario_vacio_y_parametros_del_modelo():
    filtros = leer_filtros(QueryParams('texto=&operacion=&precio_min=&moneda=&limit=12'))
    assert filtros.texto is None and filtros.operacion is None
    assert filtros.tipo_area.value == 'construida' and filtros.limite == 12


def test_enlaces_malformados_o_con_credenciales_no_se_exponen():
    assert regreso_seguro('http://[') == '/consola/'
    assert enlace_publico('http://[') is None
    assert enlace_publico('https://usuario:clave@externo.test/foto.jpg') is None
    assert enlace_publico('https://:clave@externo.test/foto.jpg') is None

def test_ficha_sin_imagenes_tiene_alternativa_visual(escenario_consola):
    id = identificar_inmueble('metrocuadrado', '3-M3')
    pagina = soup(TestClient(app).get('/consola/inmuebles/' + id))
    assert not pagina.select('[data-gallery-main]')
    assert 'No hay una fotografía disponible' in pagina.get_text()
