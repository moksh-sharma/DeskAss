"""Crash-analysis scanner: app crashes/hangs, BSODs and minidump files."""
from __future__ import annotations

import os

from app.services.scanners.base import IS_WINDOWS, as_list, ps_json, safe_scan


def _app_crashes() -> list[dict]:
    rows = as_list(ps_json(
        "$start=(Get-Date).AddDays(-7);"
        "Get-WinEvent -FilterHashtable @{LogName='Application'; Id=1000,1002; StartTime=$start} "
        "-MaxEvents 40 -ErrorAction SilentlyContinue | Select-Object Id,"
        "@{N='TimeCreated';E={$_.TimeCreated.ToString('yyyy-MM-ddTHH:mm:ss')}},"
        "@{N='Message';E={($_.Message -split \"`n\")[0]}} | ConvertTo-Json -Compress",
        timeout=25.0,
    ))
    out = []
    for r in rows:
        out.append({
            "type": "Hang" if r.get("Id") == 1002 else "Crash",
            "timestamp": r.get("TimeCreated"),
            "description": (r.get("Message") or "")[:240],
        })
    return out


def _bsod_events() -> list[dict]:
    rows = as_list(ps_json(
        "$start=(Get-Date).AddDays(-30);"
        "Get-WinEvent -FilterHashtable @{LogName='System'; Id=41,1001,6008; StartTime=$start} "
        "-MaxEvents 20 -ErrorAction SilentlyContinue | Select-Object Id,ProviderName,"
        "@{N='TimeCreated';E={$_.TimeCreated.ToString('yyyy-MM-ddTHH:mm:ss')}},"
        "@{N='Message';E={($_.Message -split \"`n\")[0]}} | ConvertTo-Json -Compress",
        timeout=25.0,
    ))
    label = {41: "Unexpected shutdown (kernel power)", 1001: "Bugcheck (BSOD)", 6008: "Unexpected shutdown"}
    return [{
        "event_id": r.get("Id"),
        "type": label.get(r.get("Id"), "Shutdown event"),
        "timestamp": r.get("TimeCreated"),
        "description": (r.get("Message") or "")[:240],
    } for r in rows]


def _minidumps() -> list[dict]:
    path = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "Minidump")
    dumps = []
    try:
        if os.path.isdir(path):
            import datetime
            for entry in sorted(os.scandir(path), key=lambda e: e.stat().st_mtime, reverse=True)[:15]:
                if entry.name.lower().endswith(".dmp"):
                    stat = entry.stat()
                    dumps.append({
                        "file": entry.name,
                        "size_kb": round(stat.st_size / 1024, 1),
                        "created": datetime.datetime.utcfromtimestamp(stat.st_mtime).isoformat(),
                    })
    except Exception:
        pass
    return dumps


@safe_scan("crash_analysis")
def scan() -> dict:
    if not IS_WINDOWS:
        return {"available": False, "note": "Crash analysis requires Windows."}
    crashes = _app_crashes()
    bsods = _bsod_events()
    dumps = _minidumps()
    return {
        "available": True,
        "application_crashes": crashes,
        "bsod_events": bsods,
        "minidumps": dumps,
        "summary": {
            "crash_count": sum(1 for c in crashes if c["type"] == "Crash"),
            "hang_count": sum(1 for c in crashes if c["type"] == "Hang"),
            "bsod_count": len(bsods),
            "minidump_count": len(dumps),
        },
    }
