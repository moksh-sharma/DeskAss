"""Service intelligence scanner: full inventory (running/stopped/disabled),
monitored critical services, dependencies and failure actions."""
from __future__ import annotations

from app.services.scanners.base import as_list, ps_json, safe_scan

# Friendly name -> service short name for the critical services to monitor.
_MONITORED = {
    "Windows Update": "wuauserv",
    "DNS Client": "Dnscache",
    "DHCP Client": "Dhcp",
    "Windows Defender": "WinDefend",
    "Print Spooler": "Spooler",
    "Windows Event Log": "EventLog",
    "Remote Desktop Services": "TermService",
    "Network Location Awareness": "NlaSvc",
    "Workstation": "LanmanWorkstation",
    "Server": "LanmanServer",
    "Docker": "com.docker.service",
    "SQL Server": "MSSQLSERVER",
}

# Critical services that should normally be running.
_SHOULD_RUN = {"Dnscache", "Dhcp", "EventLog", "NlaSvc", "LanmanWorkstation"}

_MAX_INVENTORY = 400


def _all_services() -> list[dict]:
    """Full service inventory via Win32_Service (gives Disabled start mode + PID)."""
    rows = as_list(ps_json(
        "Get-CimInstance Win32_Service -ErrorAction SilentlyContinue | Select-Object "
        "Name,DisplayName,State,StartMode,ProcessId | ConvertTo-Json -Compress",
        timeout=30.0,
    ))
    return rows


def _dependencies(short: str) -> dict:
    """Dependencies for a single service (depended-on + dependents)."""
    script = (
        "$s = Get-Service -Name '" + short + "' -ErrorAction SilentlyContinue; "
        "if ($s) { [pscustomobject]@{ "
        "RequiredServices = @($s.ServicesDependedOn | ForEach-Object Name); "
        "DependentServices = @($s.DependentServices | ForEach-Object Name) "
        "} | ConvertTo-Json -Compress }"
    )
    rows = ps_json(script, timeout=10.0)
    if isinstance(rows, dict):
        return {
            "required_services": as_list(rows.get("RequiredServices")),
            "dependent_services": as_list(rows.get("DependentServices")),
        }
    return {"required_services": [], "dependent_services": []}


def _failure_actions(short: str) -> dict | None:
    """Recovery/failure configuration for a service via `sc qfailure`."""
    script = (
        "$r = sc.exe qfailure '" + short + "' 2>$null | Out-String; "
        "$reset = if ($r -match 'RESET_PERIOD.*: (\\d+)') { [int]$Matches[1] } else { $null }; "
        "$actions = ([regex]::Matches($r, 'RESTART|RUN|REBOOT')).Count; "
        "[pscustomobject]@{ reset_period = $reset; action_count = $actions } | ConvertTo-Json -Compress"
    )
    out = ps_json(script, timeout=10.0)
    if isinstance(out, dict):
        return {"reset_period_s": out.get("reset_period"), "configured_actions": out.get("action_count")}
    return None


@safe_scan("services")
def scan(inventory=None) -> dict:
    services = _all_services()
    by_name = {(s.get("Name") or "").lower(): s for s in services}

    def _status(s: dict) -> str:
        return s.get("State") or "Unknown"

    def _start(s: dict) -> str:
        return s.get("StartMode") or "Unknown"

    monitored = []
    for friendly, short in _MONITORED.items():
        s = by_name.get(short.lower())
        if not s:
            monitored.append({"name": friendly, "service": short, "status": "Not installed",
                              "start_type": None, "issue": False})
            continue
        status = _status(s)
        issue = short in _SHOULD_RUN and status != "Running"
        entry = {
            "name": friendly,
            "service": short,
            "status": status,
            "start_type": _start(s),
            "issue": issue,
        }
        # Dependency/recovery lookups spawn a PowerShell process each, so only
        # do them for genuinely critical services or ones with a problem.
        if short in _SHOULD_RUN or issue:
            entry["dependencies"] = _dependencies(short)
        if issue:
            entry["failure_actions"] = _failure_actions(short)
        monitored.append(entry)

    running = [s for s in services if _status(s) == "Running"]
    stopped = [s for s in services if _status(s) == "Stopped"]
    disabled = [s for s in services if _start(s) == "Disabled"]

    stopped_auto = [
        {"name": s.get("DisplayName") or s.get("Name"), "status": _status(s),
         "start_type": _start(s)}
        for s in services
        if _start(s) in ("Auto", "Automatic") and _status(s) != "Running"
    ]
    failed_critical = [m for m in monitored if m.get("issue")]

    inventory_list = [
        {"name": s.get("Name"), "display_name": s.get("DisplayName"),
         "status": _status(s), "start_type": _start(s), "pid": s.get("ProcessId")}
        for s in sorted(services, key=lambda x: (x.get("DisplayName") or x.get("Name") or ""))
    ][:_MAX_INVENTORY]

    return {
        "total_count": len(services),
        "running_count": len(running),
        "stopped_count": len(stopped),
        "disabled_count": len(disabled),
        "monitored": monitored,
        "stopped_automatic": stopped_auto[:30],
        "disabled_services": [
            {"name": s.get("DisplayName") or s.get("Name"), "service": s.get("Name")}
            for s in disabled
        ][:30],
        "failed_critical": failed_critical,
        "inventory": inventory_list,
        "inventory_truncated": len(services) > _MAX_INVENTORY,
    }
