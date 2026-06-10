"""Operating-system scanner: Windows info, updates, environment."""
from __future__ import annotations

import getpass
import os
import platform
import time
from datetime import datetime, timezone

import psutil

from app.services.scanners.base import as_list, cim_one, ps_json, safe_scan


def _windows_info() -> dict:
    os_ci = cim_one("Win32_OperatingSystem",
                    "Caption,Version,BuildNumber,OSArchitecture,InstallDate,LastBootUpTime") or {}
    boot_ts = psutil.boot_time()
    uptime_secs = max(0, time.time() - boot_ts)
    return {
        "edition": os_ci.get("Caption") or platform.system(),
        "version": os_ci.get("Version") or platform.version(),
        "build_number": os_ci.get("BuildNumber") or platform.release(),
        "architecture": os_ci.get("OSArchitecture") or platform.machine(),
        "install_date": _cim_date(os_ci.get("InstallDate")),
        "last_boot_time": datetime.fromtimestamp(boot_ts, tz=timezone.utc).isoformat(),
        "uptime_hours": round(uptime_secs / 3600, 1),
        "uptime_readable": _fmt_uptime(uptime_secs),
    }


def _fmt_uptime(secs: float) -> str:
    days = int(secs // 86400)
    hours = int((secs % 86400) // 3600)
    mins = int((secs % 3600) // 60)
    parts = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    parts.append(f"{mins}m")
    return " ".join(parts)


def _cim_date(value) -> str | None:
    if not value:
        return None
    s = str(value)
    if "Date(" in s:
        try:
            ms = int(s.split("Date(")[1].split(")")[0].split("+")[0].split("-")[0])
            return datetime.utcfromtimestamp(ms / 1000).strftime("%Y-%m-%d")
        except Exception:
            return s
    if len(s) >= 8 and s[:8].isdigit():
        return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
    return s


def _updates() -> dict:
    hotfixes = as_list(ps_json(
        "Get-HotFix -ErrorAction SilentlyContinue | "
        "Sort-Object InstalledOn -Descending | Select-Object -First 25 "
        "HotFixID,Description,@{N='InstalledOn';E={$_.InstalledOn.ToString('yyyy-MM-dd')}} | "
        "ConvertTo-Json -Compress",
        timeout=25.0,
    ))
    installed = [{
        "id": h.get("HotFixID"),
        "description": h.get("Description"),
        "installed_on": h.get("InstalledOn"),
    } for h in hotfixes]

    # Pending updates via the Windows Update COM API (best-effort). This can be
    # slow or hang on managed machines, so keep a short timeout and degrade to
    # null rather than stalling the whole scan.
    pending = ps_json(
        "$ErrorActionPreference='SilentlyContinue';"
        "try{$s=New-Object -ComObject Microsoft.Update.Session;"
        "$r=$s.CreateUpdateSearcher().Search('IsInstalled=0 and IsHidden=0');"
        "@{count=$r.Updates.Count} | ConvertTo-Json -Compress}catch{'{\"count\":null}'}",
        timeout=12.0,
    )
    pending_count = (pending or {}).get("count") if isinstance(pending, dict) else None
    return {
        "installed_count": len(installed),
        "recent_installed": installed,
        "pending_count": pending_count,
        "last_installed_on": installed[0]["installed_on"] if installed else None,
    }


def _environment() -> dict:
    tz = None
    try:
        tz = time.tzname[0]
    except Exception:
        pass
    domain = os.environ.get("USERDOMAIN")
    try:
        user = getpass.getuser()
    except Exception:
        user = os.environ.get("USERNAME", "unknown")
    return {
        "computer_name": platform.node() or os.environ.get("COMPUTERNAME"),
        "logged_in_user": user,
        "domain": domain,
        "is_domain_joined": bool(domain) and domain != platform.node(),
        "time_zone": tz,
        "python_platform": platform.platform(),
    }


@safe_scan("operating_system")
def scan() -> dict:
    return {
        "windows": _windows_info(),
        "updates": _updates(),
        "environment": _environment(),
    }
