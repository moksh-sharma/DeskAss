"""Wi-Fi live probe pack: WLAN service, radio, current SSID and signal."""
from __future__ import annotations

import re

from app.models.schemas import ProbeCheck, ProbeResult, Severity, TroubleshooterFinding
from app.services.probes.base import (
    IS_WINDOWS,
    ProbeContext,
    ProbeOutcome,
    as_list,
    get_service,
    ps_json,
    run_powershell,
    unavailable,
)

DOMAIN = "wifi"
TITLE = "Wi-Fi"


def _wifi_adapters() -> list[dict]:
    return as_list(ps_json(
        "Get-NetAdapter -ErrorAction SilentlyContinue | "
        "Where-Object { $_.MediaType -eq 'Native 802.11' -or $_.Name -match 'Wi-?Fi|Wireless' } | "
        "Select-Object Name,Status,LinkSpeed | ConvertTo-Json -Compress"
    ))


def _wlan_interface() -> dict:
    """Parse `netsh wlan show interfaces` for SSID / signal / state."""
    ok, out = run_powershell("netsh wlan show interfaces")
    info: dict[str, str] = {}
    if not ok or not out:
        return info
    for line in out.splitlines():
        if ":" in line:
            k, _, v = line.partition(":")
            info[k.strip().lower()] = v.strip()
    return info


def investigate(ctx: ProbeContext) -> ProbeOutcome:
    if not IS_WINDOWS:
        return unavailable(DOMAIN, TITLE, "Wi-Fi probe only runs on Windows.")

    checks: list[ProbeCheck] = []
    findings: list[TroubleshooterFinding] = []

    svc = get_service("WlanSvc")
    if svc:
        running = str(svc.get("Status", "")).lower() == "running"
        checks.append(ProbeCheck(
            label="WLAN AutoConfig service",
            value=f"{svc.get('Status')} (start: {svc.get('StartType')})",
            status=Severity.healthy if running else Severity.warning,
        ))
        if not running:
            findings.append(TroubleshooterFinding(
                id="wifi_service_stopped",
                title="Wi-Fi Service (WlanSvc) Not Running",
                area="Wi-Fi",
                severity=Severity.warning,
                detected=f"WLAN AutoConfig service is {svc.get('Status')}.",
                likely_cause="Without WLAN AutoConfig, Windows can't manage Wi-Fi networks.",
                resolution_steps=[
                    "Open Services (`services.msc`) > 'WLAN AutoConfig'.",
                    "Set Startup type to Automatic and click Start.",
                    "Reconnect to your Wi-Fi network.",
                ],
                ask_ai_prompt="My WLAN AutoConfig service is stopped and Wi-Fi doesn't work. How do I fix it?",
            ))

    adapters = _wifi_adapters()
    if not adapters:
        checks.append(ProbeCheck(label="Wi-Fi adapter", value="None found", status=Severity.critical))
        findings.append(TroubleshooterFinding(
            id="wifi_no_adapter",
            title="No Wi-Fi Adapter Detected",
            area="Wi-Fi",
            severity=Severity.critical,
            detected="No wireless network adapter was found.",
            likely_cause="The Wi-Fi driver is missing/disabled, or the radio is off in BIOS or via a hardware switch.",
            resolution_steps=[
                "Check for a physical Wi-Fi switch or Fn key and turn the radio on.",
                "Turn off Airplane mode (Settings > Network & internet).",
                "Device Manager > Network adapters: enable the wireless adapter or install its driver.",
                "Verify the wireless card is enabled in BIOS/UEFI.",
            ],
            ask_ai_prompt="Windows shows no Wi-Fi adapter. How do I get the wireless adapter back?",
        ))
    else:
        for ad in adapters:
            status = str(ad.get("Status", ""))
            checks.append(ProbeCheck(
                label=f"Wi-Fi adapter: {ad.get('Name')}",
                value=f"{status} · {ad.get('LinkSpeed','?')}",
                status=Severity.healthy if status.lower() == "up" else Severity.warning,
            ))

    iface = _wlan_interface()
    state = iface.get("state", "")
    ssid = iface.get("ssid", "")
    signal = iface.get("signal", "")
    if state:
        checks.append(ProbeCheck(
            label="Wi-Fi connection",
            value=f"{state}" + (f" → {ssid}" if ssid else ""),
            status=Severity.healthy if state.lower() == "connected" else Severity.warning,
        ))
    if signal:
        m = re.search(r"(\d+)", signal)
        pct = int(m.group(1)) if m else None
        sev = Severity.healthy
        if pct is not None and pct < 40:
            sev = Severity.warning
        checks.append(ProbeCheck(label="Signal strength", value=signal, status=sev))
        if pct is not None and pct < 40:
            findings.append(TroubleshooterFinding(
                id="wifi_weak_signal",
                title="Weak Wi-Fi Signal",
                area="Wi-Fi",
                severity=Severity.warning,
                detected=f"Wi-Fi signal strength is {signal}.",
                likely_cause="Distance from the router, walls, or interference is weakening the signal.",
                resolution_steps=[
                    "Move closer to the router or remove obstructions.",
                    "Switch to the 5 GHz band if available.",
                    "Restart the router; reduce nearby 2.4 GHz interference.",
                    "Update the Wi-Fi adapter driver.",
                ],
                ask_ai_prompt="My Wi-Fi signal is weak. How do I improve the connection?",
            ))

    return ProbeOutcome(
        result=ProbeResult(domain=DOMAIN, title=TITLE, available=True, checks=checks),
        findings=findings,
    )
