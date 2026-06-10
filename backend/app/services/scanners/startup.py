"""Startup-programs scanner: registry Run keys + Startup folder + impact."""
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


@safe_scan("startup_programs")
def scan() -> dict:
    items = _startup_items()
    high = [i for i in items if i["impact"] == "High"]
    return {
        "total_count": len(items),
        "programs": items,
        "high_impact": high,
        "high_impact_count": len(high),
    }
