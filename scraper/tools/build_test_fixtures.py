"""Regenera muestras públicas de las inspecciones locales; nunca consulta el portal."""
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from metro.extraction import walk, sanitize

component_root=Path(__file__).resolve().parents[1]
target=component_root/'tests/fixtures'
target.mkdir(parents=True,exist_ok=True)
for file in (component_root/'data/inspection').glob('detail-*.json'):
    data=json.loads(file.read_text(encoding='utf-8'))
    candidates=[x for x in walk(data.get('next',[])) if x.get('propertyId') and isinstance(x.get('propertyType'),dict)]
    if not candidates: continue
    raw=candidates[0]
    name=raw['propertyType']['nombre'].lower()
    if name in ('apartamento','oficina','consultorio'):
        (target/f'{name}.json').write_text(json.dumps(sanitize({'raw':raw,'text':data['text'],'url':data['url']}),ensure_ascii=False,indent=2),encoding='utf-8')
        print(name,raw['propertyId'])
