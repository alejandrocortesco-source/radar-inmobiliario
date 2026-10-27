"""Valida un anuncio real sin escribir en el catálogo ni en el CRM existente.

Ejecutar desde la raíz: python consola/tools/validar_matching_real.py
Genera un CRM nuevo y evidencia JSON bajo .tmp/validacion-matching-<UUID>/.
"""
import hashlib
import json
import os
from pathlib import Path
import sys
from uuid import uuid4

RAIZ = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(RAIZ), str(RAIZ / 'scraper')]

from catalogo.persistencia.sqlite import BASE_PREDETERMINADA, CatalogoSQLite
from catalogo.servicio import ServicioCatalogo
from oportunidades.modelos import Necesidades


def main():
    ruta = Path(os.getenv('METRO_DB', str(BASE_PREDETERMINADA))).resolve()
    crm_original = Path(os.getenv('RADAR_CRM_DB', str(ruta.with_name(ruta.stem + '-consola.sqlite')))).resolve()
    existentes = [p for p in (ruta, crm_original) if p.is_file()]
    huellas = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in existentes}
    catalogo = ServicioCatalogo(CatalogoSQLite(ruta))
    todos = catalogo.listar()
    candidatos = [(i, o) for i in todos for o in i.ofertas if o.moneda == 'COP' and o.precio
                  and i.ciudad and i.barrio and i.tipo and i.habitaciones is not None
                  and i.area_construida_m2 and i.barrio == 'La Carolina'
                  and i.origen.id_original == '3147-M5621082']
    if not candidatos:
        raise RuntimeError('No hay un anuncio real con datos suficientes para esta comprobación')
    i, oferta = min(candidatos, key=lambda par: par[1].precio)
    salida = RAIZ / '.tmp' / ('validacion-matching-' + str(uuid4()))
    salida.mkdir(parents=True)
    os.environ['METRO_DB'] = str(ruta)
    os.environ['RADAR_CRM_DB'] = str(salida / 'validacion-consola.sqlite')
    from fastapi.testclient import TestClient
    from metro.web import app
    cliente = TestClient(app)
    necesidades = Necesidades(
        operacion='compra' if oferta.operacion.value == 'venta' else 'arriendo', tipo=i.tipo,
        ciudad='Bogotá, D.C.' if i.ciudad == 'Bogotá D.C.' else i.ciudad, barrios=[i.barrio],
        presupuesto_max=oferta.precio, habitaciones_min=i.habitaciones,
        area_min_m2=i.area_construida_m2, banos_min=i.banos, parqueaderos_min=i.parqueaderos)
    c = cliente.post('/api/clientes', json={'nombre': 'Validación local v0.3'}).json()
    response = cliente.post('/api/oportunidades', json={'cliente_id': c['id'], 'necesidades': necesidades.model_dump(mode='json')})
    assert response.status_code == 201
    o = response.json()
    diagnostico = cliente.get(f"/api/oportunidades/{o['id']}/diagnostico").json()
    assert any(r['inmueble']['origen']['id_original'] == i.origen.id_original
               and r['inmueble']['origen']['fuente'] == i.origen.fuente
               and not r['pendientes'] for r in diagnostico['resultados'])
    assert diagnostico['compatibles'] >= 1
    # Un lugar conocido que no exista en este catálogo: todos los datos están presentes.
    negativa = necesidades.model_dump(mode='json') | {'ciudad': 'Ciudad de validación sin anuncios'}
    no = cliente.post('/api/oportunidades', json={'cliente_id': c['id'], 'necesidades': negativa}).json()
    sin = cliente.get(f"/api/oportunidades/{no['id']}/diagnostico").json()
    assert sin['total_resultados'] == 0
    assert cliente.get(f"/consola/?oportunidad={no['id']}").status_code == 200
    assert cliente.get('/api/catalog?limit=1').json()['total'] == len(todos)
    assert all(hashlib.sha256(Path(p).read_bytes()).hexdigest() == digest for p, digest in huellas.items())
    resumen = {
        'catalogo': str(ruta), 'crm_pruebas': os.environ['RADAR_CRM_DB'], 'total_catalogo': len(todos),
        'inmueble_real': {'id_interno': i.id_interno, 'id_original': i.origen.id_original,
                         'precio': str(oferta.precio), 'moneda': oferta.moneda, 'ciudad': i.ciudad,
                         'barrio': i.barrio, 'area_construida_m2': str(i.area_construida_m2),
                         'barrio_original': i.geografia.barrio_original,
                         'edificio': i.edificio, 'geografia_estado': i.geografia.estado,
                         'habitaciones': i.habitaciones, 'banos': i.banos, 'parqueaderos': i.parqueaderos,
                         'publicacion': i.origen.url},
        'necesidades': necesidades.model_dump(mode='json'), 'oportunidad_positiva': o['id'],
        'compatibles': diagnostico['compatibles'], 'pendientes': diagnostico['pendientes'],
        'inmueble_incluido': True, 'etapas': diagnostico['etapas'],
        'oportunidad_negativa': no['id'], 'sin_coincidencias': sin['total_resultados'],
        'motivos_negativa': sin['motivos'], 'huellas_originales_sin_cambios': huellas,
    }
    (salida / 'evidencia.json').write_text(json.dumps(resumen, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(resumen, ensure_ascii=True, indent=2))
    return resumen


if __name__ == '__main__':
    main()
