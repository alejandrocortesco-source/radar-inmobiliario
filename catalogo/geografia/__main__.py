"""python -m catalogo.geografia [ruta metro.sqlite]"""
import argparse
import json
from .persistencia import reprocesar
from ..persistencia.sqlite import BASE_PREDETERMINADA

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('origen', nargs='?', default=str(BASE_PREDETERMINADA))
args = parser.parse_args()
print(json.dumps(reprocesar(args.origen), ensure_ascii=False, indent=2))
