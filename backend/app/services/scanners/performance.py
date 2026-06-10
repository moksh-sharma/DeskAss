"""Performance scanner: CPU/memory/disk sampling and network throughput."""
from __future__ import annotations

import time

import psutil

from app.services.scanners.base import bytes_to_mb, safe_scan


def _cpu_perf() -> dict:
    samples = [psutil.cpu_percent(interval=0.2) for _ in range(5)]
    return {
        "current_pct": round(samples[-1], 1),
        "average_pct": round(sum(samples) / len(samples), 1),
        "peak_pct": round(max(samples), 1),
        "samples": [round(s, 1) for s in samples],
    }


def _memory_perf() -> dict:
    vm = psutil.virtual_memory()
    swap = psutil.swap_memory()
    return {
        "current_pct": vm.percent,
        "used_gb": round(vm.used / (1024 ** 3), 1),
        "available_gb": round(vm.available / (1024 ** 3), 1),
        "swap_used_pct": swap.percent,
    }


def _disk_perf() -> dict:
    try:
        a = psutil.disk_io_counters()
        time.sleep(0.5)
        b = psutil.disk_io_counters()
    except Exception:
        return {"available": False}
    if not a or not b:
        return {"available": False}
    factor = 2  # 0.5s window -> per second
    return {
        "available": True,
        "read_mb_s": bytes_to_mb((b.read_bytes - a.read_bytes) * factor, 2),
        "write_mb_s": bytes_to_mb((b.write_bytes - a.write_bytes) * factor, 2),
        "read_count": b.read_count,
        "write_count": b.write_count,
    }


def _network_perf() -> dict:
    try:
        a = psutil.net_io_counters()
        time.sleep(0.5)
        b = psutil.net_io_counters()
    except Exception:
        return {"available": False}
    factor = 2
    return {
        "available": True,
        "upload_mb_s": bytes_to_mb((b.bytes_sent - a.bytes_sent) * factor, 3),
        "download_mb_s": bytes_to_mb((b.bytes_recv - a.bytes_recv) * factor, 3),
        "packets_sent": b.packets_sent,
        "packets_recv": b.packets_recv,
        "errors_in": b.errin,
        "errors_out": b.errout,
        "drops_in": b.dropin,
        "drops_out": b.dropout,
    }


@safe_scan("performance")
def scan() -> dict:
    return {
        "cpu": _cpu_perf(),
        "memory": _memory_perf(),
        "disk": _disk_perf(),
        "network": _network_perf(),
    }
