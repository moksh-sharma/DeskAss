"""Input devices probe: mouse, keyboard, touchpad and HID device health."""
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

DOMAIN = "input"
TITLE = "Input Devices (Mouse / Keyboard)"


def _devices(pnp_class: str) -> list[dict]:
    return as_list(ps_json(
        f"Get-PnpDevice -Class {pnp_class} -ErrorAction SilentlyContinue | "
        "Select-Object FriendlyName,Status,Problem,ProblemDescription | ConvertTo-Json -Compress"
    ))


def _hid_problems() -> list[dict]:
    devices = as_list(ps_json(
        "Get-PnpDevice -Class HIDClass -ErrorAction SilentlyContinue | "
        "Select-Object FriendlyName,Status,Problem,ProblemDescription | ConvertTo-Json -Compress"
    ))
    return [d for d in devices if is_real_device_problem(d.get("Status"), d.get("Problem"))]


def _scan_class(label: str, pnp_class: str, checks: list[ProbeCheck],
                findings: list[TroubleshooterFinding], device_word: str) -> None:
    devices = _devices(pnp_class)
    ok = [d for d in devices if str(d.get("Status", "")).lower() == "ok"]
    problem = [d for d in devices if is_real_device_problem(d.get("Status"), d.get("Problem"))]
    checks.append(ProbeCheck(
        label=f"{label} devices",
        value=(f"{len(ok)} working" + (f", {len(problem)} with errors" if problem else ""))
        if (ok or problem) else "None connected",
        status=Severity.warning if problem else (Severity.healthy if ok else Severity.info),
    ))
    if problem:
        top = problem[0]
        findings.append(TroubleshooterFinding(
            id=f"input_{pnp_class.lower()}_problem",
            title=f"{label} Problem Detected",
            area="Input Devices",
            severity=Severity.warning,
            detected=f"{len(problem)} {label.lower()} device(s) with a non-OK status (e.g. "
            f"{top.get('FriendlyName') or label}: {top.get('Status')}"
            + (f", code {top.get('Problem')}" if top.get("Problem") else "") + ").",
            likely_cause=f"A driver problem, a disconnected/dead {device_word}, or (for wireless) a flat "
            "battery or lost USB receiver pairing.",
            resolution_steps=[
                f"For a wired {device_word}: unplug and replug it, ideally into a different USB port.",
                f"For a wireless {device_word}: replace/charge the battery and re-seat the USB receiver; "
                "re-pair if it's Bluetooth.",
                f"Device Manager (`devmgmt.msc`) > {label}: right-click the device > Update driver.",
                f"Uninstall the {device_word} in Device Manager, then Action > Scan for hardware changes.",
                f"Test the {device_word} on another PC (or another {device_word} on this PC) to isolate hardware failure.",
            ],
            ask_ai_prompt=f"My {device_word} isn't working - Device Manager shows a problem. How do I fix it?",
        ))


def investigate(ctx: ProbeContext) -> ProbeOutcome:
    if not IS_WINDOWS:
        return unavailable(DOMAIN, TITLE, "Input device probe only runs on Windows.")

    checks: list[ProbeCheck] = []
    findings: list[TroubleshooterFinding] = []

    wants_mouse = "mouse" in ctx.domains or any(
        w in ctx.message.lower() for w in ("mouse", "touchpad", "trackpad", "cursor", "pointer")
    )
    wants_keyboard = "keyboard" in ctx.domains or "keyboard" in ctx.message.lower()

    # Default: scan both if the domain is generic input.
    if not wants_mouse and not wants_keyboard:
        wants_mouse = wants_keyboard = True

    if wants_mouse:
        _scan_class("Mouse / Pointing", "Mouse", checks, findings, "mouse")
    if wants_keyboard:
        _scan_class("Keyboard", "Keyboard", checks, findings, "keyboard")

    # HID layer (covers many USB/Bluetooth input peripherals).
    hid = _hid_problems()
    if hid:
        top = hid[0]
        checks.append(ProbeCheck(
            label="HID input devices with errors",
            value=str(len(hid)),
            status=Severity.warning,
            detail=top.get("FriendlyName"),
        ))
        if not findings:
            findings.append(TroubleshooterFinding(
                id="input_hid_problem",
                title="Input (HID) Device Problem",
                area="Input Devices",
                severity=Severity.warning,
                detected=f"{len(hid)} HID input device(s) report errors (e.g. {top.get('FriendlyName')}).",
                likely_cause="A driver fault or a flaky USB/Bluetooth connection on an input peripheral.",
                resolution_steps=[
                    "Unplug and replug the device; try another USB port.",
                    "Device Manager > Human Interface Devices: update or reinstall the affected device.",
                    "For wireless devices, replace the battery and re-pair.",
                    "Restart the PC and test again.",
                ],
                ask_ai_prompt="An input device shows an HID error in Device Manager. How do I fix it?",
            ))
    else:
        checks.append(ProbeCheck(label="HID input devices with errors", value="None", status=Severity.healthy))

    return ProbeOutcome(
        result=ProbeResult(domain=DOMAIN, title=TITLE, available=True, checks=checks),
        findings=findings,
    )
