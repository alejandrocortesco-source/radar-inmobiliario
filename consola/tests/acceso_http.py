"""Entorno HTTP local explícito compartido; sin excepciones en producción."""
import functools

import pytest
from starlette.testclient import TestClient


@pytest.fixture(autouse=True)
def acceso_local_sintetico(monkeypatch):
    monkeypatch.setenv('RADAR_AUTH_MODE', 'local')
    for name in ('K_SERVICE', 'K_REVISION', 'K_CONFIGURATION', 'RADAR_IAP_AUDIENCE', 'RADAR_PUBLIC_ORIGIN'):
        monkeypatch.delenv(name, raising=False)
    # TestClient simula una conexión real de loopback y el Origin que enviaría
    # el navegador. Las pruebas de acceso pueden sustituir ambos explícitamente.
    original = TestClient.__init__

    @functools.wraps(original)
    def init(self, app, *args, **kwargs):
        if not args:
            kwargs.setdefault('base_url', 'http://127.0.0.1')
        kwargs.setdefault('client', ('127.0.0.1', 50000))
        kwargs.setdefault('headers', {'Origin': kwargs.get('base_url', 'http://127.0.0.1')})
        original(self, app, *args, **kwargs)

    monkeypatch.setattr(TestClient, '__init__', init)
