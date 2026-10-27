"""Auditoría local de geografía; no modifica el catálogo ni el CRM.

python consola/tools/auditar_geografia.py genera evidencia en .tmp/geografia/.
"""
from collections import Counter
from dataclasses import asdict
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import sqlite3
import sys

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))
from catalogo.persistencia.sqlite import CatalogoSQLite, BASE_PREDETERMINADA
from catalogo.geografia.persistencia import reprocesar
from consola.ubicaciones import opciones_ubicacion


def main():
    ruta = Path(os.environ.get('METRO_DB', BASE_PREDETERMINADA)).resolve()
    crm = Path(os.environ.get('RADAR_CRM_DB', ruta.with_name(ruta.stem + '-consola.sqlite')))
    huellas = {str(p): sha256(p.read_bytes()).hexdigest() for p in (ruta, crm) if p.is_file()}
    with sqlite3.connect(ruta.as_uri() + '?mode=ro', uri=True) as db:
        docs = {id: json.loads(d) for id, d in db.execute('SELECT id,data_json FROM properties')}
    todos = CatalogoSQLite(ruta).listar()
    marca = re.compile(r'\bEDIF(?:ICIO)?\b', re.I)
    edificios = [i for i in todos if any(marca.search(v or '') for v in
        (i.geografia.barrio_original, i.geografia.barrio_comun_original))]
    iguales = sum(d.get('normalized', {}).get('neighborhood') ==
        (d.get('sources', {}).get('flight_property') or d.get('extra', {})).get('neighborhood') for d in docs.values())
    migracion = reprocesar(ruta)
    segunda = reprocesar(ruta)
    assert segunda['actualizados'] == 0
    despues = CatalogoSQLite(ruta).listar()
    assert todos == despues
    assert all(sha256(Path(p).read_bytes()).hexdigest() == h for p, h in huellas.items())
    opciones = opciones_ubicacion(todos, {})['ubicaciones_crm']
    resumen = {
        'ruta_catalogo': str(ruta), 'total': len(todos), 'raw_igual_a_extraido': iguales,
        'barrios_originales_distintos': len({i.geografia.barrio_original for i in todos}),
        'registros_con_marcador_edificio_antes': len(edificios),
        'edificios_separados_con_barrio_confirmado': sum(i.geografia.estado == 'confirmada' for i in edificios),
        'con_marcador_pendientes': sum(i.geografia.estado == 'pendiente' for i in edificios),
        'nombres_edificio_en_selector_despues': sum(bool(marca.search(o['nombre'])) for o in opciones if o['tipo']=='barrio'),
        'estados_geograficos': dict(Counter(i.geografia.estado for i in todos)),
        'barrios_confirmados': dict(Counter(i.barrio for i in todos if i.barrio)),
        'motivos_pendientes': dict(Counter(m for i in todos for m in i.geografia.motivos)),
        'selector': opciones, 'migracion': migracion, 'segunda_ejecucion': segunda,
        'huellas_originales_sin_cambios': huellas,
        'ejemplos_edificios': [dict(id=i.origen.id_original, **asdict(i.geografia)) for i in edificios],
        'pendientes': [dict(id=i.origen.id_original, **asdict(i.geografia)) for i in todos if i.geografia.estado=='pendiente'],
    }
    salida = RAIZ / '.tmp' / 'geografia'
    salida.mkdir(parents=True, exist_ok=True)
    (salida / 'auditoria.json').write_text(json.dumps(resumen, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k:v for k,v in resumen.items() if k not in ('pendientes','ejemplos_edificios','selector')}, ensure_ascii=True, indent=2))


if __name__ == '__main__':
    main()
