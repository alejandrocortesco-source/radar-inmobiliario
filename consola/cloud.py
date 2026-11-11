"""Entrada de producción con autenticación antes de tocar almacenamiento."""
import os
from consola.acceso import AccesoRadar
from consola.durable import WebDurable
from metro.web import app as aplicacion

if not os.getenv('RADAR_STATE_BUCKET') or os.getenv('RADAR_AUTH_MODE') != 'iap':
    raise RuntimeError('Cloud Run requiere IAP y almacenamiento durable configurados')
app = AccesoRadar(WebDurable(aplicacion))
