"""Driver scanner: installed drivers, problem devices, and Windows Update availability."""
from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from typing import Any

from app.services.scanners.base import IS_WINDOWS, as_list, ps_json, safe_scan

# Problem codes that mean a driver is missing or broken (not "device disconnected").
_PROBLEM_LABELS: dict[int, str] = {
    1: "Not configured correctly",
    10: "Failed to start",
    18: "Reinstall required",
    22: "Disabled",
    28: "Missing driver",
    31: "Failed to load",
    43: "Stopped (error)",
    48: "Blocked by policy",
}

# Skip generic Microsoft inbox drivers when listing "user-visible" hardware drivers.
_SKIP_NAME_RE = re.compile(
    r"^(WAN Miniport|Microsoft|Generic|Standard|USB Root Hub|PCI Express|"
    r"High precision event timer|System timer|Motherboard resources|"
    r"Numeric data processor|Programmable interrupt controller|"
    r"Direct memory access controller|System CMOS|System board|"
    r"Composite Bus Enumerator|UMBus|Remote Desktop|Hyper-V)",
    re.I,
)

_WU_DRIVER_SCRIPT = r"""
$available = @(); $err = $null
try {
  $s = New-Object -ComObject Microsoft.Update.Session
  $sr = $s.CreateUpdateSearcher()
  $r = $sr.Search("IsInstalled=0 and Type='Driver'")
  for ($i = 0; $i -lt $r.Updates.Count; $i++) {
    $u = $r.Updates.Item($i)
    $available += [PSCustomObject]@{
      title = $u.Title
      driver_class = $u.DriverClass
      driver_model = $u.DriverModel
      manufacturer = $u.DriverManufacturer
      description = $u.Description
    }
  }
} catch { $err = $_.Exception.Message }
@{ available = $available; error = $err } | ConvertTo-Json -Depth 5 -Compress
"""


def _parse_driver_date(raw: str | None) -> datetime | None:
    if not raw:
        return None
    for fmt in ("%Y-%m-%d", "%Y%m%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(raw[:10], fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def _installed_drivers() -> list[dict[str, Any]]:
    rows = as_list(ps_json(
        "Get-CimInstance Win32_PnPSignedDriver -ErrorAction SilentlyContinue | "
        "Where-Object { $_.DeviceName } | "
        "Select-Object DeviceName,DeviceClass,DriverVersion,DriverDate,Manufacturer,"
        "DriverProviderName,IsSigned | ConvertTo-Json -Compress",
        timeout=45.0,
    ))
    seen: set[str] = set()
    drivers: list[dict[str, Any]] = []
    for r in rows:
        name = (r.get("DeviceName") or "").strip()
        if not name or _SKIP_NAME_RE.search(name):
            continue
        version = r.get("DriverVersion")
        cls = r.get("DeviceClass") or "Other"
        key = f"{name}|{version}|{cls}"
        if key in seen:
            continue
        seen.add(key)
        date_raw = r.get("DriverDate")
        date_str = None
        if date_raw:
            date_str = str(date_raw)[:10].replace("/", "-")
        drivers.append({
            "name": name,
            "class": cls,
            "version": version,
            "date": date_str,
            "manufacturer": r.get("Manufacturer"),
            "provider": r.get("DriverProviderName"),
            "signed": bool(r.get("IsSigned")),
        })
    drivers.sort(key=lambda d: (d.get("class") or "", d.get("name") or ""))
    return drivers


def _problem_devices() -> list[dict[str, Any]]:
    rows = as_list(ps_json(
        "Get-PnpDevice -PresentOnly -ErrorAction SilentlyContinue | "
        "Where-Object { $_.Problem -ne 0 -and $_.Problem -ne 45 } | "
        "Select-Object FriendlyName,Class,InstanceId,"
        "@{N='Status';E={$_.Status.ToString()}},"
        "@{N='Problem';E={[int]$_.Problem}} | ConvertTo-Json -Compress",
        timeout=30.0,
    ))
    out: list[dict[str, Any]] = []
    for r in rows:
        code = int(r.get("Problem") or 0)
        out.append({
            "name": r.get("FriendlyName"),
            "class": r.get("Class"),
            "status": r.get("Status"),
            "problem_code": code,
            "problem": _PROBLEM_LABELS.get(code, f"Code {code}"),
        })
    return out


def _windows_update_drivers(timeout: float = 75.0) -> tuple[list[dict[str, Any]], str | None]:
    """Query Windows Update for pending driver updates. Returns (updates, error)."""
    data = ps_json(_WU_DRIVER_SCRIPT, timeout=timeout)
    if not isinstance(data, dict):
        return [], "Windows Update query returned no data"
    updates = data.get("available") or []
    if isinstance(updates, dict):
        updates = [updates]
    err = data.get("error")
    cleaned: list[dict[str, Any]] = []
    for u in updates:
        cleaned.append({
            "title": u.get("title"),
            "driver_class": u.get("driver_class"),
            "driver_model": u.get("driver_model"),
            "manufacturer": u.get("manufacturer"),
            "description": (u.get("description") or "")[:200] or None,
        })
    return cleaned, err


def _potentially_outdated(drivers: list[dict[str, Any]], years: float = 3.0) -> list[dict[str, Any]]:
    """Flag signed drivers with very old install dates (heuristic only)."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=int(years * 365))
    stale: list[dict[str, Any]] = []
    for d in drivers:
        dt = _parse_driver_date(d.get("date"))
        if dt and dt < cutoff:
            stale.append({**d, "reason": f"Driver date older than {int(years)} years"})
    return stale[:20]


@safe_scan("drivers")
def scan() -> dict[str, Any]:
    if not IS_WINDOWS:
        return {"available": False, "note": "Driver scanning requires Windows."}

    installed: list[dict[str, Any]] = []
    problems: list[dict[str, Any]] = []
    updates: list[dict[str, Any]] = []
    wu_error: str | None = None

    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = {
            pool.submit(_installed_drivers): "installed",
            pool.submit(_problem_devices): "problems",
            pool.submit(_windows_update_drivers): "updates",
        }
        for fut in as_completed(futures):
            key = futures[fut]
            try:
                result = fut.result()
                if key == "installed":
                    installed = result
                elif key == "problems":
                    problems = result
                else:
                    updates, wu_error = result
            except Exception as exc:  # pragma: no cover - host dependent
                if key == "updates":
                    wu_error = str(exc)

    stale = _potentially_outdated(installed)

    return {
        "available": True,
        "installed_count": len(installed),
        "installed_drivers": installed[:120],
        "problem_devices": problems,
        "problem_count": len(problems),
        "available_updates": updates,
        "available_update_count": len(updates),
        "potentially_outdated": stale,
        "potentially_outdated_count": len(stale),
        "windows_update_error": wu_error,
        "summary": {
            "needs_attention": len(updates) + len(problems),
            "updates_available": len(updates),
            "problem_devices": len(problems),
            "potentially_outdated": len(stale),
        },
    }
