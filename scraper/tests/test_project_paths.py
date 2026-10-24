"""Verifica que la reorganización no dependa del directorio de invocación."""
import json
from pathlib import Path
import subprocess
import sys

from metro.paths import COMPONENT_ROOT, DEFAULT_DB
from metro.scraper import Config
from metro.storage import Store
from metro.web import store as web_store


def test_default_data_is_component_local(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    assert DEFAULT_DB == COMPONENT_ROOT / 'data' / 'metro.sqlite'
    assert Path(Config().db) == DEFAULT_DB
    assert DEFAULT_DB.is_absolute()


def test_cli_from_unrelated_directory(tmp_path):
    database = tmp_path / 'check.sqlite'
    run_id = Store(database).new_run('https://www.metrocuadrado.com/inmuebles/', {})
    result = subprocess.run(
        [sys.executable, str(COMPONENT_ROOT / 'run.py'), '--db', str(database), 'status', str(run_id)],
        cwd=tmp_path, capture_output=True, text=True, encoding='utf-8', check=True,
    )
    assert json.loads(result.stdout)['id'] == run_id
    assert not (tmp_path / 'data').exists()


def test_web_honors_custom_database_after_chdir(monkeypatch, tmp_path):
    database = tmp_path / 'custom.sqlite'
    monkeypatch.setenv('METRO_DB', str(database))
    monkeypatch.chdir(tmp_path)
    assert Path(web_store().path) == database
