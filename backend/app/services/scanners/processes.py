"""Running-processes scanner: top consumers and suspicious-process flags."""
from __future__ import annotations

from datetime import datetime, timezone

import psutil

from app.services.scanners.base import safe_scan

# Processes commonly abused by malware when running from unusual paths.
_SUSPICIOUS_NAMES = {"powershell.exe", "cmd.exe", "wscript.exe", "cscript.exe", "mshta.exe", "rundll32.exe"}
_TRUSTED_DIRS = ("c:\\windows", "c:\\program files", "c:\\program files (x86)")


def _collect() -> list[dict]:
    procs: list[dict] = []
    ncpu = psutil.cpu_count(logical=True) or 1
    # Prime cpu_percent.
    for p in psutil.process_iter():
        try:
            p.cpu_percent(None)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    import time
    time.sleep(0.4)
    for p in psutil.process_iter(["pid", "name", "username", "create_time", "exe"]):
        try:
            cpu = p.cpu_percent(None) / ncpu
            mem = p.memory_info().rss
            info = p.info
            procs.append({
                "pid": info.get("pid"),
                "name": info.get("name"),
                "username": info.get("username"),
                "cpu_pct": round(cpu, 1),
                "memory_mb": round(mem / (1024 ** 2), 1),
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


@safe_scan("processes")
def scan() -> dict:
    procs = _collect()
    by_cpu = sorted(procs, key=lambda p: p.get("cpu_pct", 0), reverse=True)[:20]
    by_mem = sorted(procs, key=lambda p: p.get("memory_mb", 0), reverse=True)[:20]
    return {
        "total_processes": len(procs),
        "top_cpu": by_cpu,
        "top_memory": by_mem,
        "suspicious": _suspicious(procs),
        "high_resource_count": sum(1 for p in procs if p.get("cpu_pct", 0) >= 50 or p.get("memory_mb", 0) >= 1500),
    }
