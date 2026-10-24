"""Rutas del componente independientes del directorio desde el que se invoca."""
from pathlib import Path

COMPONENT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = COMPONENT_ROOT / 'data'
DEFAULT_DB = DATA_DIR / 'metro.sqlite'
