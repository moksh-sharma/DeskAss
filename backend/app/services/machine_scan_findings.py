"""Turn a comprehensive machine scan into issue-focused probes and findings.

The full machine scan always runs, but what we surface to the user and LLM is
filtered to the reported problem (e.g. microphone only — not CPU, firewall, or
unrelated stopped services).
"""
from __future__ import annotations

import os
import re
from typing import Any

from app.models.schemas import (
    IssueProfile,
    ProbeCheck,
    ProbeResult,
    Severity,
    TroubleshooterFinding,
)
from app.services.probes.base import as_list, get_service, ps_json, run_powershell
from app.services.scanners.physical_device import (
    asks_physical_connection,
    is_virtual_audio,
    is_virtual_camera,
)

_CAMERA_CLASSES = {"Camera", "Image"}
_AUDIO_DEVICE_PATTERNS = re.compile(
    r"audio|sound|speaker|microphone|mic|realtek|conexant|high definition audio|headset",
    re.I,
)
_MIC_NAME_PATTERNS = re.compile(r"microphone|mic array|headset|input|capture", re.I)

# Services that matter for audio — NOT generic "critical" services like NLA.
_AUDIO_SERVICES = {
    "Audiosrv": "Windows Audio",
    "AudioEndpointBuilder": "Windows Audio Endpoint Builder",
}


def _sev_from_score(score: int) -> Severity:
    if score >= 80:
        return Severity.healthy
    if score >= 50:
        return Severity.warning
    return Severity.critical


def _is_mic_issue(message: str, profile: IssueProfile) -> bool:
    text = (message or "").lower()
    if re.search(r"\b(mic|microphone)\b", text):
        return True
    if "no_sound" in profile.symptoms and not re.search(r"\b(speaker|speakers|playback)\b", text):
        return "mic" in text or "microphone" in text
    return False


def _is_speaker_issue(message: str, profile: IssueProfile) -> bool:
    text = (message or "").lower()
    if _is_mic_issue(message, profile):
        return False
    return bool(
        profile.domains and "audio" in profile.domains
        and re.search(r"\b(sound|speaker|speakers|audio|volume|playback|hear)\b", text)
    )


def _privacy_access(kind: str) -> str | None:
    """kind: 'webcam' or 'microphone'."""
    ok, out = run_powershell(
        f"$paths = @("
        f"'HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\CapabilityAccessManager\\ConsentStore\\{kind}',"
        f"'HKCU:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\CapabilityAccessManager\\ConsentStore\\{kind}'"
        f"); "
        "foreach ($p in $paths) { "
        "  if (Test-Path $p) { "
        "    (Get-ItemProperty -Path $p -Name Value -ErrorAction SilentlyContinue).Value; break "
        "  } "
        "}"
    )
    return out.strip() if ok and out.strip() else None


def _camera_devices(hw: dict) -> list[dict]:
    devices = (hw.get("devices") or {}).get("all") or []
    return [
        d for d in devices
        if d.get("class") in _CAMERA_CLASSES
        or re.search(r"camera|webcam|integrated cam", (d.get("name") or ""), re.I)
    ]


def _audio_devices(hw: dict) -> list[dict]:
    devices = (hw.get("devices") or {}).get("all") or []
    return [d for d in devices if _AUDIO_DEVICE_PATTERNS.search(
        f"{d.get('name', '')} {d.get('class', '')} {d.get('category', '')}"
    )]


def _mic_endpoints() -> list[dict]:
    return as_list(ps_json(
        "Get-PnpDevice -Class AudioEndpoint -PresentOnly -ErrorAction SilentlyContinue | "
        "Select-Object FriendlyName,Status,Problem | ConvertTo-Json -Compress"
    ))


def _issue_label(profile: IssueProfile, message: str) -> str:
    if "webcam" in profile.domains:
        return "webcam / camera"
    if "audio" in profile.domains:
        return "microphone" if _is_mic_issue(message, profile) else "audio / sound"
    if profile.primary_domain:
        return profile.primary_domain.replace("_", " ")
    return "your reported issue"


def _no_fault_finding(profile: IssueProfile, message: str, subsystem: str) -> TroubleshooterFinding:
    """Honest result when the full scan found no fault in the relevant subsystem."""
    label = _issue_label(profile, message)
    if subsystem == "microphone":
        steps = [
            "Settings > Privacy & security > Microphone: turn on access and allow your app.",
            "Settings > System > Sound > Input: select the correct microphone and test the input meter while speaking.",
            "Right-click the speaker icon > Sound settings > Input volume — ensure the mic is not muted.",
            "Device Manager > Audio inputs and outputs: update or reinstall the microphone driver.",
            "Close other apps using the mic (Teams, Zoom, Discord) and test in Windows Voice Recorder.",
        ]
        cause = (
            "The full system scan found no driver or device error for your microphone. "
            "The issue is likely app permissions, the wrong input device selected, or the mic muted in software."
        )
    elif subsystem == "webcam":
        steps = [
            "Settings > Privacy & security > Camera: allow access for your app.",
            "Test in the built-in Camera app; close Teams/Zoom/OBS if they may hold the camera.",
            "Device Manager > Cameras: update the driver if video is still black.",
        ]
        cause = (
            "No camera hardware fault was detected. Check privacy settings, physical privacy shutter, "
            "and whether another app is using the camera."
        )
    else:
        steps = [
            f"Re-test {label} to confirm the symptom.",
            "Restart the PC and try again.",
            f"If it persists, note when {label} fails and which app is involved.",
        ]
        cause = (
            f"The full system scan found no clear fault in components related to {label}. "
            "The problem may be app-specific, intermittent, or external to this PC."
        )
    return TroubleshooterFinding(
        id=f"no_fault_{subsystem}",
        title=f"No {subsystem.replace('_', ' ').title()} Fault Detected",
        area=subsystem.replace("_", " ").title(),
        severity=Severity.info,
        detected=f"Full hardware and software scan found no error in {label} drivers, devices, or services.",
        likely_cause=cause,
        resolution_steps=steps,
        ask_ai_prompt=f"My {label} isn't working but the system scan looks OK. What should I check?",
    )


# ------------------------------------------------------------------ #
#  Issue-specific findings (only these are returned — no generic dump)
# ------------------------------------------------------------------ #

def _webcam_findings(hw: dict) -> list[TroubleshooterFinding]:
    findings: list[TroubleshooterFinding] = []
    physical = _physical_cameras(hw)
    virtual = _virtual_cameras(hw)
    # Fallback to hardware scanner device list when external inventory is empty.
    if not physical and not virtual:
        physical = [
            c for c in _camera_devices(hw)
            if not is_virtual_camera(c.get("name") or "")
        ]
    broken = [c for c in physical if not c.get("connected", c.get("working"))]

    access = _privacy_access("webcam")
    if access and access.lower() != "allow":
        findings.append(TroubleshooterFinding(
            id="webcam_privacy_denied",
            title="Camera Access Disabled in Windows",
            area="Webcam",
            severity=Severity.warning,
            detected="Windows reports camera access is denied at the system level.",
            likely_cause="Camera privacy settings block apps from using the webcam.",
            resolution_steps=[
                "Settings > Privacy & security > Camera > turn on 'Camera access'.",
                "Enable access for the app you are using.",
                "Check for a physical privacy shutter or Fn key that disables the camera.",
            ],
            ask_ai_prompt="Windows camera access is denied. How do I enable my webcam?",
        ))

    if not physical:
        if virtual:
            examples = ", ".join(c.get("name", "camera") for c in virtual[:3])
            findings.append(TroubleshooterFinding(
                id="webcam_not_connected",
                title="No Physical Camera Connected",
                area="Webcam",
                severity=Severity.warning,
                detected=f"No physical camera is connected. Windows only lists virtual camera(s): "
                f"{examples}. These are software devices, not hardware.",
                likely_cause="No webcam hardware is attached. Virtual cameras from apps like OBS or "
                "ManyCam can appear even when no physical camera is present.",
                resolution_steps=[
                    "Plug in an external USB webcam or enable a built-in camera in Device Manager.",
                    "Device Manager > Cameras: enable or reinstall the physical camera driver.",
                    "Test in the built-in Camera app after connecting hardware.",
                ],
                ask_ai_prompt="I don't have a physical webcam connected but Windows shows a camera. "
                "How do I connect a real one?",
            ))
        else:
            findings.append(TroubleshooterFinding(
                id="webcam_not_detected",
                title="No Camera Detected",
                area="Webcam",
                severity=Severity.critical,
                detected="The scan found no camera or imaging device on this PC.",
                likely_cause="Driver missing, device disabled, or external webcam unplugged.",
                resolution_steps=[
                    "Reconnect external webcams; try another USB port.",
                    "Device Manager > Cameras: enable or reinstall the driver.",
                    "Test in the built-in Camera app.",
                ],
                ask_ai_prompt="Windows can't find my camera. How do I fix it?",
            ))
    elif broken:
        top = broken[0]
        findings.append(TroubleshooterFinding(
            id="webcam_device_error",
            title="Camera Driver or Device Error",
            area="Webcam",
            severity=Severity.warning,
            detected=f"Camera error: {top.get('name')} (status {top.get('status')}).",
            likely_cause="Driver problem, disabled device, or another app holding the camera.",
            resolution_steps=[
                "Close apps using the camera (Teams, Zoom, OBS).",
                "Device Manager > Cameras > Update driver or uninstall and rescan.",
                "Settings > Privacy & security > Camera: allow access for your app.",
            ],
            ask_ai_prompt="My webcam has a driver error. How do I fix it?",
        ))
    elif not findings:
        ready = [c for c in physical if c.get("connected", c.get("working"))]
        listing = ", ".join(c.get("name", "Camera") for c in ready[:3])
        virtual_note = ""
        if virtual:
            virtual_note = (
                f" ({len(virtual)} virtual camera(s) also listed — e.g. {virtual[0].get('name')} — "
                "not hardware.)"
            )
        findings.append(TroubleshooterFinding(
            id="no_fault_webcam",
            title="Physical Camera Is Connected",
            area="Webcam",
            severity=Severity.info,
            detected=f"{len(ready)} physical camera(s) connected: {listing}.{virtual_note}",
            likely_cause="A physical camera is present and reporting a normal status. "
            "If video fails in an app, check privacy settings or whether another app is using the camera.",
            resolution_steps=[
                "Settings > Privacy & security > Camera: allow access for your app.",
                "Close Teams/Zoom/OBS if they may hold the camera.",
                "Test in the built-in Camera app.",
            ],
            ask_ai_prompt="My camera is connected but an app can't use it. What should I check?",
        ))
    return findings


def _audio_findings(hw: dict, message: str, profile: IssueProfile) -> list[TroubleshooterFinding]:
    findings: list[TroubleshooterFinding] = []
    mic_focus = _is_mic_issue(message, profile)

    for svc_name, label in _AUDIO_SERVICES.items():
        svc = get_service(svc_name)
        if not svc:
            continue
        running = str(svc.get("Status", "")).lower() == "running"
        if not running:
            findings.append(TroubleshooterFinding(
                id=f"audio_service_{svc_name.lower()}",
                title=f"{label} Not Running",
                area="Audio",
                severity=Severity.warning,
                detected=f"The {label} service ({svc_name}) is {svc.get('Status', 'stopped')}.",
                likely_cause="Without this service, Windows audio input/output will not work.",
                resolution_steps=[
                    f"Open Services (`services.msc`) > '{label}'.",
                    "Set Startup type to Automatic and click Start.",
                    "Also ensure 'Windows Audio Endpoint Builder' is running.",
                    "Restart the PC if the microphone or speakers still fail.",
                ],
                ask_ai_prompt=f"My {label} service is stopped. How do I fix audio?",
            ))

    if mic_focus:
        access = _privacy_access("microphone")
        if access and access.lower() != "allow":
            findings.append(TroubleshooterFinding(
                id="mic_privacy_denied",
                title="Microphone Access Disabled in Windows",
                area="Microphone",
                severity=Severity.warning,
                detected="Windows reports microphone access is denied at the system level.",
                likely_cause="Microphone privacy settings block apps from using your mic.",
                resolution_steps=[
                    "Settings > Privacy & security > Microphone > turn on 'Microphone access'.",
                    "Enable 'Let apps access your microphone' and allow your meeting/browser app.",
                    "Retry in the app after changing privacy settings.",
                ],
                ask_ai_prompt="Windows microphone access is denied. How do I enable my mic?",
            ))

        endpoints = _mic_endpoints()
        mic_eps = [e for e in endpoints if _MIC_NAME_PATTERNS.search(e.get("FriendlyName") or "")]
        physical_mics = _physical_audio_inputs(hw)
        virtual_mics = [d for d in _ext_audio_inputs(hw) if d.get("is_virtual")]
        if not mic_eps and endpoints:
            mic_eps = endpoints
        broken_mics = [
            e for e in mic_eps
            if str(e.get("Status", "")).lower() not in ("ok", "")
        ]
        if not physical_mics:
            if virtual_mics:
                examples = ", ".join(d.get("name", "mic") for d in virtual_mics[:3])
                findings.append(TroubleshooterFinding(
                    id="mic_not_connected",
                    title="No Physical Microphone Connected",
                    area="Microphone",
                    severity=Severity.warning,
                    detected=f"No physical microphone is connected. Windows only lists virtual input(s): "
                    f"{examples}.",
                    likely_cause="No mic hardware is attached. Virtual audio devices from apps like Voicemeeter "
                    "or Stereo Mix are software, not a physical microphone.",
                    resolution_steps=[
                        "Plug in a USB or headset microphone, or enable a built-in mic in Device Manager.",
                        "Settings > System > Sound > Input: check a physical device appears.",
                        "Device Manager > Audio inputs and outputs: enable/install the microphone.",
                    ],
                    ask_ai_prompt="I don't have a physical microphone connected. How do I add one?",
                ))
            else:
                findings.append(TroubleshooterFinding(
                    id="mic_not_detected",
                    title="No Microphone Input Detected",
                    area="Microphone",
                    severity=Severity.critical,
                    detected="Windows reports no microphone audio input endpoint.",
                    likely_cause="Mic driver missing, device disabled, or external mic unplugged.",
                    resolution_steps=[
                        "Settings > System > Sound > Input: check a device is listed.",
                        "Device Manager > Audio inputs and outputs: enable/install the microphone.",
                        "Reconnect USB/headset mic; try another port.",
                    ],
                    ask_ai_prompt="Windows can't see my microphone. How do I fix it?",
                ))
        elif broken_mics:
            top = broken_mics[0]
            findings.append(TroubleshooterFinding(
                id="mic_endpoint_error",
                title="Microphone Device Error",
                area="Microphone",
                severity=Severity.warning,
                detected=f"Microphone endpoint problem: {top.get('FriendlyName')} ({top.get('Status')}).",
                likely_cause="Driver fault or disabled input device.",
                resolution_steps=[
                    "Device Manager > Audio inputs and outputs > update or reinstall the mic.",
                    "Settings > System > Sound > Input: pick the correct microphone.",
                    "Restart the PC and test in Voice Recorder.",
                ],
                ask_ai_prompt="My microphone endpoint shows an error. How do I fix it?",
            ))

    elif _is_speaker_issue(message, profile):
        physical_spk = _physical_audio_outputs(hw)
        virtual_spk = [d for d in _ext_audio_outputs(hw) if d.get("is_virtual")]
        if not physical_spk:
            if virtual_spk:
                examples = ", ".join(d.get("name", "speaker") for d in virtual_spk[:3])
                findings.append(TroubleshooterFinding(
                    id="speaker_not_connected",
                    title="No Physical Speaker or Headphone Connected",
                    area="Audio",
                    severity=Severity.warning,
                    detected=f"No physical audio output device is connected. Only virtual output(s): {examples}.",
                    likely_cause="No speakers or headphones are attached. Virtual audio devices are software, "
                    "not physical speakers.",
                    resolution_steps=[
                        "Plug in speakers, headphones, or a headset.",
                        "Settings > System > Sound > Output: select the physical device.",
                        "Device Manager > Audio outputs: enable or reinstall the driver.",
                    ],
                    ask_ai_prompt="No physical speakers are connected. How do I set up audio output?",
                ))
            else:
                findings.append(TroubleshooterFinding(
                    id="speaker_not_detected",
                    title="No Audio Output Device Detected",
                    area="Audio",
                    severity=Severity.warning,
                    detected="Windows reports no physical audio output endpoint.",
                    likely_cause="Audio driver missing, device disabled, or speakers/headphones unplugged.",
                    resolution_steps=[
                        "Plug in speakers or headphones.",
                        "Settings > System > Sound > Output: check a device is listed.",
                        "Device Manager > Sound, video and game controllers: update the driver.",
                    ],
                    ask_ai_prompt="Windows can't see my speakers. How do I fix audio output?",
                ))

    audio_devs = _audio_devices(hw)
    broken_audio = [
        d for d in audio_devs
        if not d.get("working") and not is_virtual_audio(d.get("name") or "")
    ]
    if broken_audio:
        top = broken_audio[0]
        findings.append(TroubleshooterFinding(
            id="audio_device_error",
            title="Audio Device Driver Error",
            area="Audio",
            severity=Severity.warning,
            detected=f"Audio device error: {top.get('name')} (status {top.get('status')}).",
            likely_cause="Faulty or outdated audio driver.",
            resolution_steps=[
                "Device Manager > Sound, video and game controllers > Update driver.",
                "Roll back the driver if the problem started after an update.",
                "Uninstall the device and Scan for hardware changes.",
            ],
            ask_ai_prompt="My audio device has a driver error. How do I fix it?",
        ))

    if not findings:
        subsystem = "microphone" if mic_focus else "audio"
        if mic_focus and _physical_audio_inputs(hw):
            ready = [d for d in _physical_audio_inputs(hw) if d.get("working")]
            listing = ", ".join(d.get("name", "Microphone") for d in ready[:3])
            findings.append(TroubleshooterFinding(
                id="no_fault_microphone",
                title="Physical Microphone Is Connected",
                area="Microphone",
                severity=Severity.info,
                detected=f"{len(ready)} physical microphone(s) connected: {listing}.",
                likely_cause="A physical microphone is present. If apps can't hear you, check privacy "
                "settings, mute, or the wrong input device selected.",
                resolution_steps=[
                    "Settings > Privacy & security > Microphone: allow access for your app.",
                    "Settings > System > Sound > Input: select the correct mic and test the meter.",
                    "Close other apps that may be using the microphone.",
                ],
                ask_ai_prompt="My microphone is connected but an app can't hear me. What should I check?",
            ))
        elif _is_speaker_issue(message, profile) and _physical_audio_outputs(hw):
            ready = [d for d in _physical_audio_outputs(hw) if d.get("working")]
            listing = ", ".join(d.get("name", "Speaker") for d in ready[:3])
            findings.append(TroubleshooterFinding(
                id="no_fault_speaker",
                title="Physical Audio Output Is Connected",
                area="Audio",
                severity=Severity.info,
                detected=f"{len(ready)} physical output device(s): {listing}.",
                likely_cause="Physical speakers or headphones are connected. If there's no sound, "
                "check volume, mute, and the selected output device.",
                resolution_steps=[
                    "Settings > System > Sound > Output: select the correct device.",
                    "Check volume and mute in the taskbar and in your app.",
                    "Try unplugging and replugging headphones or speakers.",
                ],
                ask_ai_prompt="My speakers are connected but I hear no sound. What should I check?",
            ))
        else:
            findings.append(_no_fault_finding(profile, message, subsystem))
    return findings


def _device_findings_for_domain(hw: dict, domain: str, patterns: list[str]) -> list[TroubleshooterFinding]:
    problems = (hw.get("devices") or {}).get("problem_devices") or []
    matched = [
        d for d in problems
        if any(re.search(p, f"{d.get('name', '')} {d.get('class', '')} {d.get('category', '')}", re.I) for p in patterns)
    ]
    if not matched:
        return []
    top = matched[0]
    return [TroubleshooterFinding(
        id=f"{domain}_device_error",
        title=f"{top.get('category') or domain.title()} Device Error",
        area=domain.title(),
        severity=Severity.warning,
        detected=f"{top.get('name')} reports status {top.get('status')} (problem code {top.get('problem_code')}).",
        likely_cause="Driver fault, disconnected peripheral, or disabled device.",
        resolution_steps=[
            f"Device Manager > {top.get('category') or 'Devices'}: update or reinstall the driver.",
            "Unplug/replug the device; try another port if external.",
            "Restart the PC and re-test.",
        ],
        ask_ai_prompt=f"My {domain} device shows an error. How do I fix it?",
    )]


# ------------------------------------------------------------------ #
#  External-hardware findings (connection state, not just driver errors)
# ------------------------------------------------------------------ #

def _external(hw: dict) -> dict:
    """The external-device inventory section of the scan (may be empty)."""
    return (hw.get("external_devices") or {}) if isinstance(hw, dict) else {}


def _ext_cameras(hw: dict) -> list[dict]:
    section = _external(hw).get("cameras") or {}
    return section.get("cameras") or []


def _physical_cameras(hw: dict) -> list[dict]:
    return [c for c in _ext_cameras(hw) if c.get("is_physical")]


def _virtual_cameras(hw: dict) -> list[dict]:
    return [c for c in _ext_cameras(hw) if c.get("is_virtual")]


def _ext_audio_inputs(hw: dict) -> list[dict]:
    return (_external(hw).get("audio") or {}).get("input_devices") or []


def _ext_audio_outputs(hw: dict) -> list[dict]:
    return (_external(hw).get("audio") or {}).get("output_devices") or []


def _physical_audio_inputs(hw: dict) -> list[dict]:
    return [d for d in _ext_audio_inputs(hw) if d.get("is_physical")]


def _physical_audio_outputs(hw: dict) -> list[dict]:
    return [d for d in _ext_audio_outputs(hw) if d.get("is_physical")]


def _usb_peripherals(hw: dict) -> list[dict]:
    return [
        d for d in ((_external(hw).get("usb") or {}).get("devices") or [])
        if d.get("is_peripheral")
    ]


def _peripherals_matching(hw: dict, pattern: re.Pattern[str]) -> list[dict]:
    return [
        d for d in _usb_peripherals(hw)
        if pattern.search(f"{d.get('name', '')} {d.get('type', '')}")
    ]


def _printer_findings(hw: dict) -> list[TroubleshooterFinding]:
    ext = _external(hw)
    section = ext.get("printers") or {}
    printers = section.get("printers") or []
    physical = [p for p in printers if p.get("is_physical")]
    virtual = [p for p in printers if p.get("is_virtual")]
    pnp_usb = section.get("pnp_usb_printers") or []
    findings: list[TroubleshooterFinding] = []

    if not physical:
        if pnp_usb:
            names = ", ".join(p.get("name", "printer") for p in pnp_usb[:3])
            findings.append(TroubleshooterFinding(
                id="printer_hardware_unconfigured",
                title="Printer Hardware Detected but Not Set Up",
                area="Printers",
                severity=Severity.warning,
                detected=f"USB printer hardware is connected ({names}) but no physical printer "
                "queue is installed in Windows.",
                likely_cause="The device is plugged in but Windows has no driver/queue for it yet.",
                resolution_steps=[
                    "Settings > Bluetooth & devices > Printers & scanners > Add device.",
                    "Install the printer driver from the manufacturer's website if auto-detect fails.",
                    "Try a different USB port or cable.",
                ],
                ask_ai_prompt="Windows sees my USB printer hardware but I can't print. How do I install it?",
            ))
        elif virtual:
            examples = ", ".join(p.get("name", "printer") for p in virtual[:3])
            findings.append(TroubleshooterFinding(
                id="printer_not_connected",
                title="No Physical Printer Connected",
                area="Printers",
                severity=Severity.warning,
                detected=f"No physical printer is connected. Windows only lists {len(virtual)} "
                f"software printer(s): {examples}. These are not hardware devices.",
                likely_cause="No printer is plugged in (USB) or on the network. Windows still shows "
                "built-in virtual printers like Print to PDF and OneNote even when no hardware is attached.",
                resolution_steps=[
                    "Turn the printer on and connect it (USB cable seated, or on the same Wi-Fi/network).",
                    "Settings > Bluetooth & devices > Printers & scanners > Add device.",
                    "For a network printer, install it by its IP address if auto-detect fails.",
                    "Install the printer driver from the maker's website if Windows can't find one.",
                ],
                ask_ai_prompt="I don't have a physical printer connected but Windows shows printers. "
                "How do I add a real printer?",
            ))
        else:
            findings.append(TroubleshooterFinding(
                id="printer_not_connected",
                title="No Printer Is Connected",
                area="Printers",
                severity=Severity.warning,
                detected="The scan found no printer installed or connected to this PC.",
                likely_cause="The printer is powered off, unplugged (USB), not on the same network, "
                "or its driver was never installed.",
                resolution_steps=[
                    "Turn the printer on and connect it (USB cable seated, or on the same Wi-Fi/network).",
                    "Settings > Bluetooth & devices > Printers & scanners > Add device.",
                    "For a network printer, install it by its IP address if auto-detect fails.",
                    "Install the printer driver from the maker's website if Windows can't find one.",
                ],
                ask_ai_prompt="Windows doesn't show any printer. How do I add and connect my printer?",
            ))
        return findings

    if section.get("spooler_running") is False:
        findings.append(TroubleshooterFinding(
            id="printer_spooler_stopped",
            title="Print Spooler Is Not Running",
            area="Printers",
            severity=Severity.critical,
            detected="The Print Spooler service is stopped, so no printing is possible.",
            likely_cause="The spooler crashed (often on a stuck job) or was disabled.",
            resolution_steps=[
                "Open Services (services.msc) > 'Print Spooler'.",
                "Set Startup type to Automatic and click Start.",
                "If it won't stay running, stop it, delete files in "
                "C:\\Windows\\System32\\spool\\PRINTERS, then start it again.",
            ],
            ask_ai_prompt="My Print Spooler keeps stopping and I can't print. How do I fix it?",
        ))

    offline = [p for p in physical if p.get("health") == "Offline"]
    if offline:
        names = ", ".join(p.get("name", "printer") for p in offline[:3])
        findings.append(TroubleshooterFinding(
            id="printer_offline",
            title="Printer Shows Offline",
            area="Printers",
            severity=Severity.warning,
            detected=f"Printer(s) marked offline: {names}.",
            likely_cause="The PC can't reach the printer (powered off, network/USB issue) "
            "or 'Use Printer Offline' is set.",
            resolution_steps=[
                "Confirm the printer is powered on and connected (USB seated or on the network).",
                "Settings > Printers & scanners > the printer > uncheck 'Use printer offline'.",
                "For network printers, verify the printer's IP is reachable (ping it).",
                "Restart the Print Spooler service and retry.",
            ],
            ask_ai_prompt="My printer shows offline even though it's on. How do I bring it back online?",
        ))

    if not findings:
        ready = [p for p in physical if p.get("health") in ("Ready", "Idle / Ready")]
        default = next((p for p in physical if p.get("is_default")), physical[0])
        listing = "; ".join(
            f"{p.get('name')} ({p.get('connection')}, {p.get('health')})" for p in physical[:4]
        )
        virtual_note = ""
        if virtual:
            virtual_note = (
                f" ({len(virtual)} software printer(s) also installed — e.g. "
                f"{virtual[0].get('name')} — these are not physical devices.)"
            )
        findings.append(TroubleshooterFinding(
            id="no_fault_printer",
            title="Physical Printer Is Connected and Ready",
            area="Printers",
            severity=Severity.info,
            detected=f"{len(physical)} physical printer(s); "
            f"{len(ready)} ready. Default: {default.get('name')}. {listing}.{virtual_note}",
            likely_cause="A physical printer is connected and reporting a ready/normal status. "
            "If a specific print job fails, the issue is likely the app, paper/ink, or the document.",
            resolution_steps=[
                f"Send a test page: Settings > Printers & scanners > {default.get('name')} > "
                "Manage > Print test page.",
                "Check paper, ink/toner, and that the correct printer is selected in the app.",
                "Clear any stuck jobs in the print queue and retry.",
            ],
            ask_ai_prompt="My printer is connected but a specific document won't print. What should I check?",
        ))
    return findings


def _display_external_findings(hw: dict, message: str) -> list[TroubleshooterFinding]:
    ext = _external(hw)
    section = ext.get("monitors") or {}
    monitors = section.get("monitors") or []
    external = [m for m in monitors if m.get("is_external")]
    internal = [m for m in monitors if m.get("is_internal")]
    findings: list[TroubleshooterFinding] = []
    wants_external = any(
        w in (message or "").lower()
        for w in ("external", "second", "hdmi", "displayport", "monitor", "no signal", "extend")
    ) or asks_physical_connection(message)

    if wants_external and not external:
        internal_note = ""
        if internal:
            internal_note = (
                f" Only the built-in display ({internal[0].get('model') or 'laptop screen'}) is detected."
            )
        findings.append(TroubleshooterFinding(
            id="display_external_not_connected",
            title="No External Monitor Connected",
            area="Display",
            severity=Severity.warning,
            detected=f"No external monitor is physically connected.{internal_note}",
            likely_cause="The second screen is unplugged, the cable/input is wrong, or the dock isn't seated.",
            resolution_steps=[
                "Connect the monitor via HDMI, DisplayPort, or USB-C.",
                "Press Win+P and choose 'Extend' or 'Duplicate'.",
                "Settings > System > Display > Multiple displays > Detect.",
                "Try a different cable/port and check the monitor's input source.",
            ],
            ask_ai_prompt="My external monitor isn't connected or detected. How do I hook it up?",
        ))
    elif external:
        listing = "; ".join(
            f"{m.get('model') or 'Display'}"
            + (f" via {m.get('connection_type')}" if m.get("connection_type") else "")
            + (f" @ {m.get('resolution')}" if m.get("resolution") else "")
            for m in external[:4]
        )
        findings.append(TroubleshooterFinding(
            id="no_fault_display",
            title=f"{len(external)} External Display(s) Connected",
            area="Display",
            severity=Severity.info,
            detected=f"Connected external displays: {listing}.",
            likely_cause="External monitor(s) are physically connected and detected. "
            "Picture issues are likely resolution, refresh-rate, scaling, or cable quality.",
            resolution_steps=[
                "Settings > System > Display: set the recommended resolution and scale.",
                "Advanced display: pick the highest refresh rate the monitor supports.",
                "Swap the cable if you see flicker or artefacts.",
            ],
            ask_ai_prompt="My display is connected but the picture isn't right. How do I tune it?",
        ))
    return findings


def _bluetooth_external_findings(hw: dict) -> list[TroubleshooterFinding]:
    ext = _external(hw)
    bt = ext.get("bluetooth") or {}
    devices = bt.get("devices") or []
    findings: list[TroubleshooterFinding] = []

    if bt.get("adapter_present") is False:
        return findings

    connected = [d for d in devices if d.get("connected")]
    paired_not_connected = [d for d in devices if not d.get("connected")]

    if not connected:
        if paired_not_connected:
            names = ", ".join(d.get("name", "device") for d in paired_not_connected[:4])
            findings.append(TroubleshooterFinding(
                id="bluetooth_not_connected",
                title="No Bluetooth Device Currently Connected",
                area="Bluetooth",
                severity=Severity.warning,
                detected=f"{len(paired_not_connected)} Bluetooth device(s) are paired but not connected "
                f"right now: {names}.",
                likely_cause="Paired devices are remembered but not actively connected. "
                "The device may be off, out of range, or low on battery.",
                resolution_steps=[
                    "Turn the device on and bring it within range.",
                    "Settings > Bluetooth & devices: select the device and click Connect.",
                    "Remove and re-pair if it won't reconnect.",
                ],
                ask_ai_prompt="My Bluetooth device is paired but not connected. How do I connect it?",
            ))
        else:
            findings.append(TroubleshooterFinding(
                id="bluetooth_none_paired",
                title="No Bluetooth Devices Paired",
                area="Bluetooth",
                severity=Severity.warning,
                detected="The Bluetooth adapter is present but no devices are paired or connected.",
                likely_cause="No Bluetooth peripheral has been paired with this PC yet.",
                resolution_steps=[
                    "Put your device in pairing mode.",
                    "Settings > Bluetooth & devices > Add device > Bluetooth.",
                    "Follow the on-screen pairing steps.",
                ],
                ask_ai_prompt="How do I pair a Bluetooth device with my PC?",
            ))
    else:
        listing = "; ".join(
            f"{d.get('name')} ({d.get('device_type', 'device')})"
            for d in connected[:5]
        )
        findings.append(TroubleshooterFinding(
            id="no_fault_bluetooth",
            title=f"{len(connected)} Bluetooth Device(s) Connected",
            area="Bluetooth",
            severity=Severity.info,
            detected=f"{bt.get('paired_count')} paired, {len(connected)} connected now: {listing}.",
            likely_cause="Bluetooth device(s) are physically connected and active.",
            resolution_steps=[
                "If audio, select the device in Settings > System > Sound.",
                "Keep the device charged and within range.",
                "Re-pair if the connection drops frequently.",
            ],
            ask_ai_prompt="My Bluetooth device is connected but not working right. What should I check?",
        ))
    return findings


def _usb_external_findings(hw: dict) -> list[TroubleshooterFinding]:
    ext = _external(hw)
    usb = ext.get("usb") or {}
    problems = usb.get("problem_devices") or []
    findings: list[TroubleshooterFinding] = []
    storage = (ext.get("external_storage") or {}).get("devices") or []
    bad_storage = [s for s in storage if s.get("health") != "Connected"]

    if problems:
        top = problems[0]
        findings.append(TroubleshooterFinding(
            id="usb_device_error",
            title="USB Device Not Working Correctly",
            area="USB",
            severity=Severity.warning,
            detected=f"{len(problems)} USB device(s) report issues (e.g. {top.get('name')}: {top.get('health')}).",
            likely_cause="A driver failed to load, the device is faulty, or USB power management "
            "is turning the port off.",
            resolution_steps=[
                "Unplug and replug the device; try a different USB port.",
                "Device Manager: right-click the device > Update driver.",
                "Disable USB selective suspend: Control Panel > Power Options > USB settings.",
                "Test the device on another PC to rule out hardware failure.",
            ],
            ask_ai_prompt="A USB device shows an error / 'not recognized'. How do I get it working?",
        ))
    if bad_storage:
        s = bad_storage[0]
        findings.append(TroubleshooterFinding(
            id="external_storage_issue",
            title="External Drive Problem",
            area="External Storage",
            severity=Severity.warning,
            detected=f"External drive '{s.get('name')}' reports {s.get('health')}.",
            likely_cause="A loose connection, failing drive, or a file-system error.",
            resolution_steps=[
                "Reconnect the drive and try a different USB port/cable.",
                "Run CHKDSK on the drive letter to repair file-system errors.",
                "Back up important data immediately if the drive reports a health issue.",
            ],
            ask_ai_prompt="My external drive isn't working properly. How do I recover it?",
        ))

    if not findings:
        peripherals = _usb_peripherals(hw)
        count = usb.get("peripheral_count") or len(peripherals)
        if count == 0:
            findings.append(TroubleshooterFinding(
                id="usb_not_connected",
                title="No USB Peripherals Connected",
                area="USB",
                severity=Severity.warning,
                detected="No USB peripherals (drives, mice, keyboards, etc.) are physically connected.",
                likely_cause="Nothing is plugged into a USB port, or the device isn't drawing power/detected.",
                resolution_steps=[
                    "Plug the device into a USB port (try a rear port on a desktop).",
                    "Device Manager > Action > Scan for hardware changes.",
                    "Try a different cable or USB port.",
                ],
                ask_ai_prompt="My USB device isn't connected or detected. How do I fix it?",
            ))
        else:
            types = ", ".join(
                f"{n}x {t}" for t, n in (usb.get("type_counts") or {}).items()
            ) or "none"
            findings.append(TroubleshooterFinding(
                id="no_fault_usb",
                title=f"{count} USB Peripheral(s) Connected, No Errors",
                area="USB",
                severity=Severity.info,
                detected=f"Connected USB peripherals: {types}.",
                likely_cause="All connected USB peripherals report a healthy status.",
                resolution_steps=[
                    "Replug the missing device and try another USB port (prefer a rear port).",
                    "Device Manager > Action > Scan for hardware changes.",
                    "Install the device's driver from the maker if Windows doesn't detect it.",
                ],
                ask_ai_prompt="A USB device isn't showing up even though others work. What should I check?",
            ))
    return findings


_MOUSE_USB_RE = re.compile(r"mouse|touchpad|trackpad|pointing", re.I)
_KEYBOARD_USB_RE = re.compile(r"keyboard", re.I)
_DEVICE_NOT_WORKING_RE = re.compile(
    r"not working|won'?t work|wont work|doesn'?t work|doesnt work|"
    r"broken|dead|stuck|not responding|unresponsive|freeze|no cursor",
    re.I,
)


def _device_not_working(message: str) -> bool:
    return bool(_DEVICE_NOT_WORKING_RE.search(message or ""))


def _hw_pointing_devices(hw: dict) -> list[dict]:
    return [
        d for d in ((hw.get("devices") or {}).get("all") or [])
        if d.get("class") in ("Mouse", "HIDClass")
        and re.search(r"mouse|touchpad|trackpad|pointing|precision", d.get("name", ""), re.I)
        and d.get("working")
    ]


def _hw_keyboards(hw: dict) -> list[dict]:
    return [
        d for d in ((hw.get("devices") or {}).get("all") or [])
        if d.get("class") == "Keyboard" and d.get("working")
    ]


def _mouse_findings(hw: dict, message: str) -> list[TroubleshooterFinding]:
    usb_mice = _peripherals_matching(hw, _MOUSE_USB_RE)
    bt = (_external(hw).get("bluetooth") or {}).get("devices") or []
    bt_mice = [
        d for d in bt
        if d.get("connected") and re.search(r"mouse|trackpad|touchpad", d.get("name", ""), re.I)
    ]
    built_in = _hw_pointing_devices(hw)
    connected = usb_mice + bt_mice + built_in
    findings: list[TroubleshooterFinding] = []
    if not connected:
        findings.append(TroubleshooterFinding(
            id="mouse_not_connected",
            title="No Mouse or Pointing Device Connected",
            area="Mouse",
            severity=Severity.warning,
            detected="No physical mouse, touchpad, or pointing device is connected.",
            likely_cause="A USB mouse is unplugged, or a Bluetooth mouse is off/not paired.",
            resolution_steps=[
                "Plug in a USB mouse or turn on your wireless mouse.",
                "For Bluetooth mice: Settings > Bluetooth & devices > connect the mouse.",
                "Device Manager > Mice and other pointing devices: enable the device.",
            ],
            ask_ai_prompt="My mouse isn't connected. How do I get Windows to detect it?",
        ))
    elif _device_not_working(message):
        names = ", ".join(
            (d.get("name") or "Mouse")
            for d in (usb_mice[:2] + bt_mice[:2] + built_in[:2])
        )
        findings.append(TroubleshooterFinding(
            id="mouse_not_working",
            title="Mouse Connected but Not Working",
            area="Mouse",
            severity=Severity.warning,
            detected=f"Pointing device detected ({names}) but you reported the mouse or touchpad is not working.",
            likely_cause="Touchpad may be disabled (Fn key), driver fault, USB power issue, "
            "or pointer settings blocking movement.",
            resolution_steps=[
                "Press Fn + the touchpad key on your keyboard, or double-tap the top-left "
                "corner of the touchpad to turn it back on.",
                "Settings > Bluetooth & devices > Mouse: check pointer speed and that the "
                "correct device is selected.",
                "Device Manager > Mice and other pointing devices: right-click your device > "
                "Update driver, or Uninstall device and restart the PC.",
                "For a USB mouse: unplug it, try another USB port, or replace wireless batteries.",
                "Restart the PC and test the pointer in Notepad or on the desktop.",
            ],
            ask_ai_prompt="My mouse or touchpad is connected but not working. How do I fix it?",
        ))
    else:
        names = ", ".join(
            (d.get("name") or "Mouse")
            for d in (usb_mice[:2] + bt_mice[:2] + built_in[:2])
        )
        findings.append(TroubleshooterFinding(
            id="no_fault_mouse",
            title="Mouse / Pointing Device Is Connected",
            area="Mouse",
            severity=Severity.info,
            detected=f"Physical pointing device(s) connected: {names}.",
            likely_cause="A mouse or touchpad is present. Cursor issues may be driver or settings related.",
            resolution_steps=[
                "Settings > Bluetooth & devices > Mouse: check pointer speed.",
                "Try another USB port for wired mice.",
                "Update the pointing device driver in Device Manager.",
            ],
            ask_ai_prompt="My mouse is connected but the cursor isn't working right. What should I check?",
        ))
    return findings


def _keyboard_findings(hw: dict, message: str) -> list[TroubleshooterFinding]:
    usb_kbd = _peripherals_matching(hw, _KEYBOARD_USB_RE)
    bt = (_external(hw).get("bluetooth") or {}).get("devices") or []
    bt_kbd = [
        d for d in bt
        if d.get("connected") and re.search(r"keyboard", d.get("name", ""), re.I)
    ]
    built_in = _hw_keyboards(hw)
    connected = usb_kbd + bt_kbd + built_in
    findings: list[TroubleshooterFinding] = []
    if not connected:
        findings.append(TroubleshooterFinding(
            id="keyboard_not_connected",
            title="No Keyboard Connected",
            area="Keyboard",
            severity=Severity.warning,
            detected="No physical keyboard is connected (USB or Bluetooth).",
            likely_cause="USB keyboard unplugged, Bluetooth keyboard off, or not paired.",
            resolution_steps=[
                "Plug in a USB keyboard or turn on your wireless keyboard.",
                "For Bluetooth: Settings > Bluetooth & devices > connect the keyboard.",
                "Device Manager > Keyboards: enable or reinstall the driver.",
            ],
            ask_ai_prompt="My keyboard isn't connected. How do I get Windows to detect it?",
        ))
    elif _device_not_working(message):
        names = ", ".join(
            (d.get("name") or "Keyboard")
            for d in (usb_kbd[:2] + bt_kbd[:2] + built_in[:2])
        )
        findings.append(TroubleshooterFinding(
            id="keyboard_not_working",
            title="Keyboard Connected but Not Working",
            area="Keyboard",
            severity=Severity.warning,
            detected=f"Keyboard detected ({names}) but you reported keys are not working.",
            likely_cause="Driver fault, Filter Keys enabled, wrong input language, or a stuck key.",
            resolution_steps=[
                "Settings > Accessibility > Keyboard: turn off Filter Keys and Sticky Keys if enabled.",
                "Settings > Time & language > Language & region: confirm the correct keyboard layout.",
                "Device Manager > Keyboards: right-click your keyboard > Update driver.",
                "For wireless keyboards: replace batteries or re-pair in Bluetooth settings.",
                "Restart the PC and test in Notepad.",
            ],
            ask_ai_prompt="My keyboard is connected but keys don't work. How do I fix it?",
        ))
    else:
        names = ", ".join(
            (d.get("name") or "Keyboard")
            for d in (usb_kbd[:2] + bt_kbd[:2] + built_in[:2])
        )
        findings.append(TroubleshooterFinding(
            id="no_fault_keyboard",
            title="Keyboard Is Connected",
            area="Keyboard",
            severity=Severity.info,
            detected=f"Physical keyboard(s) connected: {names}.",
            likely_cause="A keyboard is present. Key issues may be layout, driver, or a stuck key.",
            resolution_steps=[
                "Check keyboard layout: Settings > Time & language > Language & region.",
                "Try another USB port or replace batteries in wireless keyboards.",
                "Device Manager > Keyboards: update the driver.",
            ],
            ask_ai_prompt="My keyboard is connected but keys aren't working. What should I check?",
        ))
    return findings


def _scanner_findings(hw: dict, message: str) -> list[TroubleshooterFinding]:
    if not re.search(r"\bscanner\b", message or "", re.I):
        return []
    section = _external(hw).get("scanners") or {}
    scanners = [s for s in (section.get("scanners") or []) if s.get("is_physical")]
    if not scanners:
        return [TroubleshooterFinding(
            id="scanner_not_connected",
            title="No Scanner Connected",
            area="Scanner",
            severity=Severity.warning,
            detected="No physical scanner hardware is connected to this PC.",
            likely_cause="The scanner is unplugged (USB/network) or its driver isn't installed.",
            resolution_steps=[
                "Connect the scanner via USB or network.",
                "Settings > Bluetooth & devices > Printers & scanners > Add device.",
                "Install the scanner driver from the manufacturer's website.",
            ],
            ask_ai_prompt="My scanner isn't connected. How do I set it up?",
        )]
    ready = [s for s in scanners if s.get("connected")]
    if ready:
        names = ", ".join(s.get("name", "Scanner") for s in ready[:3])
        return [TroubleshooterFinding(
            id="no_fault_scanner",
            title="Scanner Is Connected",
            area="Scanner",
            severity=Severity.info,
            detected=f"Physical scanner(s) connected: {names}.",
            likely_cause="Scanner hardware is present and reporting a normal status.",
            resolution_steps=[
                "Open Windows Scan or the manufacturer's app to test a scan.",
                "Check the scanner has paper loaded and isn't showing an error light.",
            ],
            ask_ai_prompt="My scanner is connected but won't scan. What should I check?",
        )]
    return []


_DOMAIN_HANDLERS: dict[str, Any] = {
    "webcam": lambda hw, sw, msg, prof: _webcam_findings(hw),
    "audio": lambda hw, sw, msg, prof: _audio_findings(hw, msg, prof),
    "printer": lambda hw, sw, msg, prof: _printer_findings(hw) + _scanner_findings(hw, msg),
    "display": lambda hw, sw, msg, prof: _display_external_findings(hw, msg),
    "bluetooth": lambda hw, sw, msg, prof: _bluetooth_external_findings(hw),
    "usb": lambda hw, sw, msg, prof: _usb_external_findings(hw),
    "mouse": lambda hw, sw, msg, prof: _mouse_findings(hw, msg),
    "keyboard": lambda hw, sw, msg, prof: _keyboard_findings(hw, msg),
}

_DOMAIN_DEVICE_PATTERNS: dict[str, list[str]] = {
    "bluetooth": [r"bluetooth"],
    "wifi": [r"wi-?fi", r"wireless", r"wlan"],
    "network": [r"ethernet", r"network", r"adapter"],
    "printer": [r"printer", r"print"],
    "display": [r"display", r"monitor", r"graphics", r"nvidia", r"amd", r"intel.*graphics"],
    "usb": [r"usb", r"unknown device"],
    "mouse": [r"mouse", r"touchpad", r"pointing"],
    "keyboard": [r"keyboard"],
}


def build_findings_from_scan(
    report: dict[str, Any],
    profile: IssueProfile,
    message: str = "",
) -> list[TroubleshooterFinding]:
    """Issue-focused findings only — never unrelated system health noise."""
    hw = report.get("hardware") or {}
    sw = report.get("software") or {}
    domains = list(profile.domains)
    findings: list[TroubleshooterFinding] = []
    handled: set[str] = set()

    for domain in domains:
        handler = _DOMAIN_HANDLERS.get(domain)
        if handler and domain not in handled:
            findings.extend(handler(hw, sw, message, profile))
            handled.add(domain)

    for domain, patterns in _DOMAIN_DEVICE_PATTERNS.items():
        if domain in domains and domain not in handled:
            part = _device_findings_for_domain(hw, domain, patterns)
            if part:
                findings.extend(part)
                handled.add(domain)

    if not findings and domains:
        findings.append(_no_fault_finding(profile, message, domains[0]))

    # De-dupe by title; prefer real faults over the no-fault placeholder
    seen: set[str] = set()
    unique: list[TroubleshooterFinding] = []
    faults = [f for f in findings if not f.id.startswith("no_fault_")]
    infos = [f for f in findings if f.id.startswith("no_fault_")]
    for f in faults + infos:
        if f.title in seen:
            continue
        seen.add(f.title)
        unique.append(f)
    return unique[:8]


# ------------------------------------------------------------------ #
#  Issue-focused probes for the UI (not the entire system dump)
# ------------------------------------------------------------------ #

def _audio_probe_checks(hw: dict, message: str, profile: IssueProfile) -> list[ProbeCheck]:
    checks: list[ProbeCheck] = []
    mic_focus = _is_mic_issue(message, profile)
    title = "Microphone" if mic_focus else "Audio"

    for svc_name, label in _AUDIO_SERVICES.items():
        svc = get_service(svc_name)
        if svc:
            running = str(svc.get("Status", "")).lower() == "running"
            checks.append(ProbeCheck(
                label=label,
                value=f"{svc.get('Status')} ({svc.get('StartType')})",
                status=Severity.healthy if running else Severity.warning,
            ))

    if mic_focus:
        access = _privacy_access("microphone")
        if access:
            checks.append(ProbeCheck(
                label="Microphone privacy",
                value=access,
                status=Severity.healthy if access.lower() == "allow" else Severity.warning,
            ))
        endpoints = _mic_endpoints()
        physical_mics = _physical_audio_inputs(hw)
        virtual_mics = [d for d in _ext_audio_inputs(hw) if d.get("is_virtual")]
        mic_eps = [e for e in endpoints if _MIC_NAME_PATTERNS.search(e.get("FriendlyName") or "")]
        checks.append(ProbeCheck(
            label="Physical microphones",
            value=str(len(physical_mics)) if physical_mics else "None connected",
            status=Severity.healthy if physical_mics else Severity.warning,
        ))
        if virtual_mics:
            checks.append(ProbeCheck(
                label="Virtual audio inputs",
                value=str(len(virtual_mics)),
                status=Severity.info,
                detail="Software devices (e.g. Stereo Mix, Voicemeeter) — not hardware",
            ))
        for ep in physical_mics[:3]:
            ok = ep.get("working")
            checks.append(ProbeCheck(
                label=ep.get("name") or "Microphone",
                value=str(ep.get("status") or ep.get("health") or "Unknown"),
                status=Severity.healthy if ok else Severity.warning,
            ))
    else:
        physical_out = _physical_audio_outputs(hw)
        virtual_out = [d for d in _ext_audio_outputs(hw) if d.get("is_virtual")]
        checks.append(ProbeCheck(
            label="Physical audio outputs",
            value=str(len(physical_out)) if physical_out else "None connected",
            status=Severity.healthy if physical_out else Severity.warning,
        ))
        if virtual_out:
            checks.append(ProbeCheck(
                label="Virtual audio outputs",
                value=str(len(virtual_out)),
                status=Severity.info,
            ))
        for d in physical_out[:3]:
            checks.append(ProbeCheck(
                label=d.get("name") or "Speaker",
                value=str(d.get("health") or "Unknown"),
                status=Severity.healthy if d.get("working") else Severity.warning,
            ))
        audio_devs = [
            d for d in _audio_devices(hw)
            if not is_virtual_audio(d.get("name") or "")
        ]
        if not physical_out and audio_devs:
            checks.append(ProbeCheck(
                label="Audio devices (driver scan)",
                value=f"{sum(1 for d in audio_devs if d.get('working'))} OK / {len(audio_devs)} total",
                status=Severity.healthy if audio_devs else Severity.warning,
            ))

    return checks


def _webcam_probe_checks(hw: dict) -> list[ProbeCheck]:
    checks: list[ProbeCheck] = []
    access = _privacy_access("webcam")
    if access:
        checks.append(ProbeCheck(
            label="Camera privacy",
            value=access,
            status=Severity.healthy if access.lower() == "allow" else Severity.warning,
        ))
    physical = _physical_cameras(hw)
    virtual = _virtual_cameras(hw)
    if not physical and not virtual:
        physical = [
            c for c in _camera_devices(hw)
            if not is_virtual_camera(c.get("name") or "")
        ]
    checks.append(ProbeCheck(
        label="Physical cameras",
        value=str(len(physical)) if physical else "None connected",
        status=Severity.healthy if physical else Severity.warning,
    ))
    if virtual:
        checks.append(ProbeCheck(
            label="Virtual cameras",
            value=str(len(virtual)),
            status=Severity.info,
            detail="Software cameras (e.g. OBS Virtual Camera) — not hardware",
        ))
    for cam in physical[:3]:
        ok = cam.get("connected", cam.get("working"))
        checks.append(ProbeCheck(
            label=cam.get("name") or "Camera",
            value=str(cam.get("status") or cam.get("health") or "Unknown"),
            status=Severity.healthy if ok else Severity.warning,
        ))
    return checks


def _printer_probe_checks(hw: dict) -> list[ProbeCheck]:
    section = _external(hw).get("printers") or {}
    printers = section.get("printers") or []
    physical = [p for p in printers if p.get("is_physical")]
    virtual = [p for p in printers if p.get("is_virtual")]
    checks: list[ProbeCheck] = []
    checks.append(ProbeCheck(
        label="Print Spooler service",
        value="Running" if section.get("spooler_running") else "Stopped",
        status=Severity.healthy if section.get("spooler_running") else Severity.critical,
    ))
    checks.append(ProbeCheck(
        label="Physical printers",
        value=str(len(physical)) if physical else "None connected",
        status=Severity.healthy if section.get("has_connected_physical_printer") else Severity.warning,
    ))
    if virtual:
        checks.append(ProbeCheck(
            label="Software / virtual printers",
            value=str(len(virtual)),
            status=Severity.info,
            detail="Built-in queues like Print to PDF and OneNote — not hardware",
        ))
    pnp_usb = section.get("pnp_usb_printers") or []
    if pnp_usb:
        checks.append(ProbeCheck(
            label="USB printer hardware (PnP)",
            value=str(len(pnp_usb)),
            status=Severity.healthy,
            detail=", ".join(p.get("name", "device") for p in pnp_usb[:3]),
        ))
    for p in physical[:6]:
        offline = p.get("health") == "Offline"
        detail = p.get("connection") or ""
        if p.get("network_address"):
            detail += f" · {p.get('network_address')}"
        checks.append(ProbeCheck(
            label=f"Printer: {p.get('name')}" + (" (default)" if p.get("is_default") else ""),
            value=("Offline" if offline else (p.get("health") or "Ready")),
            status=Severity.warning if offline else Severity.healthy,
            detail=detail.strip(" ·") or None,
        ))
    for p in virtual[:3]:
        checks.append(ProbeCheck(
            label=f"Virtual: {p.get('name')}" + (" (default)" if p.get("is_default") else ""),
            value="Software queue (not hardware)",
            status=Severity.info,
        ))
    if section.get("queued_jobs"):
        checks.append(ProbeCheck(
            label="Pending print jobs",
            value=str(section.get("queued_jobs")),
            status=Severity.info,
        ))
    return checks


def _display_probe_checks(hw: dict) -> list[ProbeCheck]:
    section = _external(hw).get("monitors") or {}
    monitors = section.get("monitors") or []
    external = [m for m in monitors if m.get("is_external")]
    internal = [m for m in monitors if m.get("is_internal")]
    checks: list[ProbeCheck] = [
        ProbeCheck(
            label="External displays",
            value=str(len(external)) if external else "None connected",
            status=Severity.healthy if external else Severity.warning,
        ),
        ProbeCheck(
            label="Built-in display",
            value=str(len(internal)) if internal else "None",
            status=Severity.healthy if internal else Severity.info,
        ),
    ]
    for m in external[:4]:
        bits = []
        if m.get("connection_type"):
            bits.append(m["connection_type"])
        if m.get("resolution"):
            bits.append(m["resolution"])
        if m.get("refresh_rate_hz"):
            bits.append(f"{m['refresh_rate_hz']}Hz")
        checks.append(ProbeCheck(
            label=f"External: {m.get('model') or m.get('manufacturer') or 'Display'}",
            value=" · ".join(bits) or "Active",
            status=Severity.healthy,
        ))
    return checks


def _bluetooth_probe_checks(hw: dict) -> list[ProbeCheck]:
    bt = _external(hw).get("bluetooth") or {}
    devices = bt.get("devices") or []
    connected = [d for d in devices if d.get("connected")]
    checks: list[ProbeCheck] = [ProbeCheck(
        label="Bluetooth adapter",
        value="Present" if bt.get("adapter_present") else "Not found",
        status=Severity.healthy if bt.get("adapter_present") else Severity.critical,
    )]
    checks.append(ProbeCheck(
        label="Physically connected",
        value=f"{len(connected)} connected" if connected else "None connected",
        status=Severity.healthy if connected else Severity.warning,
    ))
    checks.append(ProbeCheck(
        label="Paired devices",
        value=str(bt.get("paired_count", 0)),
        status=Severity.info,
    ))
    for d in devices[:5]:
        checks.append(ProbeCheck(
            label=f"{d.get('device_type')}: {d.get('name')}",
            value="Connected" if d.get("connected") else "Paired (not connected)",
            status=Severity.healthy if d.get("connected") else Severity.info,
        ))
    return checks


def _usb_probe_checks(hw: dict) -> list[ProbeCheck]:
    usb = _external(hw).get("usb") or {}
    peripherals = _usb_peripherals(hw)
    problems = usb.get("problem_devices") or []
    checks: list[ProbeCheck] = [ProbeCheck(
        label="USB peripherals connected",
        value=str(usb.get("peripheral_count") or len(peripherals)),
        status=Severity.healthy if peripherals else Severity.warning,
    )]
    for d in peripherals[:8]:
        ok = d.get("health") == "Connected"
        checks.append(ProbeCheck(
            label=f"{d.get('type')}: {d.get('name')}",
            value=d.get("health") or "Connected",
            status=Severity.healthy if ok else Severity.warning,
        ))
    for s in (_external(hw).get("external_storage") or {}).get("devices", [])[:4]:
        ok = s.get("health") == "Connected"
        cap = f"{s.get('free_gb')}/{s.get('capacity_gb')} GB free" if s.get("capacity_gb") else ""
        checks.append(ProbeCheck(
            label=f"External drive: {s.get('name')}",
            value=s.get("health") or "Connected",
            status=Severity.healthy if ok else Severity.warning,
            detail=cap or None,
        ))
    if not problems and peripherals:
        checks.append(ProbeCheck(label="USB peripherals with errors", value="None", status=Severity.healthy))
    return checks


def _mouse_probe_checks(hw: dict) -> list[ProbeCheck]:
    usb_mice = _peripherals_matching(hw, _MOUSE_USB_RE)
    built_in = _hw_pointing_devices(hw)
    bt = (_external(hw).get("bluetooth") or {}).get("devices") or []
    bt_mice = [
        d for d in bt
        if d.get("connected") and re.search(r"mouse|trackpad|touchpad", d.get("name", ""), re.I)
    ]
    total = usb_mice + built_in + bt_mice
    checks = [ProbeCheck(
        label="Physical pointing devices",
        value=str(len(total)) if total else "None connected",
        status=Severity.healthy if total else Severity.warning,
    )]
    for d in (usb_mice + built_in)[:4]:
        checks.append(ProbeCheck(
            label=d.get("name") or "Mouse",
            value=d.get("health") or d.get("status") or "Connected",
            status=Severity.healthy,
        ))
    for d in bt_mice[:2]:
        checks.append(ProbeCheck(
            label=f"BT: {d.get('name')}",
            value="Connected",
            status=Severity.healthy,
        ))
    return checks


def _keyboard_probe_checks(hw: dict) -> list[ProbeCheck]:
    usb_kbd = _peripherals_matching(hw, _KEYBOARD_USB_RE)
    built_in = _hw_keyboards(hw)
    bt = (_external(hw).get("bluetooth") or {}).get("devices") or []
    bt_kbd = [
        d for d in bt
        if d.get("connected") and re.search(r"keyboard", d.get("name", ""), re.I)
    ]
    total = usb_kbd + built_in + bt_kbd
    checks = [ProbeCheck(
        label="Physical keyboards",
        value=str(len(total)) if total else "None connected",
        status=Severity.healthy if total else Severity.warning,
    )]
    for d in (usb_kbd + built_in)[:4]:
        checks.append(ProbeCheck(
            label=d.get("name") or "Keyboard",
            value=d.get("health") or d.get("status") or "Connected",
            status=Severity.healthy,
        ))
    for d in bt_kbd[:2]:
        checks.append(ProbeCheck(
            label=f"BT: {d.get('name')}",
            value="Connected",
            status=Severity.healthy,
        ))
    return checks


_DOMAIN_PROBE_BUILDERS: dict[str, Any] = {
    "printer": _printer_probe_checks,
    "display": _display_probe_checks,
    "bluetooth": _bluetooth_probe_checks,
    "usb": _usb_probe_checks,
    "mouse": _mouse_probe_checks,
    "keyboard": _keyboard_probe_checks,
}


def build_probes_from_scan(
    report: dict[str, Any],
    profile: IssueProfile,
    message: str = "",
) -> list[ProbeResult]:
    """Show checks relevant to the user's issue (data from the full scan)."""
    hw = report.get("hardware") or {}
    duration = report.get("scan_duration_seconds")
    scan_note = f"From full system scan ({duration}s)" if duration else "From full system scan"
    domains = set(profile.domains)
    probes: list[ProbeResult] = []

    if "audio" in domains:
        checks = _audio_probe_checks(hw, message, profile)
        focus = "Microphone" if _is_mic_issue(message, profile) else "Audio / Sound"
        probes.append(ProbeResult(
            domain="audio",
            title=f"{focus} (issue scan)",
            available=True,
            checks=checks,
            note=scan_note,
        ))

    if "webcam" in domains:
        probes.append(ProbeResult(
            domain="webcam",
            title="Webcam / Camera (issue scan)",
            available=True,
            checks=_webcam_probe_checks(hw),
            note=scan_note,
        ))

    # External-hardware domains: report real connection status from the inventory.
    _external_titles = {
        "printer": "Printers (issue scan)",
        "display": "Displays & Monitors (issue scan)",
        "bluetooth": "Bluetooth Devices (issue scan)",
        "usb": "USB & External Devices (issue scan)",
        "mouse": "Mouse & Pointing Devices (issue scan)",
        "keyboard": "Keyboard (issue scan)",
    }
    handled_external: set[str] = set()
    for domain, builder in _DOMAIN_PROBE_BUILDERS.items():
        if domain in domains:
            probes.append(ProbeResult(
                domain=domain,
                title=_external_titles.get(domain, f"{domain.title()} (issue scan)"),
                available=True,
                checks=builder(hw),
                note=scan_note,
            ))
            handled_external.add(domain)

    for domain, patterns in _DOMAIN_DEVICE_PATTERNS.items():
        if domain in domains and domain not in ({"audio"} | handled_external):
            problems = (hw.get("devices") or {}).get("problem_devices") or []
            matched = [
                d for d in problems
                if any(re.search(p, f"{d.get('name', '')} {d.get('class', '')}", re.I) for p in patterns)
            ]
            checks = [
                ProbeCheck(
                    label=d.get("name") or "Device",
                    value=f"{d.get('status')} (code {d.get('problem_code')})",
                    status=Severity.warning,
                )
                for d in matched[:5]
            ]
            if not checks:
                checks.append(ProbeCheck(
                    label=f"{domain.title()} devices",
                    value="No driver errors detected",
                    status=Severity.healthy,
                ))
            probes.append(ProbeResult(
                domain=domain,
                title=f"{domain.title()} (issue scan)",
                available=True,
                checks=checks,
                note=scan_note,
            ))

    if not probes:
        label = _issue_label(profile, message)
        probes.append(ProbeResult(
            domain=profile.primary_domain or "issue",
            title=f"{label.title()} (issue scan)",
            available=True,
            checks=[ProbeCheck(
                label="Full scan",
                value="No fault detected in related components",
                status=Severity.info,
            )],
            note=scan_note,
        ))

    return probes


def build_issue_scoped_scan_context(
    report: dict[str, Any],
    profile: IssueProfile,
    message: str,
) -> dict[str, Any]:
    """Compact facts for the LLM — only what relates to the reported issue."""
    hw = report.get("hardware") or {}
    sw = report.get("software") or {}
    ctx: dict[str, Any] = {
        "user_issue": message,
        "focus_domains": profile.domains,
        "symptoms": profile.symptoms,
    }
    physical_inv = _external(hw).get("physical_inventory")
    if physical_inv:
        ctx["physical_inventory"] = physical_inv
        ctx["physical_device_note"] = (
            "Only devices marked physical/connected in the inventory are real hardware. "
            "Virtual/software devices (PDF printers, OBS camera, Stereo Mix, etc.) do not count."
        )

    if "audio" in profile.domains:
        mic = _is_mic_issue(message, profile)
        ctx["focus"] = "microphone" if mic else "audio"
        ctx["audio_services"] = {
            name: get_service(name)
            for name in _AUDIO_SERVICES
        }
        if mic:
            ctx["microphone_privacy"] = _privacy_access("microphone")
            audio_sec = _external(hw).get("audio") or {}
            ctx["has_connected_physical_microphone"] = audio_sec.get("has_connected_physical_input", False)
            ctx["microphone_endpoints"] = [
                {"name": d.get("name"), "status": d.get("status"), "is_virtual": d.get("is_virtual")}
                for d in _ext_audio_inputs(hw)[:8]
            ]
        else:
            audio_sec = _external(hw).get("audio") or {}
            ctx["has_connected_physical_speaker"] = audio_sec.get("has_connected_physical_output", False)
            ctx["audio_outputs"] = [
                {"name": d.get("name"), "status": d.get("status"), "is_virtual": d.get("is_virtual")}
                for d in _ext_audio_outputs(hw)[:8]
            ]
        ctx["audio_devices"] = [
            {"name": d.get("name"), "status": d.get("status"), "working": d.get("working")}
            for d in _audio_devices(hw)[:8]
            if not is_virtual_audio(d.get("name") or "")
        ]

    elif "webcam" in profile.domains:
        ctx["focus"] = "webcam"
        ctx["camera_privacy"] = _privacy_access("webcam")
        cam_sec = _external(hw).get("cameras") or {}
        ctx["has_connected_physical_camera"] = cam_sec.get("has_connected_physical_camera", False)
        ctx["cameras"] = [
            {
                "name": c.get("name"),
                "status": c.get("status") or c.get("health"),
                "is_virtual": c.get("is_virtual"),
                "is_physical": c.get("is_physical"),
            }
            for c in (cam_sec.get("cameras") or _ext_cameras(hw) or [
                {"name": c.get("name"), "status": c.get("status"), "is_physical": True}
                for c in _camera_devices(hw)
                if not is_virtual_camera(c.get("name") or "")
            ])[:8]
        ]

    elif "printer" in profile.domains:
        ctx["focus"] = "printer"
        section = _external(hw).get("printers") or {}
        ctx["spooler_running"] = section.get("spooler_running")
        ctx["queued_jobs"] = section.get("queued_jobs")
        ctx["physical_count"] = section.get("physical_count", 0)
        ctx["has_connected_physical_printer"] = section.get("has_connected_physical_printer", False)
        ctx["pnp_usb_printers"] = section.get("pnp_usb_printers") or []
        ctx["printers"] = [
            {
                "name": p.get("name"),
                "status": p.get("health"),
                "offline": p.get("offline"),
                "connection": p.get("connection"),
                "network_address": p.get("network_address"),
                "is_default": p.get("is_default"),
                "is_virtual": p.get("is_virtual"),
                "is_physical": p.get("is_physical"),
                "driver": p.get("driver"),
            }
            for p in (section.get("printers") or [])[:8]
        ]

    elif "display" in profile.domains:
        ctx["focus"] = "display"
        section = _external(hw).get("monitors") or {}
        ctx["monitor_count"] = section.get("count")
        ctx["external_monitor_count"] = section.get("external_count", 0)
        ctx["has_external_monitor"] = section.get("has_external_monitor", False)
        ctx["monitors"] = [
            {
                "model": m.get("model"),
                "connection_type": m.get("connection_type"),
                "resolution": m.get("resolution"),
                "refresh_rate_hz": m.get("refresh_rate_hz"),
                "is_external": m.get("is_external"),
                "is_internal": m.get("is_internal"),
            }
            for m in (section.get("monitors") or [])[:6]
        ]

    elif "bluetooth" in profile.domains:
        ctx["focus"] = "bluetooth"
        bt = _external(hw).get("bluetooth") or {}
        ctx["adapter_present"] = bt.get("adapter_present")
        ctx["connected_bluetooth_count"] = bt.get("connected_count", 0)
        ctx["has_connected_bluetooth_device"] = bt.get("has_connected_device", False)
        ctx["bluetooth_devices"] = [
            {"name": d.get("name"), "type": d.get("device_type"), "connected": d.get("connected")}
            for d in (bt.get("devices") or [])[:8]
        ]

    elif "usb" in profile.domains:
        ctx["focus"] = "usb"
        usb = _external(hw).get("usb") or {}
        ctx["usb_peripheral_count"] = usb.get("peripheral_count", 0)
        ctx["has_connected_usb_peripherals"] = usb.get("has_connected_peripherals", False)
        ctx["usb_devices"] = [
            {
                "name": d.get("name"),
                "type": d.get("type"),
                "health": d.get("health"),
                "is_peripheral": d.get("is_peripheral"),
            }
            for d in (usb.get("devices") or []) if d.get("is_peripheral")
        ][:12]
        ctx["external_storage"] = [
            {"name": s.get("name"), "health": s.get("health"), "free_gb": s.get("free_gb")}
            for s in (_external(hw).get("external_storage") or {}).get("devices", [])[:4]
        ]

    else:
        ctx["focus"] = profile.primary_domain or "general"
        patterns = []
        for d in profile.domains:
            patterns.extend(_DOMAIN_DEVICE_PATTERNS.get(d, []))
        if patterns:
            problems = (hw.get("devices") or {}).get("problem_devices") or []
            ctx["related_device_problems"] = [
                {"name": p.get("name"), "status": p.get("status")}
                for p in problems
                if any(re.search(pat, f"{p.get('name', '')} {p.get('class', '')}", re.I) for pat in patterns)
            ][:6]

    return ctx


# ------------------------------------------------------------------ #
#  Storage intelligence (evidence-backed "why is my disk full?")
# ------------------------------------------------------------------ #
_STORAGE_STEPS = [
    "Open Settings > System > Storage to see the breakdown, or run Disk Cleanup (`cleanmgr`).",
    "Empty the Recycle Bin and clear `%TEMP%` and `C:\\Windows\\Temp`.",
    "In Disk Cleanup, tick 'Windows Update Cleanup' and 'Delivery Optimization Files'.",
    "Move or delete large old downloads and duplicate media files.",
    "Uninstall unused apps via Settings > Apps > Installed apps; enable Storage Sense.",
]

_LARGEST_FILE_RE = re.compile(
    r"largest\s+file|biggest\s+file|which\s+file|what\s+file|what\s+is\s+using|"
    r"what's\s+using|taking\s+(?:the\s+)?(?:most|more|up)\s+space|using\s+the\s+most|"
    r"consuming\s+(the\s+)?most",
    re.I,
)


def _storage_relevant(profile: IssueProfile, message: str, data: dict[str, Any]) -> bool:
    """Whether to surface storage findings/probes for this issue."""
    if "storage" in profile.domains:
        return True
    if _LARGEST_FILE_RE.search(message or ""):
        return True
    if "performance" in profile.domains:
        for d in data.get("drives") or []:
            if (d.get("used_pct") or 0) >= 90:
                return True
    return False


def _best_storage_data(report: dict[str, Any]) -> dict[str, Any] | None:
    sw = report.get("software") or {}
    deep = sw.get("storage_deep") or {}
    if deep and not deep.get("error"):
        return deep
    quick = sw.get("storage_intelligence") or {}
    if quick and not quick.get("error"):
        return quick
    return None


def _storage_findings(
    data: dict[str, Any],
    message: str = "",
    *,
    deep: dict[str, Any] | None = None,
    show_file_details: bool = False,
) -> list[TroubleshooterFinding]:
    findings: list[TroubleshooterFinding] = []
    drives = data.get("drives") or []
    cleanup = data.get("cleanup") or {}
    total_recover = cleanup.get("total_potential_gb") or 0
    quick_wins = cleanup.get("quick_wins") or []
    safe = cleanup.get("safe_cleanup") or []
    top_items = (quick_wins + safe)[:4]
    top_text = ", ".join(
        f"{c['label']} (~{c['recover_gb']} GB)" for c in top_items if c.get("recover_gb")
    ) or "temporary files, Recycle Bin and browser caches"

    tree = (deep or {}).get("tree") or data.get("tree") or {}
    top_files = tree.get("top_files") or []
    top_folders = tree.get("top_folders") or []

    if top_files and show_file_details:
        top = top_files[0]
        drive_label = (deep or {}).get("scanned_drive") or ""
        drive_note = f" on {drive_label}" if drive_label else ""
        listing = "; ".join(
            f"{f.get('path')} ({f.get('size_gb')} GB)" for f in top_files[:6] if f.get("path")
        )
        findings.append(TroubleshooterFinding(
            id="storage_largest_files",
            title=f"Largest Files{drive_note}",
            area="Storage",
            severity=Severity.info,
            detected=(
                f"Largest file{drive_note}: {top.get('path')} ({top.get('size_gb')} GB). "
                f"Other large files: {listing}."
            ),
            likely_cause="These are the biggest individual files found during a deep disk walk. "
            "Removing or moving them frees the most space per file.",
            resolution_steps=[
                f"Review the largest file: {top.get('path')} — move it to external storage or "
                "delete if you no longer need it.",
                "Check your Downloads folder and old video/installer files.",
                "Run Disk Cleanup for safe system caches after removing personal large files.",
                "Empty the Recycle Bin after deleting files.",
            ],
            ask_ai_prompt="Which files on my PC are using the most space and what can I delete?",
        ))

    if top_folders and show_file_details:
        big = top_folders[0]
        folder_list = "; ".join(
            f"{f.get('path')} ({f.get('size_gb')} GB)" for f in top_folders[:4] if f.get("path")
        )
        findings.append(TroubleshooterFinding(
            id="storage_largest_folders",
            title="Largest Folders on Disk",
            area="Storage",
            severity=Severity.info,
            detected=(
                f"Largest folder: {big.get('path')} ({big.get('size_gb')} GB). "
                f"Also large: {folder_list}."
            ),
            likely_cause="These folders contain the most data on the scanned drive.",
            resolution_steps=[
                f"Open {big.get('path')} in File Explorer and sort by size to find what's inside.",
                "Move old projects, games, or media to another drive if possible.",
                "Uninstall unused applications from Settings > Apps.",
            ],
            ask_ai_prompt="Which folders are using the most disk space on my PC?",
        ))

    flagged = False
    for d in drives:
        used = d.get("used_pct") or 0
        free = d.get("free_gb")
        if used >= 85:
            flagged = True
            sev = Severity.critical if used >= 95 else Severity.warning
            findings.append(TroubleshooterFinding(
                id=f"storage_full_{(d.get('drive') or 'x').strip(':')}",
                title=f"{d.get('drive')} Is {used}% Full",
                area="Storage",
                severity=sev,
                detected=(
                    f"{d.get('drive')} has {free} GB free of {d.get('total_gb')} GB "
                    f"({used}% used). About {round(total_recover, 1)} GB is recoverable now."
                ),
                likely_cause=f"Space is consumed by temporary files, caches and downloads. Top wins: {top_text}.",
                resolution_steps=_STORAGE_STEPS,
                ask_ai_prompt=f"My {d.get('drive')} drive is {used}% full. What can I safely delete?",
            ))

    if not flagged and total_recover >= 1:
        findings.append(TroubleshooterFinding(
            id="storage_recoverable",
            title=f"~{round(total_recover, 1)} GB Can Be Recovered",
            area="Storage",
            severity=Severity.info,
            detected=f"Cleanup opportunities total about {round(total_recover, 1)} GB. Top: {top_text}.",
            likely_cause="Accumulated temporary files, caches, update leftovers and old downloads.",
            resolution_steps=_STORAGE_STEPS,
            ask_ai_prompt="How do I safely free up disk space on my PC?",
        ))
    return findings


def _storage_probe_checks(data: dict[str, Any], *, deep: dict[str, Any] | None = None) -> list[ProbeCheck]:
    checks: list[ProbeCheck] = []
    tree = (deep or {}).get("tree") or data.get("tree") or {}
    mode = "deep" if deep and not deep.get("error") else "quick"
    checks.append(ProbeCheck(
        label="Storage scan mode",
        value=mode,
        status=Severity.info,
    ))
    for d in data.get("drives") or []:
        used = d.get("used_pct") or 0
        sev = Severity.healthy
        if used >= 95:
            sev = Severity.critical
        elif used >= 85:
            sev = Severity.warning
        checks.append(ProbeCheck(
            label=f"Drive {d.get('drive')}",
            value=f"{used}% used · {d.get('free_gb')} GB free of {d.get('total_gb')} GB",
            status=sev,
        ))
    cleanup = data.get("cleanup") or {}
    total = cleanup.get("total_potential_gb") or 0
    checks.append(ProbeCheck(
        label="Recoverable space",
        value=f"~{round(total, 1)} GB",
        status=Severity.warning if total >= 5 else Severity.info,
    ))
    for loc in (data.get("cleanup_locations") or [])[:6]:
        gb = loc.get("size_gb") or 0
        if gb < 0.05:
            continue
        checks.append(ProbeCheck(
            label=loc.get("label") or "Cleanup location",
            value=f"{gb} GB",
            status=Severity.info,
        ))
    for f in (tree.get("top_files") or [])[:5]:
        checks.append(ProbeCheck(
            label=f"Largest file: {os.path.basename(f.get('path') or '?')}",
            value=f"{f.get('size_gb')} GB",
            status=Severity.info,
            detail=f.get("path"),
        ))
    for folder in (tree.get("top_folders") or [])[:3]:
        checks.append(ProbeCheck(
            label=f"Largest folder: {os.path.basename(folder.get('path') or '?')}",
            value=f"{folder.get('size_gb')} GB",
            status=Severity.info,
            detail=folder.get("path"),
        ))
    return checks


def _storage_context(
    data: dict[str, Any],
    *,
    deep: dict[str, Any] | None = None,
    include_files: bool = True,
    target_drive: str | None = None,
) -> dict[str, Any]:
    cleanup = data.get("cleanup") or {}
    tree = (deep or {}).get("tree") or data.get("tree") or {}
    scanned = (deep or {}).get("scanned_drive") or target_drive
    ctx: dict[str, Any] = {
        "focus": "storage",
        "scan_mode": "deep" if deep and not deep.get("error") else "quick",
        "scanned_drive": scanned,
        "target_drive": target_drive or scanned,
        "drives": [
            {"drive": d.get("drive"), "used_pct": d.get("used_pct"),
             "free_gb": d.get("free_gb"), "total_gb": d.get("total_gb")}
            for d in data.get("drives") or []
        ],
        "recoverable_total_gb": cleanup.get("total_potential_gb"),
        "cleanup_quick_wins": cleanup.get("quick_wins"),
        "cleanup_safe": cleanup.get("safe_cleanup"),
        "cleanup_advanced": cleanup.get("advanced_cleanup"),
        "top_cleanup_locations": [
            {"label": l.get("label"), "size_gb": l.get("size_gb"), "safe": l.get("safe_to_delete")}
            for l in (data.get("cleanup_locations") or [])[:10]
        ],
        "storage_health": data.get("health"),
    }
    if include_files:
        ctx["largest_files"] = [
            {"path": f.get("path"), "size_gb": f.get("size_gb")}
            for f in (tree.get("top_files") or [])[:15]
        ]
        ctx["largest_folders"] = [
            {"path": f.get("path"), "size_gb": f.get("size_gb")}
            for f in (tree.get("top_folders") or [])[:10]
        ]
        ctx["file_type_distribution"] = (tree.get("file_type_distribution") or data.get("file_type_distribution") or [])[:12]
        if tree.get("truncated"):
            ctx["scan_truncated"] = True
    return ctx


# ------------------------------------------------------------------ #
#  Continuous-monitoring telemetry (incident reconstruction + trends)
# ------------------------------------------------------------------ #
def _incident_findings(inc: dict[str, Any]) -> list[TroubleshooterFinding]:
    if not inc:
        return []
    cause = inc.get("probable_cause") or "No dominant cause found"
    conf = inc.get("confidence") or 0
    sev = Severity.warning if conf >= 70 else Severity.info
    timeline = inc.get("timeline") or []
    steps_by_cause = []
    lc = cause.lower()
    if "memory" in lc:
        steps_by_cause = [
            "Close the heaviest apps (check the top memory consumer) before they fill RAM.",
            "Restart memory-hungry apps like browsers periodically.",
            "Consider adding RAM if this recurs under your normal workload.",
        ]
    elif "cpu" in lc:
        steps_by_cause = [
            "Open Task Manager → Details and end the process pinning the CPU.",
            "Check for background updates/scans running at the time.",
        ]
    elif "disk" in lc:
        steps_by_cause = ["Free disk space (run Storage Analysis) — the drive was nearly full."]
    elif "bsod" in lc or "crash" in lc:
        steps_by_cause = ["Update or roll back the driver involved.", "Check Reliability Monitor for the faulting module."]
    else:
        steps_by_cause = ["Re-run this after the issue recurs so telemetry can capture it."]

    detail = (
        f"Around {inc.get('anchor')} (±{inc.get('window_minutes')} min): "
        f"peak CPU {inc.get('peak_cpu_pct')}%, peak RAM {inc.get('peak_mem_pct')}%"
    )
    if inc.get("min_disk_free_gb") is not None:
        detail += f", min free disk {inc.get('min_disk_free_gb')} GB"
    if not inc.get("has_telemetry"):
        return [TroubleshooterFinding(
            id="incident_no_data",
            title="Limited History For That Time",
            area="Monitoring",
            severity=Severity.info,
            detected="Continuous monitoring has little or no telemetry for that period yet.",
            likely_cause="The monitor started recently, so the incident window isn't fully covered.",
            resolution_steps=["Leave the assistant running; future incidents will be captured automatically.",
                              "If it recurs, note the time and ask again."],
            ask_ai_prompt="Reconstruct what happened the next time my PC freezes.",
        )]
    return [TroubleshooterFinding(
        id="incident_reconstruction",
        title=f"Incident Analysis: {cause}",
        area="Monitoring",
        severity=sev,
        detected=detail + f". {len(timeline)} event(s) on the timeline.",
        likely_cause=f"{cause} (confidence {conf}%).",
        resolution_steps=steps_by_cause,
        ask_ai_prompt="What caused my PC to freeze and how do I prevent it?",
    )]


def _incident_probe_checks(inc: dict[str, Any]) -> list[ProbeCheck]:
    checks: list[ProbeCheck] = [
        ProbeCheck(label="Probable cause", value=inc.get("probable_cause") or "-",
                   status=Severity.warning if (inc.get("confidence") or 0) >= 70 else Severity.info),
        ProbeCheck(label="Confidence", value=f"{inc.get('confidence')}%", status=Severity.info),
        ProbeCheck(label="Peak CPU", value=f"{inc.get('peak_cpu_pct')}%",
                   status=Severity.critical if (inc.get("peak_cpu_pct") or 0) >= 95 else Severity.healthy),
        ProbeCheck(label="Peak RAM", value=f"{inc.get('peak_mem_pct')}%",
                   status=Severity.critical if (inc.get("peak_mem_pct") or 0) >= 95 else Severity.healthy),
    ]
    for ev in (inc.get("timeline") or [])[:6]:
        checks.append(ProbeCheck(
            label=str(ev.get("ts") or "")[:19].replace("T", " "),
            value=str(ev.get("text") or "")[:90],
            status=Severity.warning if (ev.get("severity") in ("warning", "critical", "error")) else Severity.info,
        ))
    return checks


def _telemetry_probe_checks(ctx: dict[str, Any]) -> list[ProbeCheck]:
    cur = ctx.get("current") or {}
    base = ctx.get("baseline_7d") or {}
    checks: list[ProbeCheck] = []
    if cur:
        checks.append(ProbeCheck(label="CPU now", value=f"{cur.get('cpu_pct')}% (7d avg {base.get('cpu')}%)",
                                 status=Severity.warning if (cur.get("cpu_pct") or 0) >= 90 else Severity.healthy))
        checks.append(ProbeCheck(label="RAM now", value=f"{cur.get('mem_used_pct')}% (7d avg {base.get('mem')}%)",
                                 status=Severity.warning if (cur.get("mem_used_pct") or 0) >= 90 else Severity.healthy))
        checks.append(ProbeCheck(label="Disk free", value=f"{cur.get('disk_free_gb')} GB",
                                 status=Severity.warning if (cur.get("disk_used_pct") or 0) >= 90 else Severity.healthy))
    perf = (ctx.get("predictions") or {}).get("performance") or {}
    if perf.get("regression_detected"):
        checks.append(ProbeCheck(label="Performance vs last week", value="Regressed", status=Severity.warning))
    for a in (ctx.get("recent_alerts") or [])[:4]:
        checks.append(ProbeCheck(label=f"Alert: {a.get('title')}", value=str(a.get('ts'))[:16].replace("T", " "),
                                 status=Severity.warning if a.get("severity") in ("warning", "critical") else Severity.info))
    return checks or [ProbeCheck(label="Telemetry", value="Monitoring active, no recent alerts", status=Severity.healthy)]


def build_investigation_from_scan(
    report: dict[str, Any],
    profile: IssueProfile,
    message: str = "",
) -> tuple[list[ProbeResult], list[TroubleshooterFinding], dict[str, Any]]:
    probes = build_probes_from_scan(report, profile, message)
    findings = build_findings_from_scan(report, profile, message)
    scan_facts = build_issue_scoped_scan_context(report, profile, message)

    # Continuous-monitoring: incident reconstruction + trend context for
    # "what happened / when did it start / is it getting worse" questions.
    try:
        from app.services.telemetry_analytics_service import (
            TelemetryAnalyticsService, looks_like_incident, parse_incident_time,
        )

        is_incident = looks_like_incident(message)
        is_perf = "performance" in profile.domains
        if is_incident or is_perf:
            telem = TelemetryAnalyticsService()
            scan_facts["telemetry"] = telem.diagnosis_context()
            tel_checks = _telemetry_probe_checks(scan_facts["telemetry"])
            if is_incident:
                anchor, window = parse_incident_time(message)
                inc = telem.incident(anchor, window)
                scan_facts["incident_reconstruction"] = inc
                findings = [f for f in findings if not f.id.startswith("no_fault_")] + _incident_findings(inc)
                probes.insert(0, ProbeResult(
                    domain="monitoring", title="Incident Reconstruction (telemetry)",
                    available=True, checks=_incident_probe_checks(inc),
                    note=f"Telemetry around {str(anchor)[:19]} UTC",
                ))
            probes.append(ProbeResult(
                domain="monitoring", title="System Telemetry (history)",
                available=True, checks=tel_checks, note="Continuous monitoring",
            ))
    except Exception:  # pragma: no cover - never let monitoring break diagnosis
        pass

    # Every investigation runs a full machine scan with deep storage in parallel.
    # Surface storage probes/findings only when the issue is storage-related.
    storage_data = _best_storage_data(report)
    if storage_data and not storage_data.get("error"):
        deep = storage_data if storage_data.get("mode") == "deep" else None
        if not deep:
            raw_deep = (report.get("software") or {}).get("storage_deep") or {}
            deep = raw_deep if raw_deep and not raw_deep.get("error") else None
        include_files = _storage_relevant(profile, message, storage_data)
        show_file_details = bool(
            include_files
            and ("storage" in profile.domains or _LARGEST_FILE_RE.search(message or ""))
        )
        scan_facts["storage_intelligence"] = _storage_context(
            storage_data,
            deep=deep,
            include_files=include_files,
            target_drive=profile.target_drive,
        )
        if include_files:
            storage_findings = _storage_findings(
                storage_data,
                message=message,
                deep=deep,
                show_file_details=show_file_details,
            )
            findings = [f for f in findings if not f.id.startswith("no_fault_")] + storage_findings
            probes = [p for p in probes if p.domain != "storage"]
            mode_label = "deep" if deep else "quick"
            probes.insert(0, ProbeResult(
                domain="storage",
                title="Storage Intelligence (full scan)",
                available=True,
                checks=_storage_probe_checks(storage_data, deep=deep),
                note=f"Storage analysis ({mode_label}, {storage_data.get('scan_duration_seconds')}s)",
            ))
    return probes, findings, scan_facts
