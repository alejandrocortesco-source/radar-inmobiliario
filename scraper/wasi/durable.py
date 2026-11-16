"""Snapshots SQLite consistentes en objeto único; nunca SQLite sobre FUSE.

El adaptador se puede sustituir sin cambiar entidades ni el scraper. El lock
remoto no expira automáticamente: tras una terminación forzosa requiere comprobar
que no quedan ejecuciones activas antes de retirarlo en Cloud Storage.
"""
import io
import sqlite3
import tarfile
import tempfile
import uuid
from pathlib import Path
from contextlib import closing

ARCHIVOS = ('metro.sqlite', 'wasi.sqlite', 'fincaraiz.sqlite', 'fincaraiz-geografia.sqlite', 'metro-consola.sqlite', 'metro-geografia.sqlite', 'wasi-geografia.sqlite')


def empaquetar(carpeta):
    salida = io.BytesIO()
    with tempfile.TemporaryDirectory(dir=carpeta) as temporal, tarfile.open(fileobj=salida, mode='w:gz') as tar:
        for nombre in ARCHIVOS:
            origen = Path(carpeta) / nombre
            if not origen.is_file():
                continue
            destino = Path(temporal) / nombre
            with closing(sqlite3.connect(origen.as_uri() + '?mode=ro', uri=True)) as src, closing(sqlite3.connect(destino)) as dst:
                src.backup(dst)
            tar.add(destino, arcname=nombre, recursive=False)
    return salida.getvalue()


def restaurar(contenido, carpeta):
    carpeta = Path(carpeta).resolve()
    with tarfile.open(fileobj=io.BytesIO(contenido), mode='r:gz') as tar:
        miembros = tar.getmembers()
        if not miembros or any(not m.isfile() or m.name not in ARCHIVOS for m in miembros) or len({m.name for m in miembros}) != len(miembros):
            raise ValueError('Snapshot de estado inválido')
        # Validar todo antes de escribir; nunca extractall sobre contenido remoto.
        for m in miembros:
            destino = carpeta / m.name
            if destino.exists():
                raise ValueError('Restaurar exige un directorio sin bases existentes')
        carpeta.mkdir(parents=True, exist_ok=True)
        for m in miembros:
            (carpeta / m.name).write_bytes(tar.extractfile(m).read())


class EstadoGCS:
    def __init__(self, bucket, objeto='radar/state.tar.gz', client=None):
        from ejecuciones.entorno import settings
        settings()
        if client is None:
            from google.cloud import storage
            client = storage.Client()  # ADC: identidad del Job, sin claves JSON.
        self.bucket = client.bucket(bucket)
        self.objeto = objeto
        self.estado = self.bucket.blob(objeto)
        self.lock = self.bucket.blob(objeto + '.lock')
        self.generacion = 0
        self.lock_generacion = None
        self.lock_token = str(uuid.uuid4())

    def __enter__(self):
        try:
            self.lock.upload_from_string(self.lock_token, if_generation_match=0, timeout=30)
        except Exception:
            # Una respuesta perdida no prueba que la creación del lock haya fallado.
            try:
                self.lock.reload(timeout=15)
                generation = int(self.lock.generation)
                content = self.lock.download_as_bytes(if_generation_match=generation, timeout=15)
                if content != self.lock_token.encode():
                    raise RuntimeError('El bloqueo pertenece a otra operación')
                self.lock_generacion = generation
                return self
            except Exception:
                pass
            raise
        self.lock_generacion = self.lock.generation
        return self

    def cargar(self, carpeta):
        self.estado = self.bucket.blob(self.objeto)
        self.estado.reload(timeout=30)
        self.generacion = int(self.estado.generation)
        restaurar(self.estado.download_as_bytes(if_generation_match=self.generacion, timeout=120), carpeta)

    def asegurar_bloqueo(self):
        # Nunca guardar tras perder la propiedad del bloqueo compartido.
        if self.lock_generacion is None:
            raise RuntimeError('Bloqueo durable no adquirido')
        live = self.bucket.blob(self.objeto + ".lock")
        live.reload(timeout=15)
        if int(live.generation) != int(self.lock_generacion):
            raise RuntimeError('Se perdió el bloqueo durable')

    def guardar(self, carpeta):
        self.asegurar_bloqueo()
        self.estado = self.bucket.blob(self.objeto)
        self.estado.upload_from_string(empaquetar(Path(carpeta).resolve()), content_type='application/gzip',
                                      if_generation_match=self.generacion, timeout=120)
        self.generacion = int(self.estado.generation)

    def __exit__(self, *args):
        if self.lock_generacion is not None:
            self.bucket.blob(self.objeto + ".lock").delete(if_generation_match=self.lock_generacion, timeout=30)
