"""Nombres controlados, evidencia contradictoria y proyección histórica segura."""
from dataclasses import asdict
import hashlib
import json
import sqlite3

import pytest

from catalogo.geografia import normalizar_geografia, resolver_barrio, VERSION
from catalogo.geografia.persistencia import reprocesar, ruta_proyeccion
from catalogo.persistencia.sqlite import CatalogoSQLite
from test_sqlite import base, ID, INTERNO


@pytest.mark.parametrize('barrio,comun,edificio', [
    ('LA CAROLINA   EDIF CRIXTAL', 'LA CAROLINA', 'CRIXTAL'),
    ('LA CAROLINA EDIF. TORRE DE ALCALA', 'BARRIO LA CAROLINA', 'TORRE DE ALCALA'),
    ('La Carolina', 'LA CAROLINA EDIFICIO MONICA PATRICIA', 'MONICA PATRICIA'),
    ('RINCÓN DEL CHICÓ EDIFICIO CAROLINA', 'Rincon del Chico', 'CAROLINA'),
    ('LA CALLEJA EDIF TORRE NORTE', 'La Calleja', 'TORRE NORTE'),
])
def test_separa_edificio_solo_despues_de_barrio_controlado(barrio, comun, edificio):
    g = normalizar_geografia(ciudad='Bogotá, D.C.', barrio=barrio, barrio_comun=comun, zona='NORTE')
    assert g.estado == 'confirmada' and g.edificio == edificio
    assert 'EDIF' not in g.barrio.upper()
    assert g.barrio_original == barrio and g.barrio_comun_original == comun
    assert g.evidencias and g.version == VERSION
    if barrio.startswith('RINCÓN'):
        assert g.barrio_id == 'bogota:008411'


@pytest.mark.parametrize('barrio,comun,zona', [
    ('LAGUNETA', 'LA CAROLINA', 'Sur'),
    ('PLENITUD', 'LA CAROLINA', 'Norte'),
    ('LA CAROLINA', 'COUNTRY CLUB', 'Norte'),
    ('LA CAROLINA EDIF GUADAL POLO', 'LAS ACASIAS USAQUEN', 'Norte'),
    ('RINCON DEL CHICO EDIF CAROLINA', 'Chico', 'Norte'),
    ('LA CAROLINA', 'LA CAROLINA', 'Occidental'),
    ('LA CAROLINA DE SUBA', 'LA CAROLINA', 'Norte'),
    ('FOLEDO', 'LA CAROLINA', 'Norte'),
    ('LA CAROLINA', 'CERCA A UNICENTRO', 'Norte'),
])
def test_contradicciones_y_desconocidos_no_confirman(barrio, comun, zona):
    g = normalizar_geografia(ciudad='Bogotá', barrio=barrio, barrio_comun=comun, zona=zona)
    assert g.estado == 'pendiente' and g.barrio is None and g.barrio_id is None
    assert g.motivos and g.barrio_original == barrio


@pytest.mark.parametrize('valor', [' la  carolína ', 'BARRIO LA CAROLINA', 'La Carolina Usaquén'])
def test_variantes_estructuradas_no_busqueda_parcial(valor):
    assert resolver_barrio('BOGOTA D.C.', valor)[0]['id'] == 'bogota:008403'
    assert resolver_barrio('Medellín', valor)[0] is None
    assert resolver_barrio('Bogotá', 'Santa ' + valor)[0] is None


def test_calificador_sector_solo_si_esta_publicado_y_es_exacto():
    assert resolver_barrio('Bogotá', 'LA CAROLINA COUNTRY')[0] is None
    assert resolver_barrio('Bogotá', 'LA CAROLINA COUNTRY', sector='Country')[0]['id']=='bogota:008403'
    assert resolver_barrio('Bogotá', 'LA CAROLINA COUNTRY', sector='Otro')[0] is None
    assert normalizar_geografia(ciudad='Bogotá', barrio='NA', barrio_comun='La Carolina').estado=='confirmada'


def test_backfill_idempotente_no_modifica_fuente_ni_identidad_y_detecta_captura_nueva(base):
    antes = hashlib.sha256(base.read_bytes()).hexdigest()
    repo = CatalogoSQLite(base)
    originales = repo.listar()
    assert not ruta_proyeccion(base).exists()  # GET no migra ni escribe.
    assert reprocesar(base)['actualizados'] == 2
    assert reprocesar(base)['actualizados'] == 0
    assert repo.listar() == originales
    assert hashlib.sha256(base.read_bytes()).hexdigest() == antes
    with sqlite3.connect(base) as db:
        d = json.loads(db.execute('SELECT data_json FROM properties WHERE id=?', (ID,)).fetchone()[0])
        d['normalized'].update(neighborhood='LA CAROLINA EDIF CRIXTAL', common_neighborhood='La Carolina')
        db.execute('UPDATE properties SET data_json=? WHERE id=?', (json.dumps(d), ID))
    i = repo.obtener(INTERNO)
    assert i.barrio=='La Carolina' and i.edificio=='CRIXTAL' and i.id_interno==INTERNO
    assert reprocesar(base)['actualizados'] == 1
    assert reprocesar(base)['actualizados'] == 0
    with sqlite3.connect(ruta_proyeccion(base)) as db:
        guardado = json.loads(db.execute('SELECT datos_json FROM ubicaciones WHERE id_original=?', (ID,)).fetchone()[0])
        db.execute('UPDATE ubicaciones SET version=?', ('reglas-anteriores',))
    assert guardado['barrio_original'] == d['normalized']['neighborhood']
    assert repo.obtener(INTERNO).geografia == i.geografia  # Caché obsoleta ignorada.
    assert reprocesar(base)['actualizados'] == 2
    with pytest.raises(ValueError):
        reprocesar(base, base)


def test_proyeccion_incompleta_no_impide_lectura_y_error_revierte_migracion(base):
    reprocesar(base)
    proyeccion = ruta_proyeccion(base)
    with sqlite3.connect(proyeccion) as db:
        db.execute('UPDATE ubicaciones SET datos_json=?', ('{}',))
    assert CatalogoSQLite(base).obtener(INTERNO).barrio=='La Carolina'
    # Simula un fallo de escritura en medio de la transacción.
    with sqlite3.connect(proyeccion) as db:
        db.execute("UPDATE ubicaciones SET version='vieja'")
        db.execute("CREATE TRIGGER impedir BEFORE UPDATE ON ubicaciones BEGIN SELECT RAISE(ABORT,'fallo de prueba'); END")
    with pytest.raises(sqlite3.IntegrityError):
        reprocesar(base)
    with sqlite3.connect(proyeccion) as db:
        assert {r[0] for r in db.execute('SELECT version FROM ubicaciones')} == {'vieja'}
