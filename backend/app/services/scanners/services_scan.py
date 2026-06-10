"""Windows-services scanner: status of all + monitored critical services."""
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


def _all_services() -> list[dict]:
    rows = as_list(ps_json(
        "Get-Service -ErrorAction SilentlyContinue | Select-Object Name,DisplayName,"
        "@{N='Status';E={$_.Status.ToString()}},"
        "@{N='StartType';E={$_.StartType.ToString()}} | ConvertTo-Json -Compress",
        timeout=25.0,
    ))
    return rows


@safe_scan("services")
def scan(inventory=None) -> dict:
    services = _all_services()
    by_name = {(s.get("Name") or "").lower(): s for s in services}

    monitored = []
    for friendly, short in _MONITORED.items():
        s = by_name.get(short.lower())
        if not s:
            monitored.append({"name": friendly, "service": short, "status": "Not installed",
                              "start_type": None, "issue": False})
            continue
        status = s.get("Status")
        start = s.get("StartType")
        issue = short in _SHOULD_RUN and status != "Running"
        monitored.append({
            "name": friendly,
            "service": short,
            "status": status,
            "start_type": start,
            "issue": issue,
        })

    stopped_auto = [
        {"name": s.get("DisplayName") or s.get("Name"), "status": s.get("Status"),
         "start_type": s.get("StartType")}
        for s in services
        if s.get("StartType") == "Automatic" and s.get("Status") != "Running"
    ]
    failed_critical = [m for m in monitored if m.get("issue")]

    return {
        "total_count": len(services),
        "running_count": sum(1 for s in services if s.get("Status") == "Running"),
        "monitored": monitored,
        "stopped_automatic": stopped_auto[:30],
        "failed_critical": failed_critical,
    }
