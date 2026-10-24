"""Datos sintéticos: estas pruebas no utilizan la base real."""
from pathlib import Path
import pytest
from metro.storage import Store

A = 'https://www.metrocuadrado.com/inmuebles/venta/bogota/la-carolina'
B = 'https://www.metrocuadrado.com/inmuebles/venta/bogota/norte'

@pytest.fixture
def escenario_consola(tmp_path, monkeypatch):
    ruta = tmp_path / 'consola.sqlite'
    monkeypatch.setenv('METRO_DB', str(ruta))
    store = Store(ruta)
    run = store.new_run(A, {'urls': [A, B], 'listing_currency': 'COP'})
    links = [{'id': f'{n}-M{n}', 'url': f'https://www.metrocuadrado.com/inmueble/casa/{n}-M{n}',
              'raw': {'mtiponegocio': 'venta', 'mvalorventa': 100_000_000 + n * 1_000_000}}
             for n in range(1, 27)]
    store.save_page(run, 1, '1', A, 'todos', links, None, search_url=A)
    store.save_page(run, 1, '1', B, 'repetido', [links[0]], None, search_url=B)
    store.plan_incremental(run)
    documentos = {}
    for n, link in enumerate(links, 1):
        doc = {
            'normalized': {
                'title': f'Casa con jardín {n:02}', 'description': 'Una casa luminosa.\nCon terraza y jardín.',
                'price': 100_000_000 + n * 1_000_000, 'currency': 'COP',
                'operation': 'Venta y Arriendo' if n == 1 else 'venta',
                'property_type': 'Casa', 'city': 'Bogotá' if n <= 13 else 'Medellín',
                'neighborhood': 'La Carolina', 'zone': 'Norte', 'address': 'Dirección pública',
                'built_area': 80 + n, 'built_area_unit': 'm²', 'private_area': 70 + n,
                'private_area_unit': 'm²', 'rooms': 3, 'bathrooms': 2, 'garages': 0,
            },
            'quality': 'success',
            'photos': ['https://images.test/uno.jpg', 'https://images.test/dos.jpg', 'https://images.test/rota.jpg'] if n == 1 else ([] if n % 3 == 0 else ['https://images.test/rota.jpg']),
            'features': [{'title': 'Interiores', 'items': ['Terraza', 'Cocina integral']}],
            'fields': {}, 'sources': {}, 'extra': {'rentPrice': 1_000_000} if n == 1 else {},
            'media': {}, 'visible_text': '', 'errors': [],
        }
        if n <= 2:
            doc['normalized'].update(
                latitude=4.7, longitude=-74.04,
                portal_map_url=link['url'] + '#location-section',
                map_url='https://www.openstreetmap.org/?mlat=4.7&mlon=-74.04#map=16/4.7/-74.04')
            doc['extra']['ubicacionaproximada'] = 'S' if n == 1 else 'N'
        documentos[link['id']] = doc
        store.result(run, link['id'], 'success', doc)
    with store.connect() as db:
        db.execute("UPDATE properties SET updated='2026-10-20T15:00:00+00:00'")
        db.execute("UPDATE search_memberships SET last_verified_at='2026-10-24T16:00:00+00:00'")
    return {'store': store, 'ruta': ruta, 'run': run, 'documentos': documentos,
            'raiz': Path(__file__).resolve().parents[2]}
