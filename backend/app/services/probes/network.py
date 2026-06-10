"""Network live probe pack: connectivity, gateway, DNS, adapters."""
from __future__ import annotations

import socket
import subprocess

from app.models.schemas import ProbeCheck, ProbeResult, Severity, TroubleshooterFinding
from app.services.probes.base import IS_WINDOWS, ProbeContext, ProbeOutcome, as_list, ps_json

DOMAIN = "network"
TITLE = "Network & Internet"


def _internet_ok(host: str = "8.8.8.8", port: int = 53, timeout: float = 1.5) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _dns_ok(name: str = "www.microsoft.com") -> bool:
    try:
        socket.gethostbyname(name)
        return True
    except OSError:
        return False


def _default_gateway() -> str | None:
    if not IS_WINDOWS:
        return None
    data = ps_json(
        "(Get-NetRoute -DestinationPrefix '0.0.0.0/0' -ErrorAction SilentlyContinue | "
        "Sort-Object RouteMetric | Select-Object -First 1).NextHop | ConvertTo-Json -Compress"
    )
    if isinstance(data, str):
        return data
    return None


def _ping(host: str) -> bool:
    if not host:
        return False
    try:
        flag = "-n" if IS_WINDOWS else "-c"
        completed = subprocess.run(
            ["ping", flag, "1", "-w", "1000", host] if IS_WINDOWS else ["ping", flag, "1", host],
            capture_output=True, text=True, timeout=6.0,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return completed.returncode == 0
    except Exception:
        return False


def _adapters() -> list[dict]:
    if not IS_WINDOWS:
        return []
    return as_list(ps_json(
        "Get-NetAdapter -ErrorAction SilentlyContinue | "
        "Select-Object Name,Status,LinkSpeed,MediaType | ConvertTo-Json -Compress"
    ))


def investigate(ctx: ProbeContext) -> ProbeOutcome:
    checks: list[ProbeCheck] = []
    findings: list[TroubleshooterFinding] = []

    internet = _internet_ok()
    dns = _dns_ok() if internet else False
    gateway = _default_gateway()
    gw_ok = _ping(gateway) if gateway else False

    checks.append(ProbeCheck(
        label="Internet reachable",
        value="Yes" if internet else "No",
        status=Severity.healthy if internet else Severity.critical,
    ))
    checks.append(ProbeCheck(
        label="DNS resolution",
        value="Working" if dns else ("Failing" if internet else "Not tested"),
        status=Severity.healthy if dns else (Severity.warning if internet else Severity.info),
    ))
    if gateway:
        checks.append(ProbeCheck(
            label="Default gateway",
            value=f"{gateway} ({'reachable' if gw_ok else 'no reply'})",
            status=Severity.healthy if gw_ok else Severity.warning,
        ))

    up_adapters = []
    for ad in _adapters():
        name = ad.get("Name")
        status = str(ad.get("Status", ""))
        is_up = status.lower() == "up"
        if is_up:
            up_adapters.append(name)
        checks.append(ProbeCheck(
            label=f"Adapter: {name}",
            value=f"{status} · {ad.get('LinkSpeed','?')}",
            status=Severity.healthy if is_up else Severity.info,
        ))

    if not internet:
        if gateway and not gw_ok:
            findings.append(TroubleshooterFinding(
                id="net_gateway_unreachable",
                title="Can't Reach the Router/Gateway",
                area="Network",
                severity=Severity.critical,
                detected=f"No internet, and the default gateway {gateway} did not respond to ping.",
                likely_cause="The PC is disconnected from the local network - Wi-Fi dropped, cable unplugged, "
                "or the router is down.",
                resolution_steps=[
                    "Check Wi-Fi is connected or the Ethernet cable is firmly seated.",
                    "Reconnect to your network: Settings > Network & internet.",
                    "Renew the address (elevated): `ipconfig /release` then `ipconfig /renew`.",
                    "Reboot the router/modem (power off 30 seconds).",
                ],
                ask_ai_prompt="My PC can't reach the router/gateway and has no internet. How do I fix the local connection?",
            ))
        elif gateway and gw_ok:
            findings.append(TroubleshooterFinding(
                id="net_no_internet_lan_ok",
                title="Local Network OK but No Internet",
                area="Network",
                severity=Severity.critical,
                detected=f"The gateway {gateway} responds, but the internet (8.8.8.8) is unreachable.",
                likely_cause="The problem is upstream of your PC - the router's internet (WAN) link or your ISP.",
                resolution_steps=[
                    "Test another device on the same network - if it's also offline, the router/ISP is the cause.",
                    "Reboot the router/modem (power off 30 seconds).",
                    "Flush DNS (elevated): `ipconfig /flushdns`.",
                    "If only this PC is affected, temporarily disable VPN/proxy and retest.",
                ],
                ask_ai_prompt="My local network works but there's no internet access. What should I check?",
            ))
        else:
            findings.append(TroubleshooterFinding(
                id="net_no_internet",
                title="No Internet Connectivity",
                area="Network",
                severity=Severity.critical,
                detected="The PC could not reach the internet during the scan.",
                likely_cause="Wi-Fi/Ethernet is down, or DHCP/DNS failed.",
                resolution_steps=[
                    "Confirm Wi-Fi is on / Ethernet connected; check other devices.",
                    "Run: Settings > Network & internet > Advanced > Network reset (last resort).",
                    "Renew the connection: `ipconfig /release`, `ipconfig /renew`, `ipconfig /flushdns`.",
                    "Reset the stack: `netsh winsock reset` and `netsh int ip reset`, then restart.",
                ],
                ask_ai_prompt="My PC has no internet. How do I diagnose and fix it step by step?",
            ))
    elif not dns:
        findings.append(TroubleshooterFinding(
            id="net_dns_failing",
            title="DNS Resolution Is Failing",
            area="Network",
            severity=Severity.warning,
            detected="The internet is reachable by IP, but domain names are not resolving.",
            likely_cause="A bad/temporary DNS server, stale DNS cache, or a misconfigured DNS setting.",
            resolution_steps=[
                "Flush the DNS cache (elevated): `ipconfig /flushdns`.",
                "Set a public DNS: Settings > Network & internet > your adapter > DNS to 8.8.8.8 / 1.1.1.1.",
                "Disable VPN/proxy temporarily and retest.",
                "Restart the 'DNS Client' service if names still fail.",
            ],
            ask_ai_prompt="I have internet by IP but DNS names won't resolve. How do I fix DNS?",
        ))

    if not up_adapters and IS_WINDOWS and _adapters():
        findings.append(TroubleshooterFinding(
            id="net_no_active_adapter",
            title="No Active Network Adapter",
            area="Network",
            severity=Severity.warning,
            detected="No network adapter is in the 'Up' state.",
            likely_cause="All adapters are disabled or disconnected.",
            resolution_steps=[
                "Enable your adapter: Settings > Network & internet > Advanced network settings.",
                "For Wi-Fi, turn the radio on and reconnect; for Ethernet, reseat the cable.",
                "Update the network adapter driver in Device Manager.",
            ],
            ask_ai_prompt="None of my network adapters are active. How do I re-enable networking?",
        ))

    return ProbeOutcome(
        result=ProbeResult(domain=DOMAIN, title=TITLE, available=True, checks=checks),
        findings=findings,
    )
