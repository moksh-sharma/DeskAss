"""Webcam / camera live probe: PnP camera devices, driver health, privacy access."""
from __future__ import annotations

from app.models.schemas import ProbeCheck, ProbeResult, Severity, TroubleshooterFinding
from app.services.probes.base import (
    IS_WINDOWS,
    ProbeContext,
    ProbeOutcome,
    as_list,
    is_real_device_problem,
    ps_json,
    run_powershell,
    unavailable,
)

DOMAIN = "webcam"
TITLE = "Webcam / Camera"


def _camera_devices() -> list[dict]:
    """Enumerate built-in and USB cameras (Camera + legacy Image classes)."""
    devices = as_list(ps_json(
        "$classes = @('Camera','Image'); "
        "Get-PnpDevice -PresentOnly -ErrorAction SilentlyContinue | "
        "Where-Object { $classes -contains $_.Class -or $_.FriendlyName -match 'camera|webcam|integrated cam' } | "
        "Select-Object FriendlyName,Status,Class,Problem,ProblemDescription | ConvertTo-Json -Compress"
    ))
    return devices


def _global_camera_access() -> str | None:
    """Return Allow/Deny for system camera access, or None if unknown."""
    ok, out = run_powershell(
        "$paths = @("
        "'HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\CapabilityAccessManager\\ConsentStore\\webcam',"
        "'HKCU:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\CapabilityAccessManager\\ConsentStore\\webcam'"
        "); "
        "foreach ($p in $paths) { "
        "  if (Test-Path $p) { "
        "    (Get-ItemProperty -Path $p -Name Value -ErrorAction SilentlyContinue).Value; break "
        "  } "
        "}"
    )
    if not ok or not out.strip():
        return None
    return out.strip()


def investigate(ctx: ProbeContext) -> ProbeOutcome:
    if not IS_WINDOWS:
        return unavailable(DOMAIN, TITLE, "Camera probe only runs on Windows.")

    checks: list[ProbeCheck] = []
    findings: list[TroubleshooterFinding] = []

    devices = _camera_devices()
    ok_devices = [d for d in devices if str(d.get("Status", "")).lower() == "ok"]
    problem = [d for d in devices if is_real_device_problem(d.get("Status"), d.get("Problem"))]

    checks.append(ProbeCheck(
        label="Camera devices detected",
        value=(
            f"{len(ok_devices)} working"
            + (f", {len(problem)} with errors" if problem else "")
            if devices
            else "None detected"
        ),
        status=(
            Severity.warning if problem else
            (Severity.healthy if ok_devices else Severity.critical)
        ),
        detail=", ".join(d.get("FriendlyName") or "Camera" for d in devices[:3]) or None,
    ))

    access = _global_camera_access()
    if access:
        allowed = access.lower() == "allow"
        checks.append(ProbeCheck(
            label="System camera access",
            value=access,
            status=Severity.healthy if allowed else Severity.warning,
        ))
        if not allowed:
            findings.append(TroubleshooterFinding(
                id="webcam_privacy_denied",
                title="Camera Access Disabled in Windows",
                area="Webcam",
                severity=Severity.warning,
                detected="Windows reports camera access is denied at the system level.",
                likely_cause="Camera privacy settings block all apps from using the webcam.",
                resolution_steps=[
                    "Settings > Privacy & security > Camera > turn on 'Camera access'.",
                    "Enable 'Let apps access your camera' and allow access for the app you are using.",
                    "Check for a physical privacy shutter or Fn key that disables the camera.",
                    "Restart the PC and test in the built-in Camera app.",
                ],
                ask_ai_prompt="Windows camera access is denied. How do I enable my webcam?",
            ))

    if not devices:
        findings.append(TroubleshooterFinding(
            id="webcam_not_detected",
            title="No Camera Detected",
            area="Webcam",
            severity=Severity.critical,
            detected="Windows does not report any camera or imaging device on this PC.",
            likely_cause="The camera driver is missing, the device is disabled in Device Manager/BIOS, "
            "or an external webcam is unplugged.",
            resolution_steps=[
                "For external webcams: reconnect USB, try another port/cable.",
                "Device Manager > Cameras (or Imaging devices): enable the device or install/update the driver.",
                "Uninstall the camera device, then Action > Scan for hardware changes.",
                "On business laptops, check BIOS/UEFI for a camera disable option.",
                "Test in the built-in Camera app after each change.",
            ],
            ask_ai_prompt="Windows can't find my camera at all. How do I get it working?",
        ))
    elif problem:
        top = problem[0]
        findings.append(TroubleshooterFinding(
            id="webcam_device_error",
            title="Camera Driver or Device Error",
            area="Webcam",
            severity=Severity.warning,
            detected=f"{len(problem)} camera device(s) report errors (e.g. "
            f"{top.get('FriendlyName') or 'Camera'}: {top.get('Status')}"
            + (f", code {top.get('Problem')}" if top.get("Problem") else "") + ").",
            likely_cause="A faulty/outdated camera driver, a disabled device, or another app holding the camera.",
            resolution_steps=[
                "Close apps that may use the camera (Teams, Zoom, OBS, browser tabs) and retry.",
                "Device Manager > Cameras > right-click the device > Update driver.",
                "Uninstall the camera, then Action > Scan for hardware changes to reinstall.",
                "Settings > Privacy & security > Camera: ensure access is allowed for your app.",
                "Test in the built-in Camera app to confirm the device works outside meeting software.",
            ],
            ask_ai_prompt="My webcam shows a driver/device error in Device Manager. How do I fix it?",
        ))
    elif not findings:
        checks.append(ProbeCheck(
            label="Camera hardware status",
            value="Devices OK — check app permissions if video still fails",
            status=Severity.info,
        ))

    return ProbeOutcome(
        result=ProbeResult(domain=DOMAIN, title=TITLE, available=True, checks=checks),
        findings=findings,
    )
