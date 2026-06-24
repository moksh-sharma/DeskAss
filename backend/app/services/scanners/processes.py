"""Process intelligence scanner: full process table, parent/child relationships,
top consumers, and suspicious-process flags."""
from __future__ import annotations

import time
from datetime import datetime, timezone

import psutil

from app.services.scanners.base import safe_scan

# Processes commonly abused by malware when running from unusual paths.
_SUSPICIOUS_NAMES = {"powershell.exe", "cmd.exe", "wscript.exe", "cscript.exe", "mshta.exe", "rundll32.exe"}
_TRUSTED_DIRS = ("c:\\windows", "c:\\program files", "c:\\program files (x86)")

# Cap the full process table so the report payload stays reasonable.
_MAX_PROCESSES = 400


def _collect() -> list[dict]:
    procs: list[dict] = []
    ncpu = psutil.cpu_count(logical=True) or 1
    # Prime cpu_percent.
    for p in psutil.process_iter():
        try:
            p.cpu_percent(None)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    time.sleep(0.4)
    for p in psutil.process_iter(["pid", "ppid", "name", "username", "create_time", "exe", "num_threads"]):
        try:
            cpu = p.cpu_percent(None) / ncpu
            mem = p.memory_info().rss
            info = p.info
            # Per-process disk I/O is best-effort (needs permission on Windows).
            disk_mb = None
            try:
                io = p.io_counters()
                disk_mb = round((io.read_bytes + io.write_bytes) / (1024 ** 2), 1)
            except (psutil.AccessDenied, NotImplementedError, AttributeError, OSError):
                pass
            procs.append({
                "pid": info.get("pid"),
                "ppid": info.get("ppid"),
                "name": info.get("name"),
                "username": info.get("username"),
                "cpu_pct": round(cpu, 1),
                "memory_mb": round(mem / (1024 ** 2), 1),
                "threads": info.get("num_threads"),
                "disk_io_mb": disk_mb,
                "exe": info.get("exe"),
                "start_time": (
                    datetime.fromtimestamp(info["create_time"], tz=timezone.utc).isoformat()
                    if info.get("create_time") else None
                ),
            })
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return procs


def _suspicious(procs: list[dict]) -> list[dict]:
    flagged = []
    for p in procs:
        name = (p.get("name") or "").lower()
        exe = (p.get("exe") or "").lower()
        if name in _SUSPICIOUS_NAMES and exe and not any(exe.startswith(d) for d in _TRUSTED_DIRS):
            flagged.append({**p, "reason": "System tool running from a non-standard location"})
        elif p.get("cpu_pct", 0) >= 85:
            flagged.append({**p, "reason": "Sustained very high CPU usage"})
    return flagged


def _child_count(procs: list[dict]) -> dict[int, int]:
    counts: dict[int, int] = {}
    for p in procs:
        ppid = p.get("ppid")
        if ppid is not None:
            counts[ppid] = counts.get(ppid, 0) + 1
    return counts


@safe_scan("processes")
def scan() -> dict:
    procs = _collect()
    children = _child_count(procs)
    for p in procs:
        p["child_count"] = children.get(p.get("pid"), 0)

    by_cpu = sorted(procs, key=lambda p: p.get("cpu_pct", 0), reverse=True)[:20]
    by_mem = sorted(procs, key=lambda p: p.get("memory_mb", 0), reverse=True)[:20]

    # Full table (trimmed fields), capped and sorted by memory so the heaviest
    # processes are always present even if truncated.
    full = sorted(procs, key=lambda p: p.get("memory_mb", 0), reverse=True)[:_MAX_PROCESSES]
    all_processes = [
        {
            "pid": p.get("pid"), "ppid": p.get("ppid"), "name": p.get("name"),
            "cpu_pct": p.get("cpu_pct"), "memory_mb": p.get("memory_mb"),
            "threads": p.get("threads"), "child_count": p.get("child_count"),
            "start_time": p.get("start_time"), "username": p.get("username"),
        }
        for p in full
    ]

    return {
        "total_processes": len(procs),
        "returned_count": len(all_processes),
        "top_cpu": by_cpu,
        "top_memory": by_mem,
        "all_processes": all_processes,
        "suspicious": _suspicious(procs),
        "high_resource_count": sum(1 for p in procs if p.get("cpu_pct", 0) >= 50 or p.get("memory_mb", 0) >= 1500),
    }
