"""Rutas del componente independientes del directorio desde el que se invoca."""
from pathlib import Path
import sys

COMPONENT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = COMPONENT_ROOT / 'data'
DEFAULT_DB = DATA_DIR / 'metro.sqlite'

# Los componentes hermanos se importan también con python -m metro desde scraper/.
# El contenedor Job existente, sin catalogo/, no necesita esta integración web.
REPOSITORY_ROOT = COMPONENT_ROOT.parent
if (REPOSITORY_ROOT / 'catalogo').is_dir() and str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))
