"""Network scanner: interfaces, IP config, connectivity and latency tests."""
from __future__ import annotations

import socket

import psutil

from app.services.scanners.base import IS_WINDOWS, as_list, cim, ps_json, safe_scan


def _interfaces() -> list[dict]:
    out = []
    addrs = psutil.net_if_addrs()
    stats = psutil.net_if_stats()
    for name, addr_list in addrs.items():
        st = stats.get(name)
        ipv4 = next((a.address for a in addr_list if a.family == socket.AF_INET), None)
        mac = next((a.address for a in addr_list if a.family == psutil.AF_LINK), None)
        out.append({
            "name": name,
            "ipv4": ipv4,
            "mac": mac,
            "is_up": st.isup if st else None,
            "speed_mbps": st.speed if st else None,
        })
    return out


def _ip_config() -> dict:
    if not IS_WINDOWS:
        return {}
    cfg = as_list(ps_json(
        "Get-NetIPConfiguration -ErrorAction SilentlyContinue | Select-Object "
        "InterfaceAlias,@{N='IPv4';E={$_.IPv4Address.IPAddress}},"
        "@{N='Gateway';E={$_.IPv4DefaultGateway.NextHop}},"
        "@{N='DNS';E={($_.DNSServer | Where-Object {$_.AddressFamily -eq 2}).ServerAddresses -join ', '}} | "
        "ConvertTo-Json -Compress",
        timeout=20.0,
    ))
    active = [c for c in cfg if c.get("Gateway")]
    primary = active[0] if active else (cfg[0] if cfg else {})
    return {
        "interface": primary.get("InterfaceAlias"),
        "ip_address": primary.get("IPv4"),
        "gateway": primary.get("Gateway"),
        "dns_servers": primary.get("DNS"),
        "all_configs": cfg,
    }


def _adapter_types() -> dict:
    wifi = ethernet = vpn = bluetooth = []
    rows = cim("Win32_NetworkAdapter", "Name,NetConnectionID,AdapterType,PhysicalAdapter",
               where="NetEnabled=True")
    names = [r.get("Name") or r.get("NetConnectionID") or "" for r in rows]
    return {
        "wifi": [n for n in names if "wi-fi" in n.lower() or "wireless" in n.lower() or "802.11" in n.lower()],
        "ethernet": [n for n in names if "ethernet" in n.lower()],
        "vpn": [n for n in names if any(k in n.lower() for k in ("vpn", "anyconnect", "fortinet", "wireguard", "tap-"))],
        "bluetooth": [n for n in names if "bluetooth" in n.lower()],
    }


def _tcp_check(host: str, port: int, timeout: float = 2.0) -> tuple[bool, float | None]:
    import time
    start = time.perf_counter()
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True, round((time.perf_counter() - start) * 1000, 1)
    except OSError:
        return False, None


def _dns_check(host: str) -> tuple[bool, float | None]:
    import time
    start = time.perf_counter()
    try:
        socket.gethostbyname(host)
        return True, round((time.perf_counter() - start) * 1000, 1)
    except OSError:
        return False, None


def _connectivity() -> dict:
    internet_ok, internet_ms = _tcp_check("8.8.8.8", 53)
    dns_ok, dns_ms = _dns_check("www.microsoft.com")
    google_ok, google_ms = _tcp_check("www.google.com", 443)
    ms_ok, ms_ms = _tcp_check("www.microsoft.com", 443)
    return {
        "internet": internet_ok,
        "internet_latency_ms": internet_ms,
        "dns_resolution": dns_ok,
        "dns_response_ms": dns_ms,
        "google_reachable": google_ok,
        "google_latency_ms": google_ms,
        "microsoft_reachable": ms_ok,
        "microsoft_latency_ms": ms_ms,
    }


@safe_scan("network")
def scan() -> dict:
    return {
        "interfaces": _interfaces(),
        "adapter_types": _adapter_types(),
        "ip_config": _ip_config(),
        "connectivity": _connectivity(),
    }
