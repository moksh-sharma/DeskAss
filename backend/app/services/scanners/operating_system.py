"""Operating-system scanner: Windows info, updates, activation, reboot state, environment."""
from __future__ import annotations

import getpass
import os
import platform
import time
from datetime import datetime, timezone

import psutil

from app.services.scanners.base import (
    IS_WINDOWS,
    as_list,
    cim,
    cim_one,
    ps_json,
    run_powershell,
    safe_scan,
)


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


def _activation() -> dict:
    """Windows licence/activation state (enterprise compliance signal)."""
    if not IS_WINDOWS:
        return {"available": False}
    rec = cim_one(
        "SoftwareLicensingProduct",
        "Name,LicenseStatus,PartialProductKey,Description",
        where="PartialProductKey IS NOT NULL AND ApplicationID='55c92734-d682-4d71-983e-d6ec3f16059f'",
        timeout=25.0,
    ) or {}
    status_map = {0: "Unlicensed", 1: "Licensed", 2: "Out-of-box grace", 3: "Out-of-tolerance grace",
                  4: "Non-genuine grace", 5: "Notification", 6: "Extended grace"}
    status = status_map.get(rec.get("LicenseStatus"))
    is_kms = "kms" in ((rec.get("Description") or "").lower())
    return {
        "available": bool(rec),
        "status": status,
        "activated": rec.get("LicenseStatus") == 1,
        "channel": "Volume (KMS)" if is_kms else (rec.get("Description") or "").split(",")[0] or None,
        "partial_product_key": rec.get("PartialProductKey"),
    }


def _pending_reboot() -> dict:
    """Detect the standard pending-reboot markers (CBS, Windows Update, file renames)."""
    if not IS_WINDOWS:
        return {"required": None}
    result = ps_json(
        "$cbs = Test-Path 'HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Component Based Servicing\\RebootPending';"
        "$wu = Test-Path 'HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\WindowsUpdate\\Auto Update\\RebootRequired';"
        "$pfro = $null -ne (Get-ItemProperty 'HKLM:\\SYSTEM\\CurrentControlSet\\Control\\Session Manager' "
        "-Name PendingFileRenameOperations -ErrorAction SilentlyContinue);"
        "@{cbs=$cbs; windows_update=$wu; file_renames=$pfro} | ConvertTo-Json -Compress",
        timeout=15.0,
    ) or {}
    flags = {k: bool(v) for k, v in result.items()} if isinstance(result, dict) else {}
    return {
        "required": any(flags.values()) if flags else None,
        "reasons": [k for k, v in flags.items() if v],
    }


def _power_plan() -> dict:
    rows = cim("Win32_PowerPlan", "ElementName,IsActive", namespace="root/cimv2/power", timeout=15.0)
    active = next((r.get("ElementName") for r in rows if r.get("IsActive")), None)
    if not active and IS_WINDOWS:
        # The power namespace is often blocked on managed devices; powercfg always works.
        ok, out = run_powershell("powercfg /getactivescheme", timeout=10.0)
        if ok and "(" in out:
            active = out.split("(")[-1].split(")")[0].strip() or None
    return {
        "active_plan": active,
        "available_plans": [r.get("ElementName") for r in rows if r.get("ElementName")],
    }


def _join_status() -> dict:
    """Domain / Azure AD (Entra ID) join state via dsregcmd - key enterprise signal."""
    if not IS_WINDOWS:
        return {}
    ok, out = run_powershell("dsregcmd /status", timeout=20.0)
    if not ok or not out:
        return {}
    flags = {}
    for line in out.splitlines():
        if ":" not in line:
            continue
        key, _, val = line.partition(":")
        key = key.strip()
        val = val.strip()
        if key in ("AzureAdJoined", "EnterpriseJoined", "DomainJoined", "WorkplaceJoined"):
            flags[key] = val.upper() == "YES"
        elif key in ("DomainName", "TenantName") and val:
            flags[key] = val
    return {
        "azure_ad_joined": flags.get("AzureAdJoined"),
        "domain_joined": flags.get("DomainJoined"),
        "workplace_joined": flags.get("WorkplaceJoined"),
        "domain_name": flags.get("DomainName"),
        "azure_tenant": flags.get("TenantName"),
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
    # Run the independent (PowerShell-heavy) probes in parallel.
    from concurrent.futures import ThreadPoolExecutor

    jobs = {
        "windows": _windows_info,
        "updates": _updates,
        "activation": _activation,
        "pending_reboot": _pending_reboot,
        "power_plan": _power_plan,
        "join_status": _join_status,
        "environment": _environment,
    }
    out: dict = {}
    with ThreadPoolExecutor(max_workers=len(jobs)) as pool:
        futures = {pool.submit(fn): key for key, fn in jobs.items()}
        for fut, key in futures.items():
            try:
                out[key] = fut.result(timeout=45)
            except Exception as exc:  # pragma: no cover
                out[key] = {"error": str(exc)}
    return out
