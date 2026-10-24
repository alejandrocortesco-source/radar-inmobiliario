"""Pruebas con bases sintéticas: nunca abren ni copian la base real."""

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from catalogo.identidad import identificar_inmueble
from catalogo.modelos import Calidad, Disponibilidad, Operacion, TipoInmueble
from catalogo.persistencia.sqlite import (
    BASE_PREDETERMINADA, CatalogoSQLite, ErrorCatalogoSQLite,
)


A = 'https://www.metrocuadrado.com/inmuebles/venta/bogota/norte'
B = 'https://www.metrocuadrado.com/inmuebles/venta/bogota/centro'
ID = '001-M1'
INTERNO = identificar_inmueble('metrocuadrado', ID)
T1 = '2026-10-20T12:00:00+00:00'
T2 = '2026-10-21T12:00:00+00:00'
T3 = '2026-10-24T12:00:00+00:00'


@pytest.fixture
def base(tmp_path):
    ruta = tmp_path / 'base con espacios # y ?.sqlite'
    # Windows no admite ? en un nombre de archivo.
    ruta = ruta.with_name(ruta.name.replace('?', 'más'))
    documento = {
        'normalized': {
            'title': 'Apartamento con terraza', 'description': 'Descripción completa',
            'property_type': 'Apartaestudio', 'operation': 'Venta y Arriendo',
            'price': 500000000, 'currency': None, 'city': 'Bogotá',
            'zone': 'Norte', 'neighborhood': 'La Carolina', 'address': 'Calle pública',
            'area': 90, 'built_area': 85.25, 'built_area_unit': 'm²',
            'private_area': 80, 'private_area_unit': 'm2',
            'rooms': 3, 'bathrooms': 2, 'garages': 0, 'stratum': 5,
            'update_date': T1,
        },
        'extra': {'salePrice': 500000000, 'rentPrice': 2000000},
        'features': [{'title': 'Interiores', 'items': ['Terraza', 'Cocina integral']}],
        'photos': ['https://portal.test/1.jpg', 'https://portal.test/1.jpg', 'https://portal.test/2.jpg'],
        'quality': 'success',
    }
    contenido = json.dumps(documento, ensure_ascii=False)
    with sqlite3.connect(ruta) as db:
        db.executescript("""
            PRAGMA user_version=1;
            CREATE TABLE properties (
                id TEXT PRIMARY KEY, url TEXT UNIQUE NOT NULL, data_json TEXT,
                title TEXT, price REAL, city TEXT, property_type TEXT, updated TEXT,
                needs_refresh INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE search_memberships (
                search_url TEXT NOT NULL, property_id TEXT NOT NULL, state TEXT,
                first_seen TEXT, last_verified_at TEXT, last_seen_run INTEGER,
                missing_streak INTEGER DEFAULT 0, last_missing_run INTEGER,
                PRIMARY KEY(search_url, property_id));
            CREATE TABLE runs (id INTEGER PRIMARY KEY, config_json TEXT NOT NULL);
            CREATE TABLE jobs (
                run_id INTEGER, property_id TEXT, status TEXT, data_json TEXT,
                PRIMARY KEY(run_id, property_id));
        """)
        db.execute('INSERT INTO properties VALUES(?,?,?,?,?,?,?,?,?)',
                   (ID, 'https://portal.test/' + ID, contenido, 'Título anterior',
                    1, 'Ciudad anterior', 'Apartamento', T2, 1))
        db.execute('INSERT INTO properties(id,url) VALUES(?,?)',
                   ('0002', 'https://portal.test/0002'))
        for url, estado, primera, ultima in (
            (A, 'active', T1, T3), (B, 'removed', T2, T2),
        ):
            db.execute('INSERT INTO search_memberships VALUES(?,?,?,?,?,?,?,?)',
                       (url, ID, estado, primera, ultima, 1, 0, None))
        db.execute('INSERT INTO runs VALUES(1,?)', ('{"listing_currency":"COP"}',))
        db.execute('INSERT INTO jobs VALUES(1,?,?,?)', (ID, 'success', contenido))
        # Una captura nueva parcial no sustituye el catálogo fiable ni su moneda.
        db.execute('INSERT INTO runs VALUES(2,?)', ('{"listing_currency":"USD"}',))
        db.execute('INSERT INTO jobs VALUES(2,?,?,?)', (ID, 'partial', '{"quality":"partial"}'))
    return ruta


def test_catalogo_completo_deduplica_busquedas_e_incluye_pendientes(base):
    fichas = CatalogoSQLite(base).listar()
    assert len(fichas) == 2
    assert len({f.id_interno for f in fichas}) == 2
    assert [f.id_interno for f in fichas] == sorted(f.id_interno for f in fichas)
    pendiente = next(f for f in fichas if f.origen.id_original == '0002')
    assert pendiente.calidad == Calidad.DESCONOCIDA
    assert pendiente.disponibilidad == Disponibilidad.DESCONOCIDA
    assert pendiente.ofertas == ()
    assert pendiente.titulo is None


def test_ficha_recupera_atributos_precios_fotos_y_procedencia(base):
    ficha = CatalogoSQLite(base).obtener(INTERNO)
    assert ficha.id_interno == INTERNO
    assert ficha.origen.fuente == 'metrocuadrado'
    assert ficha.origen.id_original == ID
    assert ficha.origen.url == 'https://portal.test/' + ID
    assert ficha.titulo == 'Apartamento con terraza'
    assert ficha.descripcion == 'Descripción completa'
    assert ficha.tipo == TipoInmueble.APARTAMENTO
    assert ficha.origen.tipo_original == 'Apartaestudio'
    assert ficha.origen.operacion_original == 'Venta y Arriendo'
    assert ficha.ciudad == 'Bogotá' and ficha.barrio == 'La Carolina'
    assert ficha.zona == 'Norte' and ficha.direccion == 'Calle pública'
    assert ficha.area_publicada_m2 is None  # Unidad no confirmada.
    assert ficha.area_construida_m2 == Decimal('85.25')
    assert ficha.area_privada_m2 == Decimal('80')
    assert (ficha.habitaciones, ficha.banos, ficha.parqueaderos, ficha.estrato) == (3, 2, 0, 5)
    assert ficha.caracteristicas == ('Interiores: Terraza', 'Interiores: Cocina integral')
    assert ficha.fotos == ('https://portal.test/1.jpg', 'https://portal.test/2.jpg')
    assert [(o.operacion, o.precio, o.moneda) for o in ficha.ofertas] == [
        (Operacion.VENTA, Decimal('500000000'), 'COP'),
        (Operacion.ARRIENDO, Decimal('2000000'), 'COP'),
    ]
    assert ficha.calidad == Calidad.COMPLETA
    assert ficha.requiere_revision  # Independiente de la calidad de la ficha retenida.
    assert CatalogoSQLite(base).listar().count(ficha) == 1


def test_busquedas_disponibilidad_y_fechas_no_se_confunden(base):
    ficha = CatalogoSQLite(base).obtener(INTERNO)
    assert {b.id_busqueda for b in ficha.origen.busquedas} == {A, B}
    assert ficha.disponibilidad == Disponibilidad.ACTIVO
    assert {b.url for b in ficha.origen.busquedas} == {A, B}
    assert ficha.origen.primera_observacion == datetime.fromisoformat(T1)
    assert ficha.origen.actualizado_en_fuente == datetime.fromisoformat(T1)
    assert ficha.origen.ultima_extraccion == datetime.fromisoformat(T2)
    assert ficha.origen.ultima_verificacion == datetime.fromisoformat(T3)
    assert ficha.origen.busquedas[0].ultima_verificacion.tzinfo == timezone.utc


def test_retirados_siguen_en_catalogo(base):
    with sqlite3.connect(base) as db:
        db.execute("UPDATE search_memberships SET state='removed'")
    assert CatalogoSQLite(base).obtener(INTERNO).disponibilidad == Disponibilidad.RETIRADO
    assert len(CatalogoSQLite(base).listar()) == 2


def test_ausente_o_parametro_sql_no_devuelven_otra_ficha(base):
    repo = CatalogoSQLite(base)
    assert repo.obtener('no-existe') is None
    assert repo.obtener("' OR 1=1 --") is None
    assert repo.obtener(ID) is None  # La interfaz pública recibe ID interno.
    with pytest.raises(TypeError):
        repo.obtener(None)


@pytest.mark.parametrize('metodo', ['listar', 'obtener'])
def test_base_ausente_no_crea_archivo_ni_directorio(tmp_path, metodo):
    ruta = tmp_path / 'directorio-inexistente' / 'ausente.sqlite'
    repo = CatalogoSQLite(ruta)
    with pytest.raises(FileNotFoundError, match='No existe la base SQLite'):
        getattr(repo, metodo)(INTERNO) if metodo == 'obtener' else repo.listar()
    assert not ruta.exists()
    assert not ruta.parent.exists()


def test_base_vacia_y_base_corrupta_dan_error_claro_sin_migrar(tmp_path):
    vacia = tmp_path / 'vacia.sqlite'
    with sqlite3.connect(vacia) as db:
        db.execute('PRAGMA user_version=0')
    antes = vacia.read_bytes()
    with pytest.raises(ErrorCatalogoSQLite, match='esquema incremental'):
        CatalogoSQLite(vacia).listar()
    assert vacia.read_bytes() == antes
    corrupta = tmp_path / 'corrupta.sqlite'
    corrupta.write_text('esto no es una base SQLite')
    with pytest.raises(ErrorCatalogoSQLite, match='No se pudo leer'):
        CatalogoSQLite(corrupta).listar()


def test_lecturas_no_alteran_archivos_esquema_version_ni_registros(base):
    def huella():
        return {p.name: (hashlib.sha256(p.read_bytes()).hexdigest(), p.stat().st_mtime_ns)
                for p in base.parent.iterdir() if p.is_file()}
    antes = huella()
    repo = CatalogoSQLite(base)
    repo.listar()
    repo.obtener(INTERNO)
    repo.obtener('ausente')
    assert huella() == antes
    with sqlite3.connect(base) as db:
        assert db.execute('PRAGMA user_version').fetchone()[0] == 1
        assert db.execute('SELECT count(*) FROM properties').fetchone()[0] == 2


def test_uri_ro_impide_escritura_aun_desactivando_query_only(base):
    repo = CatalogoSQLite(base)
    with repo._conexion() as db:
        db.execute('PRAGMA query_only=OFF')
        with pytest.raises(sqlite3.OperationalError, match='readonly'):
            db.execute("UPDATE properties SET title='no permitido'")
    assert repo.obtener(INTERNO).titulo == 'Apartamento con terraza'


def test_lee_datos_confirmados_en_wal_sin_ignorar_actualizaciones(base):
    with sqlite3.connect(base) as escritor:
        assert escritor.execute('PRAGMA journal_mode=WAL').fetchone()[0] == 'wal'
        escritor.execute("UPDATE properties SET needs_refresh=0 WHERE id=?", (ID,))
        escritor.commit()
        assert base.with_name(base.name + '-wal').exists()
        assert CatalogoSQLite(base).obtener(INTERNO).requiere_revision is False
        escritor.execute("UPDATE properties SET needs_refresh=1 WHERE id=?", (ID,))
        escritor.commit()
        assert CatalogoSQLite(base).obtener(INTERNO).requiere_revision is True


def test_ficha_y_presencias_utilizan_una_instantanea_consistente(base):
    with sqlite3.connect(base) as escritor:
        escritor.execute('PRAGMA journal_mode=WAL')
        repo = CatalogoSQLite(base)
        with repo._conexion() as lector:
            def escribir_entre_consultas(sql):
                if sql.startswith('SELECT * FROM search_memberships'):
                    escritor.execute("UPDATE search_memberships SET state='removed'")
                    escritor.commit()
            lector.set_trace_callback(escribir_entre_consultas)
            ficha = repo._leer(lector, ID)[0]
            assert ficha.disponibilidad == Disponibilidad.ACTIVO
        assert repo.obtener(INTERNO).disponibilidad == Disponibilidad.RETIRADO


@pytest.mark.parametrize('contenido', ['{json roto', '[]', '{"normalized": []}', '{"photos": {}}', '{"features": {}}'])
def test_json_invalido_no_se_oculta_como_catalogo_vacio(base, contenido):
    with sqlite3.connect(base) as db:
        db.execute('UPDATE properties SET data_json=? WHERE id=?', (contenido, ID))
    with pytest.raises(ErrorCatalogoSQLite, match='Datos inválidos en el anuncio 001-M1'):
        CatalogoSQLite(base).listar()


def test_valores_desconocidos_y_ambiguos_no_se_inventan(base):
    documento = {
        'normalized': {
            'operation': 'arriendo', 'price': 'Desde 1000', 'currency': '$',
            'property_type': 'Tipo especial', 'rooms': True, 'bathrooms': '1.5',
            'garages': 0, 'stratum': 0, 'area': 90,
            'built_area': 80, 'built_area_unit': 'ft2',
            'update_date': '2026-10-24',
        }, 'quality': 'partial',
    }
    with sqlite3.connect(base) as db:
        db.execute('UPDATE properties SET data_json=?,updated=? WHERE id=?',
                   (json.dumps(documento), '2026-10-24', ID))
    ficha = CatalogoSQLite(base).obtener(INTERNO)
    assert ficha.ofertas[0].operacion == Operacion.ARRIENDO
    assert ficha.ofertas[0].precio is None
    assert ficha.ofertas[0].moneda is None
    assert ficha.tipo == TipoInmueble.OTRO
    assert ficha.habitaciones is None and ficha.banos is None
    assert ficha.parqueaderos == 0 and ficha.estrato is None
    assert ficha.area_publicada_m2 is None and ficha.area_construida_m2 is None
    assert ficha.origen.ultima_extraccion is None
    assert ficha.origen.actualizado_en_fuente is None
    assert ficha.calidad == Calidad.PARCIAL


def test_sin_evidencia_de_moneda_no_asume_cop_y_conserva_precision(base):
    documento = {
        'normalized': {'operation': 'venta', 'price': Decimal('1234.56')},
        'quality': 'success',
    }
    # JSON numérico decimal, no serialización a float.
    contenido = '{"normalized":{"operation":"venta","price":1234.56},"quality":"success"}'
    with sqlite3.connect(base) as db:
        db.execute('UPDATE properties SET data_json=? WHERE id=?', (contenido, ID))
    ficha = CatalogoSQLite(base).obtener(INTERNO)
    assert ficha.ofertas[0].precio == documento['normalized']['price']
    assert ficha.ofertas[0].moneda is None


def test_ruta_predeterminada_independiente_de_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert CatalogoSQLite().ruta == BASE_PREDETERMINADA
    assert BASE_PREDETERMINADA.parts[-3:] == ('scraper', 'data', 'metro.sqlite')
