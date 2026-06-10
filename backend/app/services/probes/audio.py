"""Audio live probe pack: audio service, playback devices, audio drivers."""
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

DOMAIN = "audio"
TITLE = "Audio / Sound"

_SERVICES = {"Audiosrv": "Windows Audio", "AudioEndpointBuilder": "Windows Audio Endpoint Builder"}


def _devices() -> list[dict]:
    return as_list(ps_json(
        "Get-PnpDevice -Class AudioEndpoint,Media -ErrorAction SilentlyContinue | "
        "Select-Object FriendlyName,Status,Class,Problem | ConvertTo-Json -Compress"
    ))


def investigate(ctx: ProbeContext) -> ProbeOutcome:
    if not IS_WINDOWS:
        return unavailable(DOMAIN, TITLE, "Audio probe only runs on Windows.")

    checks: list[ProbeCheck] = []
    findings: list[TroubleshooterFinding] = []

    audio_stopped = False
    for name, label in _SERVICES.items():
        svc = get_service(name)
        if not svc:
            continue
        running = str(svc.get("Status", "")).lower() == "running"
        checks.append(ProbeCheck(
            label=label,
            value=f"{svc.get('Status')} (start: {svc.get('StartType')})",
            status=Severity.healthy if running else Severity.warning,
        ))
        if not running and name == "Audiosrv":
            audio_stopped = True

    if audio_stopped:
        findings.append(TroubleshooterFinding(
            id="audio_service_stopped",
            title="Windows Audio Service Not Running",
            area="Audio",
            severity=Severity.warning,
            detected="The Windows Audio service (Audiosrv) is not running.",
            likely_cause="Without the audio service, no sound will play on any device.",
            resolution_steps=[
                "Open Services (`services.msc`) > 'Windows Audio'.",
                "Set Startup type to Automatic and click Start.",
                "Also start 'Windows Audio Endpoint Builder'.",
                "Restart the PC if sound is still missing.",
            ],
            ask_ai_prompt="My Windows Audio service is stopped and there's no sound. How do I fix it?",
        ))

    devices = _devices()
    active = [d for d in devices if str(d.get("Status", "")).lower() == "ok"]
    problem = [d for d in devices if d.get("Class") == "Media" and str(d.get("Status", "")).lower() != "ok"]

    checks.append(ProbeCheck(
        label="Audio endpoints detected",
        value=str(len([d for d in devices if d.get("Class") == "AudioEndpoint"])),
        status=Severity.healthy if active else Severity.warning,
    ))

    if not devices:
        findings.append(TroubleshooterFinding(
            id="audio_no_device",
            title="No Audio Device Detected",
            area="Audio",
            severity=Severity.critical,
            detected="Windows reports no audio endpoint/media devices.",
            likely_cause="The audio driver is missing/disabled, or the output device is unplugged.",
            resolution_steps=[
                "Device Manager > Sound, video and game controllers: enable/install the audio driver.",
                "Reinstall the audio driver from your PC maker's site.",
                "Check the physical connection (speakers/headphones plugged into the right jack).",
                "Run: Settings > System > Sound > Troubleshoot.",
            ],
            ask_ai_prompt="Windows shows no audio device at all. How do I restore sound output?",
        ))
    elif problem:
        names = ", ".join(d.get("FriendlyName", "audio device") for d in problem[:3])
        findings.append(TroubleshooterFinding(
            id="audio_device_problem",
            title="Audio Driver Problem",
            area="Audio",
            severity=Severity.warning,
            detected=f"Audio device(s) with a non-OK status: {names}.",
            likely_cause="A faulty or outdated audio driver.",
            resolution_steps=[
                "Device Manager > Sound, video and game controllers > the device > Update driver.",
                "If recent, roll back the driver (Driver tab > Roll Back Driver).",
                "Uninstall the device and Scan for hardware changes to reinstall.",
                "Set the correct default playback device: Settings > System > Sound.",
            ],
            ask_ai_prompt="My audio device shows a driver problem. How do I fix sound?",
        ))

    return ProbeOutcome(
        result=ProbeResult(domain=DOMAIN, title=TITLE, available=True, checks=checks),
        findings=findings,
    )
