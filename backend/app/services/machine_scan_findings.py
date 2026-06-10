"""Turn a comprehensive machine scan into issue-focused probes and findings.

The full machine scan always runs, but what we surface to the user and LLM is
filtered to the reported problem (e.g. microphone only — not CPU, firewall, or
unrelated stopped services).
"""
from __future__ import annotations

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
    cameras = _camera_devices(hw)
    broken = [c for c in cameras if not c.get("working")]

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

    if not cameras:
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
        if not mic_eps and endpoints:
            mic_eps = endpoints  # fallback: any input endpoint
        broken_mics = [
            e for e in mic_eps
            if str(e.get("Status", "")).lower() not in ("ok", "")
        ]
        if not mic_eps:
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

    audio_devs = _audio_devices(hw)
    broken_audio = [d for d in audio_devs if not d.get("working")]
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


_DOMAIN_HANDLERS: dict[str, Any] = {
    "webcam": lambda hw, sw, msg, prof: _webcam_findings(hw),
    "audio": lambda hw, sw, msg, prof: _audio_findings(hw, msg, prof),
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
        mic_eps = [e for e in endpoints if _MIC_NAME_PATTERNS.search(e.get("FriendlyName") or "")]
        checks.append(ProbeCheck(
            label="Microphone inputs detected",
            value=str(len(mic_eps) or len(endpoints)),
            status=Severity.healthy if (mic_eps or endpoints) else Severity.critical,
        ))
        for ep in (mic_eps or endpoints)[:3]:
            ok = str(ep.get("Status", "")).lower() == "ok"
            checks.append(ProbeCheck(
                label=ep.get("FriendlyName") or "Microphone",
                value=str(ep.get("Status") or "Unknown"),
                status=Severity.healthy if ok else Severity.warning,
            ))
    else:
        audio_devs = _audio_devices(hw)
        checks.append(ProbeCheck(
            label="Audio devices",
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
    cameras = _camera_devices(hw)
    checks.append(ProbeCheck(
        label="Cameras detected",
        value=str(len(cameras)),
        status=Severity.healthy if cameras else Severity.critical,
    ))
    for cam in cameras[:3]:
        checks.append(ProbeCheck(
            label=cam.get("name") or "Camera",
            value=str(cam.get("status") or "Unknown"),
            status=Severity.healthy if cam.get("working") else Severity.warning,
        ))
    return checks


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

    for domain, patterns in _DOMAIN_DEVICE_PATTERNS.items():
        if domain in domains and domain not in {"audio"}:
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

    if "audio" in profile.domains:
        mic = _is_mic_issue(message, profile)
        ctx["focus"] = "microphone" if mic else "audio"
        ctx["audio_services"] = {
            name: get_service(name)
            for name in _AUDIO_SERVICES
        }
        if mic:
            ctx["microphone_privacy"] = _privacy_access("microphone")
            ctx["microphone_endpoints"] = [
                {"name": e.get("FriendlyName"), "status": e.get("Status")}
                for e in _mic_endpoints()
            ]
        ctx["audio_devices"] = [
            {"name": d.get("name"), "status": d.get("status"), "working": d.get("working")}
            for d in _audio_devices(hw)[:8]
        ]

    elif "webcam" in profile.domains:
        ctx["focus"] = "webcam"
        ctx["camera_privacy"] = _privacy_access("webcam")
        ctx["cameras"] = [
            {"name": c.get("name"), "status": c.get("status"), "working": c.get("working")}
            for c in _camera_devices(hw)
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


def build_investigation_from_scan(
    report: dict[str, Any],
    profile: IssueProfile,
    message: str = "",
) -> tuple[list[ProbeResult], list[TroubleshooterFinding], dict[str, Any]]:
    probes = build_probes_from_scan(report, profile, message)
    findings = build_findings_from_scan(report, profile, message)
    scan_facts = build_issue_scoped_scan_context(report, profile, message)
    return probes, findings, scan_facts
