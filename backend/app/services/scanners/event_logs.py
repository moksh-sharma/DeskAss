"""Event Viewer scanner: Application / System / Security errors over last 7 days."""
from __future__ import annotations

from app.services.scanners.base import IS_WINDOWS, as_list, ps_json, safe_scan


def _events(log_name: str, levels: str, max_events: int = 60, days: int = 7) -> list[dict]:
    rows = as_list(ps_json(
        f"$start=(Get-Date).AddDays(-{days});"
        f"Get-WinEvent -FilterHashtable @{{LogName='{log_name}'; Level={levels}; StartTime=$start}} "
        f"-MaxEvents {max_events} -ErrorAction SilentlyContinue | "
        "Select-Object Id,LevelDisplayName,ProviderName,"
        "@{N='TimeCreated';E={$_.TimeCreated.ToString('yyyy-MM-ddTHH:mm:ss')}},"
        "@{N='Message';E={($_.Message -split \"`n\")[0]}} | ConvertTo-Json -Compress",
        timeout=30.0,
    ))
    return [{
        "event_id": r.get("Id"),
        "level": r.get("LevelDisplayName"),
        "source": r.get("ProviderName"),
        "timestamp": r.get("TimeCreated"),
        "description": (r.get("Message") or "")[:300],
    } for r in rows]


@safe_scan("event_logs")
def scan() -> dict:
    if not IS_WINDOWS:
        return {"available": False, "note": "Event logs require Windows."}
    # Level 1=Critical, 2=Error, 3=Warning.
    application = _events("Application", "1,2,3")
    system = _events("System", "1,2,3")
    security = _events("Security", "1,2")  # login/auth failures

    def count(rows, level):
        return sum(1 for r in rows if (r.get("level") or "").lower() == level)

    all_rows = application + system
    return {
        "available": True,
        "application": application,
        "system": system,
        "security": security[:30],
        "summary": {
            "critical": count(all_rows, "critical"),
            "errors": count(all_rows, "error"),
            "warnings": count(all_rows, "warning"),
            "security_failures": len(security),
        },
    }
