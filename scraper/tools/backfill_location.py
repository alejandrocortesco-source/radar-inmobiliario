"""Añade enlaces de mapa a JSON guardados, sin repetir visitas al portal."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from metro.extraction import add_location_fields
from metro.paths import DEFAULT_DB
from metro.storage import Store, dumps


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', default=str(DEFAULT_DB))
    args = parser.parse_args()
    store = Store(args.db)
    counts = {'properties': 0, 'jobs': 0, 'with_map': 0, 'without_map': 0}
    with store.connect() as db:
        # Evita perder actualizaciones concurrentes entre lectura y escritura.
        db.execute('BEGIN IMMEDIATE')
        for table, key in (('properties', 'id'), ('jobs', 'property_id')):
            query = ('SELECT p.id,p.url,p.data_json FROM properties p WHERE p.data_json IS NOT NULL'
                     if table == 'properties' else
                     'SELECT j.property_id,j.run_id,p.url,j.data_json FROM jobs j JOIN properties p ON p.id=j.property_id WHERE j.data_json IS NOT NULL')
            for row in db.execute(query).fetchall():
                data = add_location_fields(json.loads(row['data_json']), row['url'])
                params = [dumps(data), row[key]]
                condition = f'{key}=?'
                if table == 'jobs':
                    condition += ' AND run_id=?'
                    params.append(row['run_id'])
                db.execute(f'UPDATE {table} SET data_json=? WHERE {condition}', params)
                counts[table] += 1
                if table == 'properties':
                    counts['with_map' if data['normalized']['map_url'] else 'without_map'] += 1
    print(dumps(counts))


if __name__ == '__main__':
    main()
