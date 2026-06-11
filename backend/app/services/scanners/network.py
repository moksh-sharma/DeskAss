"""Network scanner: interfaces, IP config, Wi-Fi, proxy, ports, connectivity."""
from __future__ import annotations

import socket

import psutil

from app.services.scanners.base import (
    IS_WINDOWS,
    as_list,
    cim,
    ps_json,
    run_powershell,
    safe_scan,
)


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


def _wifi() -> dict:
    """Current Wi-Fi link details (SSID, signal, channel, radio) via netsh."""
    if not IS_WINDOWS:
        return {"connected": False}
    ok, out = run_powershell("netsh wlan show interfaces", timeout=15.0)
    if not ok or not out:
        return {"connected": False}
    fields: dict[str, str] = {}
    for line in out.splitlines():
        if ":" not in line:
            continue
        key, _, val = line.partition(":")
        fields.setdefault(key.strip().lower(), val.strip())
    if (fields.get("state") or "").lower() != "connected":
        return {"connected": False}
    signal = fields.get("signal", "").replace("%", "")
    return {
        "connected": True,
        "ssid": fields.get("ssid"),
        "signal_pct": int(signal) if signal.isdigit() else None,
        "radio_type": fields.get("radio type"),
        "band": fields.get("band"),
        "channel": fields.get("channel"),
        "authentication": fields.get("authentication"),
        "receive_rate_mbps": fields.get("receive rate (mbps)"),
        "transmit_rate_mbps": fields.get("transmit rate (mbps)"),
    }


def _proxy() -> dict:
    rec = ps_json(
        "Get-ItemProperty 'HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Internet Settings' "
        "-ErrorAction SilentlyContinue | Select-Object ProxyEnable,ProxyServer,AutoConfigURL | "
        "ConvertTo-Json -Compress",
        timeout=15.0,
    ) or {}
    return {
        "proxy_enabled": bool(rec.get("ProxyEnable")),
        "proxy_server": rec.get("ProxyServer"),
        "pac_url": rec.get("AutoConfigURL"),
    }


# Well-known ports that matter in an enterprise exposure review.
_NOTABLE_PORTS = {
    21: "FTP", 22: "SSH", 23: "Telnet", 25: "SMTP", 80: "HTTP", 135: "RPC",
    139: "NetBIOS", 443: "HTTPS", 445: "SMB", 1433: "SQL Server", 3306: "MySQL",
    3389: "RDP", 5432: "PostgreSQL", 5900: "VNC", 5985: "WinRM", 5986: "WinRM-S",
    8080: "HTTP-alt", 27017: "MongoDB", 6379: "Redis", 9200: "Elasticsearch",
}


def _connections() -> dict:
    """Listening ports + connection counts (exposure surface)."""
    listening: dict[int, str | None] = {}
    established = 0
    try:
        for c in psutil.net_connections(kind="inet"):
            if c.status == psutil.CONN_LISTEN and c.laddr:
                port = c.laddr.port
                if port not in listening:
                    name = None
                    try:
                        if c.pid:
                            name = psutil.Process(c.pid).name()
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        pass
                    listening[port] = name
            elif c.status == psutil.CONN_ESTABLISHED:
                established += 1
    except (psutil.AccessDenied, OSError):
        return {"available": False, "note": "Connection table not readable without admin rights."}

    notable = [
        {"port": p, "service": _NOTABLE_PORTS[p], "process": listening[p]}
        for p in sorted(listening) if p in _NOTABLE_PORTS
    ]
    return {
        "available": True,
        "listening_port_count": len(listening),
        "established_count": established,
        "notable_listening": notable,
        "listening_ports": [
            {"port": p, "process": n} for p, n in sorted(listening.items())
        ][:60],
    }


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
    from concurrent.futures import ThreadPoolExecutor

    jobs = {
        "interfaces": _interfaces,
        "adapter_types": _adapter_types,
        "ip_config": _ip_config,
        "wifi": _wifi,
        "proxy": _proxy,
        "connections": _connections,
        "connectivity": _connectivity,
    }
    out: dict = {}
    with ThreadPoolExecutor(max_workers=len(jobs)) as pool:
        futures = {pool.submit(fn): key for key, fn in jobs.items()}
        for fut, key in futures.items():
            try:
                out[key] = fut.result(timeout=45)
            except Exception as exc:  # pragma: no cover
                out[key] = {"error": str(exc)}
    return out
