"""Startup-programs scanner: Run keys, Startup folder, scheduled tasks, impact."""
from __future__ import annotations

from app.services.scanners.base import as_list, ps_json, safe_scan

# Heuristic: these vendors/apps are known heavy startup items.
_HIGH_IMPACT_HINTS = (
    "teams", "onedrive", "dropbox", "slack", "steam", "epic", "adobe", "creative cloud",
    "discord", "spotify", "skype", "zoom", "docker", "java", "icloud", "razer", "nvidia",
)


def _startup_items() -> list[dict]:
    rows = as_list(ps_json(
        "Get-CimInstance Win32_StartupCommand -ErrorAction SilentlyContinue | "
        "Select-Object Name,Command,Location,User | ConvertTo-Json -Compress",
        timeout=20.0,
    ))
    items = []
    for r in rows:
        name = (r.get("Name") or "").strip()
        cmd = (r.get("Command") or "").lower()
        impact = "High" if any(h in (name.lower() + cmd) for h in _HIGH_IMPACT_HINTS) else "Low"
        items.append({
            "name": name or r.get("Command"),
            "command": r.get("Command"),
            "location": r.get("Location"),
            "user": r.get("User"),
            "impact": impact,
        })
    return items


def _scheduled_tasks() -> dict:
    """Enabled scheduled tasks, highlighting logon/boot triggered ones (they
    behave like startup programs and are a common persistence mechanism)."""
    data = ps_json(
        "$t = Get-ScheduledTask -ErrorAction SilentlyContinue | "
        "Where-Object { $_.State.ToString() -ne 'Disabled' }; "
        "$lb = @($t | Where-Object { ($_.Triggers | ForEach-Object { $_.CimClass.CimClassName }) "
        "-match 'LogonTrigger|BootTrigger' }); "
        "[PSCustomObject]@{ total = @($t).Count; "
        "logon_boot = @($lb | Select-Object -First 50 | ForEach-Object { "
        "[PSCustomObject]@{ name=$_.TaskName; path=$_.TaskPath; state=$_.State.ToString(); "
        "author=$_.Author } }) } | ConvertTo-Json -Compress -Depth 4",
        timeout=35.0,
    )
    if not isinstance(data, dict):
        return {"available": False}
    tasks = as_list(data.get("logon_boot"))
    # Tasks outside the Microsoft tree deserve attention in an audit.
    non_ms = [t for t in tasks if not (t.get("path") or "").startswith("\\Microsoft\\")]
    return {
        "available": True,
        "enabled_total": data.get("total"),
        "logon_boot_tasks": tasks,
        "logon_boot_count": len(tasks),
        "third_party_logon_tasks": non_ms,
    }


@safe_scan("startup_programs")
def scan() -> dict:
    items = _startup_items()
    high = [i for i in items if i["impact"] == "High"]
    return {
        "total_count": len(items),
        "programs": items,
        "high_impact": high,
        "high_impact_count": len(high),
        "scheduled_tasks": _scheduled_tasks(),
    }
