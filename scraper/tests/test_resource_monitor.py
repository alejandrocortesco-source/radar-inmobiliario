import asyncio
import csv
from contextlib import nullcontext
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock

import psutil
import pytest

from metro.resource_monitor import ResourceMonitor, SUMMARY_COLUMNS
from metro.scraper import Config, Scraper


class Process:
    def __init__(self, pid, born, cpu, rss):
        self.pid, self.born, self.cpu, self.rss = pid, born, cpu, rss
        self.alive = True
        self.descendants = []

    def create_time(self): return self.born
    def children(self, recursive=False):
        assert recursive
        return self.descendants
    def is_running(self): return self.alive
    def oneshot(self): return nullcontext()
    def cpu_times(self): return SimpleNamespace(user=self.cpu, system=0.0)
    def memory_info(self): return SimpleNamespace(rss=self.rss)


def read_csv(path):
    with Path(path).open(newline='', encoding='utf-8') as handle:
        return list(csv.DictReader(handle))


def test_tree_cpu_dead_children_pid_reuse_and_peak(monkeypatch, tmp_path):
    root = Process(1, 1, 100, 20_000)
    monkeypatch.setattr('metro.resource_monitor.psutil.Process', lambda pid: root)
    monitor = ResourceMonitor(tmp_path, interval=60)
    monitor.cgroup_path = None
    monitor.start()
    try:
        node = Process(2, 2, 1, 30_000)
        browser = Process(3, 3, 0.5, 40_000)
        renderer = Process(4, 4, 0.25, 50_000)
        root.cpu = 100.2
        root.descendants = [node, browser, renderer]
        monitor._sample()
        # El navegador desaparece: su CPU acumulada no se descuenta del total.
        browser.alive = renderer.alive = False
        root.descendants = []
        node.cpu = 1.1  # Sigue siendo rastreado aunque deje de ser descendiente.
        monitor._sample()
        node.alive = False
        replacement = Process(2, 99, 0.9, 10_000)
        root.descendants = [replacement]
        monitor._sample()
    finally:
        row = monitor.finish(run_id=7, status='completed')
    assert row['cpu_seconds'] == pytest.approx(2.95)
    assert row['peak_tree_rss_bytes'] == 140_000
    assert row['max_live_processes'] == 4
    assert row['observed_processes'] == 5
    assert row['duration_seconds'] > 0
    assert row['duration_minutes'] == pytest.approx(row['duration_seconds']/60, abs=1e-6)
    assert row['cgroup_cpu_seconds'] is None
    assert read_csv(monitor.summary_path)[0]['run_id'] == '7'


def test_real_child_cpu_and_memory(tmp_path):
    monitor = ResourceMonitor(tmp_path, interval=0.05).start()
    child = None
    try:
        child = subprocess.Popen([sys.executable, '-c',
            'import time; data=bytearray(16*1024*1024); end=time.perf_counter()+0.6\n'
            'while time.perf_counter()<end: sum(range(10000))\n'
            'time.sleep(0.3)'])
        assert child.wait(timeout=15) == 0
    finally:
        if child is not None and child.poll() is None:
            child.kill()
            child.wait()
        row = monitor.finish(status='completed')
    assert row['cpu_seconds'] > 0.05
    assert row['peak_children_rss_mib'] > 10
    assert row['max_live_processes'] >= 2
    assert row['samples'] >= 3
    samples = read_csv(row['samples_csv'])
    assert len(samples) == row['samples']
    assert max(int(r['tree_rss_bytes']) for r in samples) == row['peak_tree_rss_bytes']


def test_cgroup_v2_optional_counters(tmp_path):
    cgroup = tmp_path/'cgroup'
    cgroup.mkdir()
    (cgroup/'memory.current').write_text('1234')
    (cgroup/'cpu.stat').write_text('usage_usec 1000000\nuser_usec 500000\nsystem_usec 500000\n')
    monitor = ResourceMonitor(tmp_path/'metrics', interval=60)
    monitor.cgroup_path = cgroup
    monitor.start()
    (cgroup/'memory.current').write_text('4096')
    (cgroup/'cpu.stat').write_text('usage_usec 2500000\n')
    row = monitor.finish(status='completed')
    assert row['cgroup_cpu_seconds'] == 1.5
    assert row['cgroup_peak_memory_bytes'] == 4096


def test_csv_appends_runs_with_single_header(tmp_path):
    for run in (1, 2):
        monitor = ResourceMonitor(tmp_path, interval=60).start()
        monitor.finish(run_id=run, status='incomplete')
    rows = read_csv(tmp_path/'resource_usage.csv')
    assert [r['run_id'] for r in rows] == ['1', '2']
    assert len({r['measurement_id'] for r in rows}) == 2
    assert len(list(tmp_path.glob('samples-*.csv'))) == 2
    assert tuple(rows[0]) == SUMMARY_COLUMNS


def test_process_access_denied_reports_partial(monkeypatch, tmp_path):
    root = Process(1, 1, 0, 0)
    def denied(): raise psutil.AccessDenied(1)
    root.memory_info = denied
    monkeypatch.setattr('metro.resource_monitor.psutil.Process', lambda pid: root)
    monitor = ResourceMonitor(tmp_path, interval=60).start()
    row = monitor.finish()
    assert row['measurement_quality'] == 'partial'
    assert row['peak_tree_rss_bytes'] is None
    assert row['cpu_seconds'] is None


def test_wrapper_preserves_result_and_handles_interruption(tmp_path, capsys):
    scraper = Scraper(Config(db=str(tmp_path/'results.sqlite')))
    expected = {'status':'completed', 'unique':3}
    scraper._run = AsyncMock(return_value=expected)
    assert asyncio.run(scraper.run()) is expected
    assert 'Resumen de recursos' in capsys.readouterr().out
    scraper._run = AsyncMock(side_effect=asyncio.CancelledError())
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(scraper.run())
    assert [r['status'] for r in read_csv(tmp_path/'metrics/resource_usage.csv')] == ['completed','interrupted']


def test_csv_error_does_not_change_scraping_result(monkeypatch, tmp_path):
    def denied(*args): raise PermissionError('CSV no disponible')
    monkeypatch.setattr('metro.resource_monitor.append_summary', denied)
    scraper = Scraper(Config(db=str(tmp_path/'results.sqlite')))
    expected = {'status':'incomplete'}
    scraper._run = AsyncMock(return_value=expected)
    assert asyncio.run(scraper.run()) is expected
    assert scraper.resource_usage['measurement_quality'] == 'partial'


def test_unexpected_failure_still_writes_resource_summary(tmp_path):
    scraper = Scraper(Config(db=str(tmp_path/'results.sqlite')))
    scraper._run = AsyncMock(side_effect=RuntimeError('fallo controlado'))
    with pytest.raises(RuntimeError, match='fallo controlado'):
        asyncio.run(scraper.run())
    assert read_csv(tmp_path/'metrics/resource_usage.csv')[0]['status'] == 'failed'


@pytest.mark.parametrize('interval', [0, -1, 61, float('nan'), float('inf')])
def test_invalid_intervals(interval, tmp_path):
    with pytest.raises(ValueError): ResourceMonitor(tmp_path, interval=interval)
    with pytest.raises(ValueError): Config(resource_interval=interval).validate()
