"""Bluetooth live probe pack.

Scans everything relevant to Bluetooth on this machine: adapters/drivers,
required services, radio state, paired devices and recent Bluetooth event-log
errors - then derives findings from those facts (no knowledge base)."""
from __future__ import annotations

from app.models.schemas import ProbeCheck, ProbeResult, Severity, TroubleshooterFinding
from app.services.probes.base import (
    ProbeContext,
    ProbeOutcome,
    as_list,
    get_service,
    is_real_device_problem,
    ps_json,
    unavailable,
    worst_status,
)

DOMAIN = "bluetooth"
TITLE = "Bluetooth"

# Services Bluetooth depends on (name -> friendly label).
_SERVICES = {
    "bthserv": "Bluetooth Support Service",
    "BTAGService": "Bluetooth Audio Gateway Service",
}


def _get_adapters() -> list[dict]:
    data = ps_json(
        "Get-PnpDevice -Class Bluetooth -ErrorAction SilentlyContinue | "
        "Select-Object FriendlyName,Status,InstanceId,Problem,ProblemDescription | "
        "ConvertTo-Json -Compress"
    )
    return as_list(data)


def _get_radios() -> list[dict]:
    # Requires the Windows.Devices.Radios WinRT API; fall back gracefully.
    data = ps_json(
        "Get-PnpDevice -Class Bluetooth -ErrorAction SilentlyContinue | "
        "Where-Object { $_.FriendlyName } | "
        "Select-Object FriendlyName,Status | ConvertTo-Json -Compress"
    )
    return as_list(data)


def _get_bt_events() -> list[dict]:
    data = ps_json(
        "Get-WinEvent -FilterHashtable @{LogName='System'; Level=1,2; "
        "ProviderName='BTHUSB','BthEnum','Microsoft-Windows-Bluetooth-BthLEEnum','BthLEEnum'} "
        "-MaxEvents 15 -ErrorAction SilentlyContinue | "
        "Select-Object Id,ProviderName,LevelDisplayName,TimeCreated,Message | "
        "ConvertTo-Json -Compress",
        timeout=25.0,
    )
    return as_list(data)


def investigate(ctx: ProbeContext) -> ProbeOutcome:
    from app.services.probes.base import IS_WINDOWS

    if not IS_WINDOWS:
        return unavailable(DOMAIN, TITLE, "Bluetooth probe only runs on Windows.")

    checks: list[ProbeCheck] = []
    findings: list[TroubleshooterFinding] = []

    adapters = _get_adapters()
    if not adapters:
        checks.append(ProbeCheck(
            label="Bluetooth adapter",
            value="None found",
            status=Severity.critical,
        ))
        findings.append(TroubleshooterFinding(
            id="bt_no_adapter",
            title="No Bluetooth Adapter Detected",
            area="Bluetooth",
            severity=Severity.critical,
            detected="Windows reports no Bluetooth adapter (Get-PnpDevice -Class Bluetooth returned nothing).",
            likely_cause="The Bluetooth driver is not installed, the adapter is disabled in BIOS/UEFI, "
            "or the hardware is absent/faulty.",
            resolution_steps=[
                "Open Device Manager (`devmgmt.msc`) and choose View > Show hidden devices; look for a Bluetooth or Unknown device.",
                "If listed under 'Other devices', install the wireless/Bluetooth driver from your PC maker's support site.",
                "Check BIOS/UEFI: ensure the wireless/Bluetooth radio is enabled.",
                "Confirm airplane mode is off (Settings > Network & internet > Airplane mode).",
                "Restart the PC after installing the driver.",
            ],
            ask_ai_prompt="Windows shows no Bluetooth adapter at all. How do I get Bluetooth working again?",
        ))
    else:
        for a in adapters:
            name = a.get("FriendlyName") or "Bluetooth adapter"
            status = (a.get("Status") or "Unknown")
            problem = a.get("Problem")
            problem_desc = a.get("ProblemDescription")
            real_problem = is_real_device_problem(status, problem)
            ok = not real_problem
            sev = Severity.healthy if ok else Severity.critical
            val = status if ok else f"{status}" + (f" (code {problem})" if problem else "")
            checks.append(ProbeCheck(label=f"Adapter: {name}", value=str(val), status=sev,
                                     detail=problem_desc))
            if real_problem:
                findings.append(TroubleshooterFinding(
                    id="bt_adapter_error",
                    title=f"Bluetooth Adapter Problem: {name}",
                    area="Bluetooth",
                    severity=Severity.critical,
                    detected=f"Adapter '{name}' status is '{status}'"
                    + (f", problem code {problem}" if problem else "")
                    + (f" - {problem_desc}" if problem_desc else "") + ".",
                    likely_cause="The Bluetooth driver failed to start or is corrupt/incompatible "
                    "(often after a Windows or driver update).",
                    resolution_steps=[
                        f"Open Device Manager (`devmgmt.msc`) > Bluetooth > '{name}'.",
                        "Right-click > Update driver > Search automatically.",
                        "If it was working before a recent update, use Driver tab > Roll Back Driver.",
                        "If that fails: right-click > Uninstall device (tick 'delete driver'), then Action > Scan for hardware changes.",
                        "Reinstall the latest wireless/Bluetooth driver from your PC maker and restart.",
                    ],
                    ask_ai_prompt=f"My Bluetooth adapter '{name}' shows status {status}"
                    + (f" code {problem}" if problem else "") + ". How do I fix the driver?",
                ))

    # Services. Only bthserv is essential; others (e.g. Audio Gateway) are
    # trigger-started, so a stopped state there is normal - show as info.
    for svc_name, label in _SERVICES.items():
        svc = get_service(svc_name)
        if not svc:
            continue
        status = str(svc.get("Status", ""))
        start = str(svc.get("StartType", ""))
        running = status.lower() == "running"
        is_primary = svc_name == "bthserv"
        if running:
            sev = Severity.healthy
        else:
            sev = Severity.warning if is_primary else Severity.info
        checks.append(ProbeCheck(label=label, value=f"{status} (start: {start})", status=sev))
        if not running and is_primary:
            findings.append(TroubleshooterFinding(
                id="bt_service_stopped",
                title="Bluetooth Support Service Is Not Running",
                area="Bluetooth",
                severity=Severity.warning,
                detected=f"'{label}' ({svc_name}) is {status}, start type {start}.",
                likely_cause="The Bluetooth Support Service is stopped or disabled, so Bluetooth devices "
                "can't be discovered or connected.",
                resolution_steps=[
                    "Open Services (`services.msc`) and find 'Bluetooth Support Service'.",
                    "Set Startup type to 'Manual (Trigger Start)' or 'Automatic'.",
                    "Click Start to run it now, then click OK.",
                    "Try connecting your Bluetooth device again.",
                ],
                ask_ai_prompt="My Bluetooth Support Service (bthserv) is stopped. How do I start it and keep it running?",
            ))

    # Recent Bluetooth event-log errors.
    events = _get_bt_events()
    if events:
        top = events[0]
        checks.append(ProbeCheck(
            label="Recent Bluetooth errors (System log)",
            value=f"{len(events)} in recent log",
            status=Severity.warning,
            detail=f"{top.get('ProviderName')} (ID {top.get('Id')}): {str(top.get('Message',''))[:120]}",
        ))
        # Only raise a dedicated finding if nothing more specific already fired.
        if not findings:
            findings.append(TroubleshooterFinding(
                id="bt_log_errors",
                title="Bluetooth Errors in the Event Log",
                area="Bluetooth",
                severity=Severity.warning,
                detected=f"{len(events)} recent Bluetooth-related error/warning events "
                f"(e.g. {top.get('ProviderName')} ID {top.get('Id')}).",
                likely_cause="The Bluetooth stack is logging failures - often pairing timeouts, a flaky "
                "driver, or radio interference.",
                resolution_steps=[
                    "Remove the problem device: Settings > Bluetooth & devices > the device > Remove device.",
                    "Put the device in pairing mode and add it again (Add device > Bluetooth).",
                    "Run the built-in troubleshooter: Settings > System > Troubleshoot > Other troubleshooters > Bluetooth.",
                    "Update the Bluetooth driver from Device Manager.",
                    "Reduce 2.4 GHz interference (move away from USB 3.0 hubs / crowded Wi-Fi).",
                ],
                ask_ai_prompt="My Windows System log has repeated Bluetooth errors. What is the likely cause and fix?",
            ))
    else:
        checks.append(ProbeCheck(label="Recent Bluetooth errors (System log)", value="None", status=Severity.healthy))

    # Paired-device hint (best-effort; absence isn't an error).
    radios = _get_radios()
    if radios:
        checks.append(ProbeCheck(
            label="Bluetooth devices visible to Windows",
            value=f"{len(radios)} entr{'y' if len(radios) == 1 else 'ies'}",
            status=Severity.info,
        ))

    result = ProbeResult(
        domain=DOMAIN,
        title=TITLE,
        available=True,
        checks=checks,
        note=None if adapters else "No Bluetooth adapter present.",
    )
    # Keep result status consistent with checks for callers that want it.
    _ = worst_status([c.status for c in checks]) if checks else Severity.info
    return ProbeOutcome(result=result, findings=findings)
