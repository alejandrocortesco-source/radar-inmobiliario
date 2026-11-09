"""Bloqueo de escritor local. El wrapper durable protege además entre Jobs."""
import os
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def bloqueo(ruta):
    ruta = Path(str(ruta) + '.lock')
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with ruta.open('a+b') as archivo:
        archivo.seek(0)
        archivo.write(b'0')
        archivo.flush()
        archivo.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(archivo.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(archivo.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise ValueError('Ya hay una ejecución usando este almacenamiento') from None
        yield
