"""Minimiza diagnósticos antiguos: elimina claves de sesión y referencias a trackers."""
import json
from pathlib import Path
import sys
from urllib.parse import urlsplit
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from metro.extraction import sanitize

for file in (Path(__file__).resolve().parents[1]/'data/inspection').glob('*.json'):
    data=sanitize(json.loads(file.read_text(encoding='utf-8')))
    if file.name=='listing.json':
        data['scripts']=[{**s,'src':urlsplit(s['src']).path} for s in data.get('scripts',[])
                         if not s.get('src') or urlsplit(s['src']).hostname=='www.metrocuadrado.com']
    file.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
