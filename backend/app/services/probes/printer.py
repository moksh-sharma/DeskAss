"""Printer live probe pack: Spooler service, installed printers, queue state."""
from __future__ import annotations

from app.models.schemas import ProbeCheck, ProbeResult, Severity, TroubleshooterFinding
from app.services.probes.base import (
    IS_WINDOWS,
    ProbeContext,
    ProbeOutcome,
    as_list,
    get_service,
    ps_json,
    unavailable,
)

DOMAIN = "printer"
TITLE = "Printers"


def _printers() -> list[dict]:
    return as_list(ps_json(
        "Get-Printer -ErrorAction SilentlyContinue | "
        "Select-Object Name,PrinterStatus,WorkOffline,Default | ConvertTo-Json -Compress"
    ))


def _queue_count() -> int:
    data = ps_json(
        "(Get-Printer -ErrorAction SilentlyContinue | "
        "ForEach-Object { Get-PrintJob -PrinterName $_.Name -ErrorAction SilentlyContinue }).Count "
        "| ConvertTo-Json -Compress"
    )
    try:
        return int(data) if data is not None else 0
    except (TypeError, ValueError):
        return 0


def investigate(ctx: ProbeContext) -> ProbeOutcome:
    if not IS_WINDOWS:
        return unavailable(DOMAIN, TITLE, "Printer probe only runs on Windows.")

    checks: list[ProbeCheck] = []
    findings: list[TroubleshooterFinding] = []

    svc = get_service("Spooler")
    spooler_running = bool(svc) and str(svc.get("Status", "")).lower() == "running"
    if svc:
        checks.append(ProbeCheck(
            label="Print Spooler service",
            value=f"{svc.get('Status')} (start: {svc.get('StartType')})",
            status=Severity.healthy if spooler_running else Severity.critical,
        ))
        if not spooler_running:
            findings.append(TroubleshooterFinding(
                id="printer_spooler_stopped",
                title="Print Spooler Is Not Running",
                area="Printers",
                severity=Severity.critical,
                detected=f"The Print Spooler service is {svc.get('Status')}.",
                likely_cause="Without the spooler, no printing is possible. It may have crashed on a stuck job.",
                resolution_steps=[
                    "Open Services (`services.msc`) > 'Print Spooler'.",
                    "Set Startup type to Automatic and click Start.",
                    "If it won't stay running, clear stuck jobs: stop the spooler, delete files in "
                    "`C:\\Windows\\System32\\spool\\PRINTERS`, then start it again.",
                    "Retry your print job.",
                ],
                ask_ai_prompt="My Print Spooler service keeps stopping and I can't print. How do I fix it?",
            ))

    printers = _printers()
    checks.append(ProbeCheck(
        label="Installed printers",
        value=str(len(printers)) if printers else "None",
        status=Severity.healthy if printers else Severity.warning,
    ))

    offline = [p for p in printers if p.get("WorkOffline")]
    for p in printers:
        name = p.get("Name")
        off = bool(p.get("WorkOffline"))
        checks.append(ProbeCheck(
            label=f"Printer: {name}",
            value=("Offline" if off else "Ready") + (" (default)" if p.get("Default") else ""),
            status=Severity.warning if off else Severity.healthy,
        ))

    if offline and spooler_running:
        names = ", ".join(p.get("Name", "printer") for p in offline[:3])
        findings.append(TroubleshooterFinding(
            id="printer_offline",
            title="Printer Shows Offline",
            area="Printers",
            severity=Severity.warning,
            detected=f"Printer(s) marked offline: {names}.",
            likely_cause="The PC can't reach the printer (powered off, network/USB issue) or 'Use Printer Offline' is set.",
            resolution_steps=[
                "Confirm the printer is powered on and connected (USB seated or on the same network).",
                "Settings > Bluetooth & devices > Printers & scanners > the printer > uncheck 'Use printer offline'.",
                "For network printers, verify the printer's IP is reachable (ping it).",
                "Restart the Print Spooler service and retry.",
            ],
            ask_ai_prompt="My printer shows offline even though it's on. How do I bring it back online?",
        ))

    queue = _queue_count()
    if queue:
        checks.append(ProbeCheck(label="Pending print jobs", value=str(queue),
                                 status=Severity.info if queue < 3 else Severity.warning))

    return ProbeOutcome(
        result=ProbeResult(domain=DOMAIN, title=TITLE, available=True, checks=checks),
        findings=findings,
    )
