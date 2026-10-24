"""Muestreo portable del proceso Python y sus descendientes, sin tocar resultados."""
import csv
import json
import logging
import math
import os
from pathlib import Path
import platform
import sys
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from uuid import uuid4

import psutil

log = logging.getLogger('metro.resources')
MIB = 1024 ** 2
SAMPLE_COLUMNS = (
    'timestamp_utc', 'elapsed_seconds', 'cpu_seconds', 'cpu_percent_one_core',
    'tree_rss_bytes', 'python_rss_bytes', 'children_rss_bytes', 'live_processes',
    'cgroup_memory_bytes',
)
SUMMARY_COLUMNS = (
    'measurement_id', 'run_id', 'status', 'started_at_utc', 'finished_at_utc',
    'duration_seconds', 'duration_minutes', 'cpu_seconds', 'cpu_average_percent_one_core',
    'cpu_peak_percent_one_core', 'peak_tree_rss_bytes', 'peak_tree_rss_mib',
    'peak_python_rss_mib', 'peak_children_rss_mib', 'max_live_processes',
    'observed_processes', 'samples', 'interval_seconds', 'platform', 'python_version',
    'resumed', 'headed', 'concurrency', 'delay_seconds', 'max_pages', 'max_details',
    'cgroup_cpu_seconds', 'cgroup_peak_memory_bytes', 'measurement_quality',
    'warnings', 'samples_csv',
)


def utc_now():
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def csv_lock(path):
    """Serializa la cabecera y el append entre scrapers con distintas bases."""
    with open(str(path) + '.lock', 'a+b') as handle:
        handle.seek(0, os.SEEK_END)
        if not handle.tell():
            handle.write(b'0')
            handle.flush()
        deadline = time.monotonic() + 5
        while True:
            try:
                handle.seek(0)
                if os.name == 'nt':
                    import msvcrt
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise TimeoutError('No se pudo bloquear el CSV de recursos')
                time.sleep(0.05)
        try:
            yield
        finally:
            if os.name == 'nt':
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def append_summary(path, row):
    with csv_lock(path):
        with path.open('a+', newline='', encoding='utf-8') as handle:
            handle.seek(0)
            header = next(csv.reader(handle), None)
            if header is not None and header != list(SUMMARY_COLUMNS):
                raise ValueError('La cabecera del CSV de recursos no corresponde a esta versión')
            handle.seek(0, os.SEEK_END)
            writer = csv.DictWriter(handle, fieldnames=SUMMARY_COLUMNS)
            if header is None:
                writer.writeheader()
            writer.writerow(row)


class ResourceMonitor:
    def __init__(self, output_dir, interval=0.2):
        if not math.isfinite(interval) or not 0.05 <= interval <= 60:
            raise ValueError('Intervalo de recursos entre 0.05 y 60 segundos')
        self.output_dir = Path(output_dir).resolve()
        self.interval = interval
        self.measurement_id = uuid4().hex
        self.root = psutil.Process(os.getpid())
        self._processes = {}
        self._cpu_last = {}
        self._observed = set()
        self._warnings = set()
        self._stop = threading.Event()
        self._thread = None
        self._file = None
        self._writer = None
        self._cpu_seconds = 0.0
        self._cpu_reads = 0
        self._memory_reads = 0
        self._peak_cpu_percent = 0.0
        self._peak_rss = self._peak_python = self._peak_children = 0
        self._max_processes = self._samples = 0
        self._previous_elapsed = self._previous_cpu = 0.0
        self._cgroup_peak = None
        self.cgroup_path = Path('/sys/fs/cgroup') if sys.platform.startswith('linux') else None
        self._cgroup_cpu_start = None

    def _warning(self, error):
        # Sólo tipos/mensajes del monitor: no lee argumentos, cookies ni entorno de hijos.
        self._warnings.add(str(error))

    def _cgroup(self):
        memory = cpu = None
        if self.cgroup_path is not None:
            try:
                memory = int((self.cgroup_path/'memory.current').read_text().strip())
                self._cgroup_peak = max(self._cgroup_peak or 0, memory)
            except (OSError, ValueError):
                pass  # cgroup v2 opcional; psutil sigue funcionando en v1/Windows.
            try:
                stats = dict(line.split() for line in (self.cgroup_path/'cpu.stat').read_text().splitlines())
                cpu = int(stats['usage_usec']) / 1_000_000
            except (OSError, ValueError, KeyError):
                pass
        return memory, cpu

    def start(self):
        self.started_at = utc_now()
        self._started = time.perf_counter()
        _, self._cgroup_cpu_start = self._cgroup()
        self.samples_path = self.output_dir / (
            'samples-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') +
            '-' + self.measurement_id[:8] + '.csv')
        try:
            self.output_dir.mkdir(parents=True, exist_ok=True)
            self._file = self.samples_path.open('w', newline='', encoding='utf-8')
            self._writer = csv.DictWriter(self._file, fieldnames=SAMPLE_COLUMNS)
            self._writer.writeheader()
        except OSError as exc:
            self._warning(f'CSV de muestras: {exc}')
        self._sample(baseline=True)
        self._thread = threading.Thread(target=self._loop, name='metro-resource-monitor', daemon=True)
        self._thread.start()
        return self

    def _loop(self):
        while not self._stop.wait(self.interval):
            self._sample()

    def _sample(self, baseline=False):
        try:
            candidates = [self.root]
            try:
                candidates.extend(self.root.children(recursive=True))
            except psutil.AccessDenied:
                self._warning('Acceso denegado al descubrir descendientes: medición parcial')
            for process in candidates:
                try:
                    key = (process.pid, process.create_time())
                    self._processes[key] = process
                    self._observed.add(key)
                except psutil.NoSuchProcess:
                    pass
            rss = python_rss = children_rss = live = 0
            for key, process in list(self._processes.items()):
                try:
                    if not process.is_running():
                        del self._processes[key]
                        continue
                    with process.oneshot():
                        cpu = process.cpu_times()
                        memory = process.memory_info().rss
                    total_cpu = cpu.user + cpu.system
                    # Los procesos existentes al inicio descuentan su uso previo.
                    previous = self._cpu_last.get(key, total_cpu if baseline else 0.0)
                    self._cpu_seconds += max(0, total_cpu - previous)
                    self._cpu_last[key] = total_cpu
                    self._cpu_reads += 1
                    self._memory_reads += 1
                    live += 1
                    rss += memory
                    if process.pid == self.root.pid:
                        python_rss += memory
                    else:
                        children_rss += memory
                except psutil.NoSuchProcess:
                    del self._processes[key]
                except psutil.AccessDenied:
                    self._warning('Acceso denegado a CPU/RAM de un proceso: medición parcial')
            elapsed = time.perf_counter() - self._started
            delta = elapsed - self._previous_elapsed
            cpu_percent = (100 * (self._cpu_seconds - self._previous_cpu) / delta
                           if delta > 0 and not baseline else 0.0)
            self._previous_elapsed, self._previous_cpu = elapsed, self._cpu_seconds
            self._peak_cpu_percent = max(self._peak_cpu_percent, cpu_percent)
            self._peak_rss = max(self._peak_rss, rss)
            self._peak_python = max(self._peak_python, python_rss)
            self._peak_children = max(self._peak_children, children_rss)
            self._max_processes = max(self._max_processes, live)
            self._samples += 1
            cgroup_memory, _ = self._cgroup()
            if self._writer:
                try:
                    self._writer.writerow(dict(zip(SAMPLE_COLUMNS, (
                        utc_now(), round(elapsed, 6), round(self._cpu_seconds, 6), round(cpu_percent, 3),
                        rss, python_rss, children_rss, live, cgroup_memory))))
                    self._file.flush()
                except (OSError, ValueError) as exc:
                    self._warning(f'CSV de muestras: {exc}')
                    self._writer = None
        except Exception as exc:
            self._warning(f'Muestreo {type(exc).__name__}: {exc}')

    def finish(self, *, run_id=None, status='unknown', config=None):
        self._stop.set()
        if self._thread:
            self._thread.join()
        self._sample()
        duration = time.perf_counter() - self._started
        finished_at = utc_now()
        _, cgroup_cpu = self._cgroup()
        if self._file:
            self._file.close()
        config = config or {}
        cpu = self._cpu_seconds if self._cpu_reads else None
        row = dict(zip(SUMMARY_COLUMNS, (
            self.measurement_id, run_id, status, self.started_at, finished_at,
            round(duration, 6), round(duration/60, 6), round(cpu, 6) if cpu is not None else None,
            round(cpu/duration*100, 3) if cpu is not None and duration else None,
            round(self._peak_cpu_percent, 3) if cpu is not None else None,
            self._peak_rss if self._memory_reads else None,
            round(self._peak_rss/MIB, 3) if self._memory_reads else None,
            round(self._peak_python/MIB, 3) if self._memory_reads else None,
            round(self._peak_children/MIB, 3) if self._memory_reads else None,
            self._max_processes, len(self._observed), self._samples, self.interval,
            platform.system(), platform.python_version(), bool(config.get('resume')),
            config.get('headed'), config.get('concurrency'), config.get('delay'),
            config.get('max_pages'), config.get('max_details'),
            round(max(0, cgroup_cpu-self._cgroup_cpu_start), 6)
            if cgroup_cpu is not None and self._cgroup_cpu_start is not None else None,
            self._cgroup_peak, 'partial' if self._warnings else 'sampled',
            json.dumps(sorted(self._warnings), ensure_ascii=False), str(self.samples_path),
        )))
        self.summary_path = self.output_dir/'resource_usage.csv'
        try:
            append_summary(self.summary_path, row)
        except (OSError, ValueError, TimeoutError) as exc:
            self._warning(f'CSV de resumen: {exc}')
            row['measurement_quality'] = 'partial'
            row['warnings'] = json.dumps(sorted(self._warnings), ensure_ascii=False)
        if self._warnings:
            log.warning('Incidentes del monitor de recursos: %s', row['warnings'])
        return row


def print_summary(row, summary_path):
    def fmt(value):
        return f'{value:.2f}' if value is not None else 'no disponible'
    print('\nResumen de recursos de la ejecución:')
    print(f"  Duración: {row['duration_seconds']:.2f} segundos ({row['duration_minutes']:.2f} minutos)")
    print(f"  CPU consumida (árbol): {fmt(row['cpu_seconds'])} s; media {fmt(row['cpu_average_percent_one_core'])}% de un núcleo; pico {fmt(row['cpu_peak_percent_one_core'])}%")
    print(f"  RAM máxima observada Python + navegador: {fmt(row['peak_tree_rss_mib'])} MiB")
    print(f"  Procesos simultáneos: {row['max_live_processes']}; muestras: {row['samples']}")
    print(f'  CSV comparativo: {summary_path}')
    print(f"  CSV de muestras: {row['samples_csv']}", flush=True)
