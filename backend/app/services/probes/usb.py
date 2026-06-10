"""USB live probe pack: USB controllers and devices with error states."""
from __future__ import annotations

from app.models.schemas import ProbeCheck, ProbeResult, Severity, TroubleshooterFinding
from app.services.probes.base import (
    IS_WINDOWS,
    ProbeContext,
    ProbeOutcome,
    as_list,
    is_real_device_problem,
    ps_json,
    unavailable,
)

DOMAIN = "usb"
TITLE = "USB Devices"


def _problem_devices() -> list[dict]:
    # USB / unknown devices, then keep only genuine faults (exclude disconnected
    # phantom devices, which show Status 'Unknown' / Problem code 45).
    devices = as_list(ps_json(
        "Get-PnpDevice -ErrorAction SilentlyContinue | "
        "Where-Object { $_.Status -ne 'OK' -and ($_.Class -eq 'USB' -or $_.InstanceId -match 'USB' "
        "-or $_.FriendlyName -match 'Unknown') } | "
        "Select-Object FriendlyName,Status,Class,Problem,ProblemDescription | ConvertTo-Json -Compress"
    ))
    return [d for d in devices if is_real_device_problem(d.get("Status"), d.get("Problem"))]


def _usb_controllers() -> list[dict]:
    return as_list(ps_json(
        "Get-PnpDevice -Class USB -ErrorAction SilentlyContinue | "
        "Select-Object Status,Problem | ConvertTo-Json -Compress"
    ))


def investigate(ctx: ProbeContext) -> ProbeOutcome:
    if not IS_WINDOWS:
        return unavailable(DOMAIN, TITLE, "USB probe only runs on Windows.")

    checks: list[ProbeCheck] = []
    findings: list[TroubleshooterFinding] = []

    controllers = _usb_controllers()
    # Exclude disconnected phantom devices (Status 'Unknown' / code 45) from the
    # "connected" count so a healthy machine doesn't look broken.
    connected = [c for c in controllers if str(c.get("Status", "")).lower() != "unknown"]
    ok_controllers = [c for c in connected if str(c.get("Status", "")).lower() == "ok"]
    checks.append(ProbeCheck(
        label="USB controllers/devices (OK)",
        value=f"{len(ok_controllers)}/{len(connected)}" if connected else "None connected",
        status=Severity.healthy if connected else Severity.info,
    ))

    problems = _problem_devices()
    if problems:
        names = ", ".join(p.get("FriendlyName") or "Unknown device" for p in problems[:4])
        checks.append(ProbeCheck(
            label="USB/unknown devices with errors",
            value=str(len(problems)),
            status=Severity.warning,
            detail=names,
        ))
        top = problems[0]
        findings.append(TroubleshooterFinding(
            id="usb_device_error",
            title="USB Device Not Working Correctly",
            area="USB",
            severity=Severity.warning,
            detected=f"{len(problems)} USB/unknown device(s) report errors (e.g. "
            f"{top.get('FriendlyName') or 'Unknown device'}: {top.get('Status')}"
            + (f", code {top.get('Problem')}" if top.get("Problem") else "") + ").",
            likely_cause="A driver failed to load, the device is faulty, or USB power management is "
            "turning the port off.",
            resolution_steps=[
                "Unplug and replug the device; try a different USB port (prefer a rear/USB 2.0 port to test).",
                "Device Manager: right-click the problem/unknown device > Update driver.",
                "Uninstall the device, then Action > Scan for hardware changes.",
                "Disable USB selective suspend: Control Panel > Power Options > Change plan > USB settings.",
                "Test the device on another PC to rule out hardware failure.",
            ],
            ask_ai_prompt="A USB device shows an error / 'not recognized'. How do I get it working?",
        ))
    else:
        checks.append(ProbeCheck(label="USB devices with errors", value="None", status=Severity.healthy))

    return ProbeOutcome(
        result=ProbeResult(domain=DOMAIN, title=TITLE, available=True, checks=checks),
        findings=findings,
    )
