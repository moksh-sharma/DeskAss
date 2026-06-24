"""User activity scanner: most/least used applications (UserAssist), per-account
logon counts, and currently active interactive sessions.

App-usage telemetry comes from the per-user UserAssist registry (run counts +
last-used time, no admin needed). Logon history uses Win32_NetworkLoginProfile;
the Security event log (4624/4634) is read opportunistically when elevated.
"""
from __future__ import annotations

import os
import re

from app.services.scanners.base import as_list, ps_json, run_powershell, safe_scan

# UserAssist: ROT13-encoded value names, binary data with run count + last-used.
_USERASSIST_PS = r"""
$guids = Get-ChildItem 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Explorer\UserAssist' -ErrorAction SilentlyContinue
$results = @()
foreach ($g in $guids) {
  $countPath = Join-Path $g.PSPath 'Count'
  $key = Get-Item -LiteralPath $countPath -ErrorAction SilentlyContinue
  if (-not $key) { continue }
  foreach ($name in $key.GetValueNames()) {
    $decoded = -join ($name.ToCharArray() | ForEach-Object {
      $c = [int]$_
      if ($c -ge 65 -and $c -le 90) { [char](65 + (($c - 65 + 13) % 26)) }
      elseif ($c -ge 97 -and $c -le 122) { [char](97 + (($c - 97 + 13) % 26)) }
      else { [char]$c }
    })
    $data = $key.GetValue($name)
    if ($data -isnot [byte[]] -or $data.Length -lt 8) { continue }
    $runcount = [BitConverter]::ToInt32($data, 4)
    $last = $null
    if ($data.Length -ge 68) {
      $ft = [BitConverter]::ToInt64($data, 60)
      if ($ft -gt 0) { try { $last = [DateTime]::FromFileTime($ft).ToString('o') } catch {} }
    }
    if ($decoded -match '\.exe' -and $runcount -gt 0) {
      $results += [pscustomobject]@{ name = $decoded; run_count = $runcount; last_used = $last }
    }
  }
}
$results | Sort-Object run_count -Descending | Select-Object -First 40 | ConvertTo-Json -Compress
"""


def _leaf(name: str) -> str:
    """Strip the {GUID}\\ prefix and folder path to the executable's leaf name."""
    name = re.sub(r"^\{[0-9A-Fa-f-]+\}\\?", "", name or "")
    name = name.replace("/", "\\")
    return os.path.basename(name) or name


def _most_used_apps() -> list[dict]:
    rows = as_list(ps_json(_USERASSIST_PS, timeout=25.0))
    apps: list[dict] = []
    seen: set[str] = set()
    for r in rows:
        leaf = _leaf(r.get("name") or "")
        if not leaf.lower().endswith(".exe"):
            continue
        key = leaf.lower()
        if key in seen:
            continue
        seen.add(key)
        apps.append({
            "app": leaf,
            "run_count": r.get("run_count"),
            "last_used": r.get("last_used"),
            "path": r.get("name"),
        })
    return apps


def _account_logons() -> list[dict]:
    rows = as_list(ps_json(
        "Get-CimInstance Win32_NetworkLoginProfile -ErrorAction SilentlyContinue | "
        "Select-Object Name,NumberOfLogons,LastLogon,LastLogoff | ConvertTo-Json -Compress",
        timeout=20.0,
    ))
    out = []
    for r in rows:
        name = r.get("Name")
        if not name:
            continue
        out.append({
            "account": name,
            "logon_count": r.get("NumberOfLogons"),
            "last_logon": r.get("LastLogon"),
            "last_logoff": r.get("LastLogoff"),
        })
    return out


def _active_sessions() -> list[dict]:
    """Currently logged-on interactive sessions via `quser`."""
    ok, out = run_powershell(
        "quser 2>$null | ForEach-Object { $_ -replace '\\s{2,}', ',' }", timeout=15.0
    )
    if not ok or not out:
        return []
    sessions = []
    for line in out.splitlines()[1:]:  # skip header
        parts = [p.strip() for p in line.lstrip(">").split(",") if p.strip()]
        if len(parts) >= 2:
            sessions.append({"raw": ", ".join(parts)})
    return sessions


def _recent_logons() -> dict:
    """Recent successful logons from the Security log (needs elevation)."""
    rows = ps_json(
        "Get-WinEvent -FilterHashtable @{LogName='Security';Id=4624} -MaxEvents 20 "
        "-ErrorAction SilentlyContinue | Select-Object @{N='time';E={$_.TimeCreated.ToString('o')}} | "
        "ConvertTo-Json -Compress",
        timeout=20.0,
    )
    items = as_list(rows)
    if not items:
        return {"available": False, "note": "Security log requires Administrator."}
    return {"available": True, "recent_logon_times": [r.get("time") for r in items if r.get("time")][:20]}


@safe_scan("user_activity")
def scan() -> dict:
    most_used = _most_used_apps()
    return {
        "most_used_apps": most_used[:20],
        "least_used_apps": [a for a in most_used if (a.get("run_count") or 0) > 0][-10:],
        "account_logons": _account_logons(),
        "active_sessions": _active_sessions(),
        "logon_events": _recent_logons(),
        "available": True,
    }
