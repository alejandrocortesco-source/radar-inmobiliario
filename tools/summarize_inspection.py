import json
from pathlib import Path

def walk(v):
    if isinstance(v, dict):
        yield v
        for x in v.values():
            yield from walk(x)
    elif isinstance(v, list):
        for x in v:
            yield from walk(x)

for path in Path('data/inspection').glob('*.json'):
    if path.name not in ('next.json',) and not path.name.startswith('detail-'):
        continue
    data = json.loads(path.read_text(encoding='utf-8'))
    print('\nFILE', path.name)
    for obj in walk(data):
        if isinstance(obj.get('initialResults'),dict):
            print('PROPS KEYS', list(obj))
            print('INITIAL', {k: len(v) if isinstance(v,list) else str(v)[:200] for k,v in obj['initialResults'].items()})
        if any(k in obj for k in ('property', 'propertyData', 'realEstate', 'inmueble', 'propertyDetail')):
            print('CANDIDATE', str(obj)[:1800].encode('ascii','replace').decode())
    if isinstance(data, dict):
        print('TEXT', data.get('text','')[:11000].encode('ascii','replace').decode())
        print('HEADINGS', str(data.get('headings')).encode('ascii','replace').decode())
        print('ROOT NEXT', str(data.get('next'))[-20000:].encode('ascii','replace').decode())
