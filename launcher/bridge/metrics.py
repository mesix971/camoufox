"""
Live per-session CPU/RAM/bandwidth metrics using psutil.

Uses psutil lazily — if it's not installed, the metrics functions return
`None` values rather than crashing. `pip install psutil` is recommended
but we don't force it as a hard dep (the launcher works without it).

Metrics are sampled on-demand (per bridge list-sessions call). They are
NOT persisted — they reflect the moment of the query.
"""

from __future__ import annotations

from typing import Dict, List, Optional

try:
    import psutil  # type: ignore
    _HAS_PSUTIL = True
except ImportError:
    psutil = None  # type: ignore
    _HAS_PSUTIL = False


def has_psutil() -> bool:
    return _HAS_PSUTIL


def process_metrics(pid: int) -> Dict[str, Optional[float]]:
    """Return {cpu_percent, rss_bytes, num_threads, num_children, io_read, io_write}.

    Values are None when psutil is missing or the process is gone.
    """
    if not _HAS_PSUTIL or pid <= 0:
        return {
            "cpu_percent": None,
            "rss_bytes": None,
            "num_threads": None,
            "num_children": None,
            "io_read_bytes": None,
            "io_write_bytes": None,
            "create_time": None,
        }
    try:
        p = psutil.Process(pid)
        # Include children — a Camoufox session tree includes firefox.exe + subprocesses.
        children = p.children(recursive=True)
        all_procs = [p] + children
        cpu = 0.0
        rss = 0
        threads = 0
        io_read = 0
        io_write = 0
        for pr in all_procs:
            try:
                cpu += pr.cpu_percent(interval=None)
                rss += pr.memory_info().rss
                threads += pr.num_threads()
                try:
                    counters = pr.io_counters()
                    io_read += counters.read_bytes
                    io_write += counters.write_bytes
                except (psutil.AccessDenied, AttributeError):
                    pass
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return {
            "cpu_percent": round(cpu, 1),
            "rss_bytes": rss,
            "num_threads": threads,
            "num_children": len(children),
            "io_read_bytes": io_read,
            "io_write_bytes": io_write,
            "create_time": p.create_time(),
        }
    except (psutil.NoSuchProcess, psutil.AccessDenied, OSError):
        return {
            "cpu_percent": None,
            "rss_bytes": None,
            "num_threads": None,
            "num_children": None,
            "io_read_bytes": None,
            "io_write_bytes": None,
            "create_time": None,
        }


def system_metrics() -> Dict[str, Optional[float]]:
    """Host-wide metrics — total CPU %, total RAM used, total RAM available."""
    if not _HAS_PSUTIL:
        return {
            "cpu_percent": None,
            "memory_total_bytes": None,
            "memory_used_bytes": None,
            "memory_available_bytes": None,
            "memory_percent": None,
        }
    try:
        vm = psutil.virtual_memory()
        return {
            "cpu_percent": psutil.cpu_percent(interval=None),
            "memory_total_bytes": vm.total,
            "memory_used_bytes": vm.used,
            "memory_available_bytes": vm.available,
            "memory_percent": vm.percent,
        }
    except OSError:
        return {
            "cpu_percent": None,
            "memory_total_bytes": None,
            "memory_used_bytes": None,
            "memory_available_bytes": None,
            "memory_percent": None,
        }


def metrics_for_sessions(pids: List[int]) -> Dict[int, Dict[str, Optional[float]]]:
    """Batch-compute metrics for a list of pids. Same shape as process_metrics per pid."""
    return {pid: process_metrics(pid) for pid in pids}
