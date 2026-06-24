"""External hardware discovery & inventory.

Discovers, identifies, and reports the health of every external/peripheral
device connected to the machine: USB devices, monitors, printers, scanners,
audio devices, cameras, Bluetooth devices, docking stations, network hardware,
external storage, Thunderbolt and PCI/expansion cards.

Every probe is defensive (PowerShell/CIM failures degrade to empty), runs on a
worker thread, and the assembled report includes a per-device health verdict and
a computer->peripheral relationship map.
"""
from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from app.services.scanners.physical_device import (
    is_internal_monitor,
    is_usb_infrastructure,
    is_virtual_audio,
    is_virtual_camera,
    is_virtual_printer,
)
from app.services.scanners.base import (
    IS_WINDOWS,
    as_list,
    bytes_to_gb,
    cim,
    ps_json,
    safe_scan,
    to_int,
)

# --------------------------------------------------------------------------- #
#  Classification helpers
# --------------------------------------------------------------------------- #

# Map a PnP class (and instance hints) to a friendly USB device type.
_USB_TYPE_BY_CLASS = {
    "DiskDrive": "External Storage",
    "USBSTOR": "USB Flash Drive",
    "Net": "USB Network Adapter",
    "Camera": "USB Camera",
    "Image": "USB Scanner / Imaging",
    "Media": "USB Audio Device",
    "AudioEndpoint": "USB Audio Device",
    "Keyboard": "USB Keyboard",
    "Mouse": "USB Mouse",
    "HIDClass": "USB HID / Input",
    "Printer": "USB Printer",
    "PrintQueue": "USB Printer",
    "SmartCardReader": "USB Smart Card Reader",
    "SmartCardFilter": "USB Smart Card Reader",
    "Bluetooth": "USB Bluetooth Adapter",
    "WPD": "USB Portable Device",
    "Biometric": "USB Biometric Device",
}

# Name patterns that refine the device type when the class is generic.
_USB_TYPE_BY_NAME = [
    (re.compile(r"\bssd\b", re.I), "External SSD"),
    (re.compile(r"\bhdd\b|hard disk|hard drive", re.I), "External HDD"),
    (re.compile(r"flash|pendrive|pen drive|thumb|usb drive|memory stick", re.I), "USB Flash Drive"),
    (re.compile(r"\bhub\b", re.I), "USB Hub"),
    (re.compile(r"wi-?fi|wireless.*adapter|802\.11", re.I), "USB WiFi Adapter"),
    (re.compile(r"bluetooth", re.I), "USB Bluetooth Adapter"),
    (re.compile(r"webcam|camera", re.I), "USB Camera"),
    (re.compile(r"microphone|\bmic\b", re.I), "USB Microphone"),
    (re.compile(r"headset|headphone|speaker|audio", re.I), "USB Audio Device"),
    (re.compile(r"keyboard", re.I), "USB Keyboard"),
    (re.compile(r"mouse|trackpad|touchpad", re.I), "USB Mouse"),
    (re.compile(r"printer", re.I), "USB Printer"),
    (re.compile(r"scanner", re.I), "USB Scanner"),
    (re.compile(r"smart\s*card|ccid", re.I), "USB Smart Card Reader"),
    (re.compile(r"security key|fido|yubikey|titan", re.I), "USB Security Key"),
    (re.compile(r"dongle|receiver", re.I), "USB Dongle"),
    (re.compile(r"dock|docking", re.I), "Docking Station"),
]

_VIDPID_RE = re.compile(r"VID_([0-9A-Fa-f]{4}).*?PID_([0-9A-Fa-f]{4})", re.I)


def _classify_usb(name: str, cls: str, instance_id: str) -> str:
    blob = f"{name} {instance_id}"
    for pattern, label in _USB_TYPE_BY_NAME:
        if pattern.search(blob):
            return label
    return _USB_TYPE_BY_CLASS.get(cls, "USB Device")


def _parse_vid_pid(instance_id: str) -> tuple[str | None, str | None]:
    m = _VIDPID_RE.search(instance_id or "")
    if not m:
        return None, None
    return m.group(1).upper(), m.group(2).upper()


def _parse_serial(instance_id: str) -> str | None:
    # USB\VID_xxxx&PID_yyyy\<serial>  - last path segment, when not a generated id.
    parts = (instance_id or "").split("\\")
    if len(parts) >= 3:
        serial = parts[-1]
        # Generated ids contain '&' (e.g. 7&1a2b3c&0&1); real serials usually don't.
        if "&" not in serial and serial:
            return serial
    return None


def _status_health(status: str | None, problem: object) -> str:
    """Map a PnP status/problem code to a device-health verdict."""
    s = (status or "").strip().lower()
    try:
        code = int(problem) if problem is not None else 0
    except (TypeError, ValueError):
        code = 0
    if code == 22 or s == "disabled":
        return "Disabled"
    if code == 28:
        return "Driver Missing"
    if code == 45 or s == "unknown":
        return "Disconnected"
    if s == "error" or code not in (0, 45):
        return "Communication Issue"
    if s == "ok":
        return "Connected"
    return "Connected" if s in ("", "ok") else "Communication Issue"


# --------------------------------------------------------------------------- #
#  Signed-driver lookup (driver version/date by device id)
# --------------------------------------------------------------------------- #
def _driver_map() -> dict[str, dict]:
    """Map uppercased DeviceID -> {version, date, provider} from signed drivers."""
    out: dict[str, dict] = {}
    for d in cim(
        "Win32_PnPSignedDriver",
        "DeviceID,DriverVersion,DriverDate,DriverProviderName",
        timeout=30.0,
    ):
        dev_id = (d.get("DeviceID") or "").upper()
        if not dev_id:
            continue
        out[dev_id] = {
            "driver_version": d.get("DriverVersion"),
            "driver_provider": d.get("DriverProviderName"),
        }
    return out


# --------------------------------------------------------------------------- #
#  USB devices
# --------------------------------------------------------------------------- #
def _usb_devices(drivers: dict[str, dict]) -> dict:
    rows = as_list(ps_json(
        "Get-PnpDevice -PresentOnly -ErrorAction SilentlyContinue | "
        "Where-Object { $_.InstanceId -match '^USB' -or $_.InstanceId -match '^USBSTOR' } | "
        "Select-Object FriendlyName,Class,Manufacturer,InstanceId,Service,"
        "@{N='Status';E={$_.Status.ToString()}},@{N='Problem';E={[int]$_.Problem}} | "
        "ConvertTo-Json -Compress",
        timeout=30.0,
    ))
    devices: list[dict] = []
    seen: set[str] = set()
    for r in rows:
        name = r.get("FriendlyName")
        instance = r.get("InstanceId") or ""
        # Skip root hubs / generic controllers that aren't user peripherals.
        if not name:
            continue
        if re.search(r"root hub|host controller|generic usb hub|composite device", name, re.I):
            # Keep hubs but mark type; drop only host controllers/composite shells.
            if re.search(r"host controller|composite device", name, re.I):
                continue
        vid, pid = _parse_vid_pid(instance)
        serial = _parse_serial(instance)
        dedupe_key = f"{name}|{vid}|{pid}|{serial}"
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        drv = drivers.get(instance.upper(), {})
        health = _status_health(r.get("Status"), r.get("Problem"))
        dtype = _classify_usb(name, r.get("Class") or "", instance)
        is_infra = is_usb_infrastructure(name, dtype)
        devices.append({
            "name": name,
            "type": dtype,
            "manufacturer": (r.get("Manufacturer") or "").strip() or None,
            "vendor_id": vid,
            "product_id": pid,
            "serial_number": serial,
            "driver": r.get("Service"),
            "driver_version": drv.get("driver_version"),
            "device_status": r.get("Status"),
            "health": health,
            "connected": health not in ("Disconnected",),
            "is_infrastructure": is_infra,
            "is_peripheral": not is_infra,
            "is_physical": not is_infra,
            "is_virtual": False,
        })
    devices.sort(key=lambda d: (d.get("type") or "", d.get("name") or ""))
    type_counts: dict[str, int] = {}
    for d in devices:
        type_counts[d["type"]] = type_counts.get(d["type"], 0) + 1
    peripherals = [d for d in devices if d.get("is_peripheral")]
    connected_peripherals = [d for d in peripherals if d.get("connected")]
    return {
        "devices": devices,
        "count": len(devices),
        "peripheral_count": len(peripherals),
        "connected_peripheral_count": len(connected_peripherals),
        "has_connected_peripherals": bool(connected_peripherals),
        "type_counts": type_counts,
        "problem_devices": [d for d in peripherals if d["health"] not in ("Connected",)],
    }


# --------------------------------------------------------------------------- #
#  Monitors / displays
# --------------------------------------------------------------------------- #
_CONNECTION_TYPE = {
    0: "VGA", 1: "S-Video", 2: "Composite", 3: "Component", 4: "DVI", 5: "HDMI",
    6: "LVDS", 8: "D-Jpn", 9: "SDI", 10: "DisplayPort", 11: "DisplayPort",
    12: "DisplayPort (embedded)", 13: "UDI", 14: "UDI (embedded)", 15: "SDTV dongle",
    16: "Miracast", 17: "Indirect wired", -2: "Uninitialized", -1: "Other", 2147483648: "Internal",
}


def _monitors() -> dict:
    decode = (
        "[System.Text.Encoding]::ASCII.GetString([byte[]]@($_.{0} | "
        "Where-Object {{$_ -ge 32 -and $_ -le 126}})).Trim()"
    )
    ids = as_list(ps_json(
        "Get-CimInstance -Namespace root/wmi -ClassName WmiMonitorID -ErrorAction SilentlyContinue | "
        "ForEach-Object { [PSCustomObject]@{ "
        f"Manufacturer = {decode.format('ManufacturerName')}; "
        f"Model = {decode.format('UserFriendlyName')}; "
        f"Serial = {decode.format('SerialNumberID')}; "
        "Year = $_.YearOfManufacture; Instance = $_.InstanceName; Active = $_.Active } } | "
        "ConvertTo-Json -Compress",
        timeout=20.0,
    ))
    # Connection technology per monitor instance.
    conn_rows = as_list(ps_json(
        "Get-CimInstance -Namespace root/wmi -ClassName WmiMonitorConnectionParams "
        "-ErrorAction SilentlyContinue | "
        "Select-Object InstanceName,VideoOutputTechnology | ConvertTo-Json -Compress",
        timeout=20.0,
    ))
    conn_by_instance = {
        (c.get("InstanceName") or ""): _CONNECTION_TYPE.get(
            to_int(c.get("VideoOutputTechnology")), None
        )
        for c in conn_rows
    }
    # Current mode (resolution/refresh) from the active video controllers.
    modes = []
    for v in cim("Win32_VideoController",
                 "Name,CurrentHorizontalResolution,CurrentVerticalResolution,CurrentRefreshRate"):
        if v.get("CurrentHorizontalResolution"):
            modes.append({
                "resolution": f"{v.get('CurrentHorizontalResolution')}x{v.get('CurrentVerticalResolution')}",
                "refresh_hz": to_int(v.get("CurrentRefreshRate")),
            })

    monitors: list[dict] = []
    for i, r in enumerate(ids):
        instance = r.get("Instance") or ""
        mode = modes[i] if i < len(modes) else (modes[0] if modes else {})
        conn = conn_by_instance.get(instance)
        is_internal = is_internal_monitor(conn)
        monitors.append({
            "manufacturer": r.get("Manufacturer") or None,
            "model": r.get("Model") or None,
            "serial_number": (r.get("Serial") or "").strip("0") or r.get("Serial") or None,
            "year_of_manufacture": to_int(r.get("Year")),
            "connection_type": conn,
            "resolution": (mode or {}).get("resolution"),
            "refresh_rate_hz": (mode or {}).get("refresh_hz"),
            "active": bool(r.get("Active", True)),
            "is_internal": is_internal,
            "is_external": not is_internal,
            "is_physical": True,
            "is_virtual": False,
            "connected": bool(r.get("Active", True)),
        })
    external = [m for m in monitors if m.get("is_external")]
    return {
        "monitors": monitors,
        "count": len(monitors),
        "external_count": len(external),
        "internal_count": len(monitors) - len(external),
        "has_external_monitor": bool(external),
        "multi_monitor": len(monitors) > 1,
    }


# --------------------------------------------------------------------------- #
#  Printers
# --------------------------------------------------------------------------- #
_PRINTER_STATUS = {
    1: "Other", 2: "Unknown", 3: "Idle / Ready", 4: "Printing", 5: "Warming Up",
    6: "Stopped Printing", 7: "Offline",
}

# Software queues Windows always lists (PDF, OneNote, XPS, fax, etc.) - not hardware.
# Classification lives in physical_device.py (is_virtual_printer).


def _is_virtual_printer_row(row: dict, port: str) -> bool:
    return is_virtual_printer(
        str(row.get("Name") or ""),
        str(row.get("DriverName") or ""),
        str(port or ""),
        str(row.get("Type") or ""),
    )


def _pnp_printers() -> list[dict]:
    """USB/other printer hardware present in PnP (not software queues)."""
    return [
        {
            "name": r.get("FriendlyName"),
            "status": r.get("Status"),
            "instance_id": r.get("InstanceId"),
        }
        for r in as_list(ps_json(
            "Get-PnpDevice -Class Printer -PresentOnly -ErrorAction SilentlyContinue | "
            "Select-Object FriendlyName,Status,InstanceId | ConvertTo-Json -Compress",
            timeout=20.0,
        ))
        if str(r.get("Status") or "").upper() == "OK"
    ]


def _discover_lan_printers() -> list[dict]:
    """Probe reachable LAN neighbours for printers and resolve a display name.

    Uses TCP ports (RAW/IPP/LPD), reverse DNS, and HTTP/IPP page titles.
    """
    rows = as_list(ps_json(
        "function Resolve-PrinterName([string]$ip) { "
        "  $name = $null; "
        "  try { "
        "    $entry = [System.Net.Dns]::GetHostEntry($ip); "
        "    if ($entry.HostName -and $entry.HostName -ne $ip) { "
        "      $name = ($entry.HostName -split '\\.')[0] "
        "    } "
        "  } catch {} "
        "  if (-not $name) { "
        "    foreach ($port in @(631, 80)) { "
        "      try { "
        "        $r = Invoke-WebRequest -Uri \"http://${ip}:${port}/\" -TimeoutSec 2 "
        "          -UseBasicParsing -ErrorAction Stop; "
        "        if ($r.Content -match '<title>\\s*([^<]+)\\s*</title>') { "
        "          $t = $matches[1].Trim(); "
        "          if ($t -and $t -notmatch '^(Index|Home|Login|Printer)$') { $name = $t; break } "
        "        } "
        "      } catch {} "
        "    } "
        "  } "
        "  if (-not $name) { $name = \"Printer at $ip\" }; "
        "  return $name "
        "} "
        "$neighbors = @(Get-NetNeighbor -AddressFamily IPv4 -ErrorAction SilentlyContinue | "
        "Where-Object { $_.State -eq 'Reachable' -and $_.IPAddress -and "
        "$_.IPAddress -notmatch '^169\\.254\\.' -and $_.IPAddress -ne '127.0.0.1' } | "
        "Select-Object -ExpandProperty IPAddress -Unique | Select-Object -First 40); "
        "$ports = @(9100, 631, 515); $found = @(); "
        "foreach ($ip in $neighbors) { "
        "  foreach ($port in $ports) { "
        "    $client = New-Object System.Net.Sockets.TcpClient; "
        "    try { "
        "      $iar = $client.BeginConnect($ip, $port, $null, $null); "
        "      $ok = $iar.AsyncWaitHandle.WaitOne(300, $false); "
        "      if ($ok -and $client.Connected) { "
        "        $svc = switch ($port) { 9100 { 'RAW' } 631 { 'IPP' } 515 { 'LPD' } default { 'Printer' } }; "
        "        $found += [PSCustomObject]@{ name=(Resolve-PrinterName $ip); ip_address=$ip; "
        "          port=$port; service=$svc }; "
        "        $client.Close(); break "
        "      } "
        "    } catch {} finally { $client.Dispose() } "
        "  } "
        "} "
        "$found | ConvertTo-Json -Compress",
        timeout=60.0,
    ))
    out: list[dict] = []
    for r in rows:
        ip = r.get("ip_address")
        if not ip:
            continue
        out.append({
            "name": r.get("name") or f"Printer at {ip}",
            "ip_address": ip,
            "port": r.get("port"),
            "service": r.get("service") or "Printer",
            "source": "lan_port_scan",
        })
    return out


def _printers() -> dict:
    rows = as_list(ps_json(
        "Get-Printer -ErrorAction SilentlyContinue | "
        "Select-Object Name,@{N='Status';E={$_.PrinterStatus.ToString()}},WorkOffline,"
        "Default,Shared,Published,PortName,DriverName,"
        "@{N='Type';E={$_.Type.ToString()}},ComputerName | ConvertTo-Json -Compress",
        timeout=25.0,
    ))
    # Map driver -> version.
    driver_versions: dict[str, str] = {}
    for d in as_list(ps_json(
        "Get-PrinterDriver -ErrorAction SilentlyContinue | "
        "Select-Object Name,@{N='Version';E={$_.DriverVersion}},MajorVersion | "
        "ConvertTo-Json -Compress",
        timeout=20.0,
    )):
        if d.get("Name"):
            driver_versions[d["Name"]] = str(d.get("Version") or d.get("MajorVersion") or "")
    # Port -> network address (for network/TCP-IP printers).
    port_addr: dict[str, str] = {}
    for p in as_list(ps_json(
        "Get-PrinterPort -ErrorAction SilentlyContinue | "
        "Select-Object Name,PrinterHostAddress | ConvertTo-Json -Compress",
        timeout=20.0,
    )):
        if p.get("Name") and p.get("PrinterHostAddress"):
            port_addr[p["Name"]] = p["PrinterHostAddress"]

    pnp_usb = _pnp_printers()
    printers: list[dict] = []
    for r in rows:
        offline = bool(r.get("WorkOffline"))
        status = str(r.get("Status") or "Unknown")
        port = r.get("PortName") or ""
        is_virtual = _is_virtual_printer_row(r, port)
        is_network = (
            not is_virtual
            and (
                bool(r.get("ComputerName"))
                or str(r.get("Type", "")).lower() == "connection"
                or port.lower().startswith(("ip_", "wsd", "tcp", "http", "https"))
            )
        )
        net_addr = port_addr.get(port) or r.get("ComputerName")
        # Health verdict.
        if offline or status.lower() == "offline":
            health = "Offline"
        elif status.lower() in ("normal", "idle", "ready", "idle / ready"):
            health = "Ready"
        else:
            health = status
        if is_virtual:
            connection = "Software / Virtual"
        elif is_network:
            connection = "Network"
        else:
            connection = "Local / USB"
        printers.append({
            "name": r.get("Name"),
            "status": status,
            "offline": offline,
            "health": health,
            "is_default": bool(r.get("Default")),
            "shared": bool(r.get("Shared")),
            "is_virtual": is_virtual,
            "is_physical": not is_virtual,
            "connection": connection,
            "network_address": net_addr,
            "port": port,
            "driver": r.get("DriverName"),
            "driver_version": driver_versions.get(r.get("DriverName") or ""),
        })
    # Spooler service state (no printing possible without it).
    spooler = ps_json(
        "Get-Service -Name Spooler -ErrorAction SilentlyContinue | "
        "Select-Object @{N='Status';E={$_.Status.ToString()}} | ConvertTo-Json -Compress"
    )
    spooler_running = bool(spooler) and str(
        (spooler if isinstance(spooler, dict) else {}).get("Status", "")
    ).lower() == "running"
    # Pending print jobs.
    queued = ps_json(
        "(Get-Printer -ErrorAction SilentlyContinue | ForEach-Object { "
        "Get-PrintJob -PrinterName $_.Name -ErrorAction SilentlyContinue }).Count | ConvertTo-Json -Compress"
    )
    physical = [p for p in printers if p.get("is_physical")]
    virtual = [p for p in printers if p.get("is_virtual")]
    physical_ready = [
        p for p in physical
        if p.get("health") in ("Ready", "Idle / Ready") and not p.get("offline")
    ]
    network_installed = [p for p in physical if p.get("connection") == "Network"]
    local_installed = [p for p in physical if p.get("connection") == "Local / USB"]
    installed_net_ips = {
        str(p.get("network_address") or "").strip()
        for p in network_installed
        if p.get("network_address")
    }
    discovered = _discover_lan_printers()
    discovered_new = [
        d for d in discovered
        if str(d.get("ip_address") or "").strip() not in installed_net_ips
    ]
    network_available = list(network_installed) + [
        {
            "name": d.get("name") or f"Printer at {d.get('ip_address')}",
            "connection": "Network (discovered, not installed)",
            "network_address": d.get("ip_address"),
            "port": d.get("port"),
            "service": d.get("service"),
            "health": "Reachable",
            "is_physical": True,
            "is_virtual": False,
            "is_discovered": True,
        }
        for d in discovered_new
    ]
    return {
        "printers": printers,
        "count": len(printers),
        "physical_count": len(physical),
        "virtual_count": len(virtual),
        "physical_ready_count": len(physical_ready),
        "has_physical_printer": bool(physical),
        "has_connected_physical_printer": bool(physical_ready),
        "pnp_usb_printers": pnp_usb,
        "offline_count": sum(1 for p in physical if p["health"] == "Offline"),
        "spooler_running": spooler_running,
        "queued_jobs": to_int(queued) or 0,
        "network_installed_count": len(network_installed),
        "network_discovered_count": len(discovered_new),
        "network_available_count": len(network_available),
        "local_installed_count": len(local_installed),
        "network_installed": network_installed,
        "network_discovered": discovered_new,
        "network_available": network_available,
    }


# --------------------------------------------------------------------------- #
#  Scanners (imaging)
# --------------------------------------------------------------------------- #
def _scanners() -> dict:
    rows = as_list(ps_json(
        "Get-PnpDevice -Class Image -PresentOnly -ErrorAction SilentlyContinue | "
        "Select-Object FriendlyName,Manufacturer,"
        "@{N='Status';E={$_.Status.ToString()}},@{N='Problem';E={[int]$_.Problem}} | "
        "ConvertTo-Json -Compress",
        timeout=20.0,
    ))
    scanners: list[dict] = []
    for r in rows:
        name = r.get("FriendlyName")
        if not name:
            continue
        health = _status_health(r.get("Status"), r.get("Problem"))
        is_virtual = is_virtual_camera(name)
        scanners.append({
            "name": name,
            "manufacturer": (r.get("Manufacturer") or "").strip() or None,
            "driver_status": r.get("Status"),
            "health": health,
            "connected": health != "Disconnected",
            "is_virtual": is_virtual,
            "is_physical": not is_virtual,
        })
    physical = [s for s in scanners if s.get("is_physical")]
    connected = [s for s in physical if s.get("connected")]
    return {
        "scanners": scanners,
        "count": len(scanners),
        "physical_count": len(physical),
        "connected_physical_count": len(connected),
        "has_connected_physical_scanner": bool(connected),
    }


# --------------------------------------------------------------------------- #
#  Audio devices (input / output)
# --------------------------------------------------------------------------- #
_INPUT_RE = re.compile(r"microphone|mic array|\bmic\b|input|capture|line in", re.I)


def _audio_devices() -> dict:
    rows = as_list(ps_json(
        "Get-PnpDevice -Class AudioEndpoint -PresentOnly -ErrorAction SilentlyContinue | "
        "Select-Object FriendlyName,@{N='Status';E={$_.Status.ToString()}},"
        "@{N='Problem';E={[int]$_.Problem}} | ConvertTo-Json -Compress",
        timeout=20.0,
    ))
    inputs: list[dict] = []
    outputs: list[dict] = []
    for r in rows:
        name = r.get("FriendlyName")
        if not name:
            continue
        health = _status_health(r.get("Status"), r.get("Problem"))
        is_virtual = is_virtual_audio(name)
        entry = {
            "name": name,
            "status": r.get("Status"),
            "health": health,
            "working": health == "Connected",
            "is_virtual": is_virtual,
            "is_physical": not is_virtual,
            "connected": health == "Connected",
        }
        (inputs if _INPUT_RE.search(name) else outputs).append(entry)
    physical_inputs = [d for d in inputs if d.get("is_physical")]
    physical_outputs = [d for d in outputs if d.get("is_physical")]
    return {
        "input_devices": inputs,
        "output_devices": outputs,
        "input_count": len(inputs),
        "output_count": len(outputs),
        "physical_input_count": len(physical_inputs),
        "physical_output_count": len(physical_outputs),
        "virtual_input_count": len(inputs) - len(physical_inputs),
        "virtual_output_count": len(outputs) - len(physical_outputs),
        "has_connected_physical_input": any(d.get("working") for d in physical_inputs),
        "has_connected_physical_output": any(d.get("working") for d in physical_outputs),
        "disabled_count": sum(1 for d in inputs + outputs if d["health"] == "Disabled"),
    }


# --------------------------------------------------------------------------- #
#  Cameras / webcams
# --------------------------------------------------------------------------- #
def _cameras() -> dict:
    rows = as_list(ps_json(
        "Get-PnpDevice -PresentOnly -ErrorAction SilentlyContinue | "
        "Where-Object { $_.Class -eq 'Camera' -or $_.FriendlyName -match 'camera|webcam' } | "
        "Select-Object FriendlyName,Manufacturer,"
        "@{N='Status';E={$_.Status.ToString()}},@{N='Problem';E={[int]$_.Problem}} | "
        "ConvertTo-Json -Compress",
        timeout=20.0,
    ))
    cameras: list[dict] = []
    for r in rows:
        name = r.get("FriendlyName")
        if not name:
            continue
        health = _status_health(r.get("Status"), r.get("Problem"))
        is_virtual = is_virtual_camera(name)
        cameras.append({
            "name": name,
            "manufacturer": (r.get("Manufacturer") or "").strip() or None,
            "status": r.get("Status"),
            "health": health,
            "connected": health != "Disconnected",
            "is_virtual": is_virtual,
            "is_physical": not is_virtual,
        })
    physical = [c for c in cameras if c.get("is_physical")]
    connected = [c for c in physical if c.get("connected")]
    return {
        "cameras": cameras,
        "count": len(cameras),
        "physical_count": len(physical),
        "virtual_count": len(cameras) - len(physical),
        "connected_physical_count": len(connected),
        "has_connected_physical_camera": bool(connected),
    }


# --------------------------------------------------------------------------- #
#  Bluetooth devices
# --------------------------------------------------------------------------- #
# Windows profile/service nodes that are not end-user peripherals.
_BT_SERVICE_RE = re.compile(
    r"(?i)\b("
    r"avrcp\s*transport|object\s*push|phonebook\s*access|audio\s*gateway|"
    r"personal\s*area\s*network|sim\s*access|hands-?free|headset\s*audio|"
    r"nap\s*service|pse\s*service|bpp\s*service|dun\s*service|"
    r"ftp\s*service|sync\s*service|obex|serial\s*port|"
    r"low\s*energy\s*gatt|device\s*information\s*service|"
    r"generic\s*attribute|generic\s*access"
    r")\b",
)

_BT_NAME_SUFFIXES = (
    " Avrcp Transport",
    " Avrcp",
    " Hands-Free AG",
    " Hands-Free",
    " Hands Free",
    " Stereo",
    " Headset",
)


def _bt_is_service_entry(name: str) -> bool:
    return bool(_BT_SERVICE_RE.search(name or ""))


def _bt_base_name(name: str) -> str:
    """Normalize a Bluetooth friendly name for dedupe / connection matching."""
    n = (name or "").strip()
    for suffix in _BT_NAME_SUFFIXES:
        if n.lower().endswith(suffix.lower()):
            n = n[: -len(suffix)].strip()
    return n.lower()


def _bt_winrt_connected_bases() -> set[str] | None:
    """Return normalized names of Bluetooth devices Windows reports as connected now."""
    try:
        import asyncio

        from winrt.windows.devices.bluetooth import BluetoothConnectionStatus, BluetoothDevice
        from winrt.windows.devices.enumeration import DeviceInformation

        async def _query() -> set[str]:
            selector = BluetoothDevice.get_device_selector_from_connection_status(
                BluetoothConnectionStatus.CONNECTED
            )
            devices = await DeviceInformation.find_all_async_aqs_filter(selector)
            return {_bt_base_name(d.name) for d in devices if d.name}

        return asyncio.run(_query())
    except Exception:
        return None


def _bt_pnp_connected_bases() -> set[str]:
    """Fallback when WinRT is unavailable: BTHENUM PresentOnly base device names."""
    present = as_list(ps_json(
        "Get-PnpDevice -PresentOnly -ErrorAction SilentlyContinue | "
        "Where-Object { $_.Class -eq 'Bluetooth' -and $_.InstanceId -match 'BTHENUM' } | "
        "Select-Object FriendlyName,@{N='Status';E={$_.Status.ToString()}} | ConvertTo-Json -Compress",
        timeout=20.0,
    ))
    bases: set[str] = set()
    for row in present:
        if str(row.get("Status", "")).lower() != "ok":
            continue
        raw = row.get("FriendlyName") or ""
        if _bt_is_service_entry(raw):
            continue
        base = _bt_base_name(raw)
        if base:
            bases.add(base)
    return bases


def _bt_connected_bases() -> set[str]:
    connected = _bt_winrt_connected_bases()
    if connected is not None:
        return connected
    return _bt_pnp_connected_bases()


def _bluetooth_user_devices(paired_rows: list[dict], connected_bases: set[str]) -> list[dict]:
    """Build a de-duplicated list of real peripherals (not Windows BT service nodes)."""
    by_base: dict[str, dict] = {}
    for row in paired_rows:
        name = (row.get("FriendlyName") or "").strip()
        if not name or _bt_is_service_entry(name):
            continue
        base = _bt_base_name(name)
        if not base:
            continue
        connected = _bt_base_name(name) in connected_bases
        entry = {
            "name": name,
            "device_type": _bt_type(name),
            "paired": True,
            "connected": connected,
            "status": "Connected" if connected else "Not connected",
            "is_physical": True,
            "is_virtual": False,
        }
        prev = by_base.get(base)
        if prev is None:
            by_base[base] = entry
            continue
        # Prefer the shorter/cleaner display name and keep connected=True if any alias is active.
        if connected:
            prev["connected"] = True
            prev["status"] = "Connected"
        if len(name) < len(prev["name"]) and not _bt_is_service_entry(name):
            prev["name"] = name
            prev["device_type"] = _bt_type(name)

    devices = list(by_base.values())
    devices.sort(key=lambda d: (not d["connected"], d["name"].lower()))
    return devices


def _bluetooth() -> dict:
    paired = as_list(ps_json(
        "Get-PnpDevice -ErrorAction SilentlyContinue | "
        "Where-Object { $_.Class -eq 'Bluetooth' -and $_.InstanceId -match 'BTHENUM' } | "
        "Select-Object FriendlyName,@{N='Status';E={$_.Status.ToString()}} | ConvertTo-Json -Compress",
        timeout=20.0,
    ))
    connected_bases = _bt_connected_bases()
    devices = _bluetooth_user_devices(paired, connected_bases)
    connected = [d for d in devices if d["connected"]]

    adapter = as_list(ps_json(
        "Get-PnpDevice -Class Bluetooth -PresentOnly -ErrorAction SilentlyContinue | "
        "Where-Object { $_.InstanceId -notmatch 'BTHENUM' } | "
        "Select-Object FriendlyName,InstanceId,"
        "@{N='Status';E={$_.Status.ToString()}},"
        "@{N='Problem';E={[int]$_.Problem}} | ConvertTo-Json -Compress",
        timeout=20.0,
    ))
    adapters: list[dict] = []
    adapter_faults: list[dict] = []
    for a in adapter:
        name = a.get("FriendlyName")
        if not name:
            continue
        status = a.get("Status")
        problem = a.get("Problem")
        entry = {
            "name": name,
            "status": status,
            "problem_code": problem,
        }
        adapters.append(entry)
        if status == "Error" or (problem not in (0, 45, None)):
            adapter_faults.append(entry)
    return {
        "adapter_present": bool(adapters),
        "adapters": adapters,
        "adapter_faults": adapter_faults,
        "adapter_names": [a.get("name") for a in adapters if a.get("name")],
        "devices": devices,
        "paired_count": len(devices),
        "connected_count": len(connected),
        "connected_devices": [d["name"] for d in connected],
        "has_connected_device": bool(connected),
    }


def _bt_type(name: str) -> str:
    blob = name.lower()
    if re.search(r"headphone|headset|earbud|airpod|buds|audio", blob):
        return "Headphones / Headset"
    if re.search(r"speaker", blob):
        return "Speaker"
    if re.search(r"keyboard", blob):
        return "Keyboard"
    if re.search(r"mouse|trackpad", blob):
        return "Mouse"
    if re.search(r"phone|iphone|galaxy|pixel", blob):
        return "Mobile Phone"
    if re.search(r"watch|band|fit", blob):
        return "Smart Watch"
    return "Bluetooth Device"


# --------------------------------------------------------------------------- #
#  External storage (USB-attached disks)
# --------------------------------------------------------------------------- #
def _external_storage() -> dict:
    disks = as_list(ps_json(
        "Get-Disk -ErrorAction SilentlyContinue | "
        "Where-Object { $_.BusType -eq 'USB' -or $_.BusType -eq 'SD' -or $_.BusType -eq '1394' } | "
        "Select-Object Number,FriendlyName,SerialNumber,@{N='BusType';E={$_.BusType.ToString()}},"
        "Size,@{N='HealthStatus';E={$_.HealthStatus.ToString()}},"
        "@{N='OperationalStatus';E={$_.OperationalStatus.ToString()}} | ConvertTo-Json -Compress",
        timeout=25.0,
    ))
    # Map disk number -> free/total from its volumes.
    vol_rows = as_list(ps_json(
        "Get-Partition -ErrorAction SilentlyContinue | Where-Object { $_.DriveLetter } | "
        "ForEach-Object { $v = Get-Volume -Partition $_ -ErrorAction SilentlyContinue; "
        "[PSCustomObject]@{ DiskNumber=$_.DiskNumber; Drive=$_.DriveLetter; "
        "Size=$v.Size; Free=$v.SizeRemaining } } | ConvertTo-Json -Compress",
        timeout=25.0,
    ))
    free_by_disk: dict[int, dict] = {}
    for v in vol_rows:
        num = to_int(v.get("DiskNumber"))
        if num is None:
            continue
        agg = free_by_disk.setdefault(num, {"size": 0, "free": 0, "drives": []})
        agg["size"] += to_int(v.get("Size")) or 0
        agg["free"] += to_int(v.get("Free")) or 0
        if v.get("Drive"):
            agg["drives"].append(f"{v.get('Drive')}:")

    storage: list[dict] = []
    for d in disks:
        num = to_int(d.get("Number"))
        agg = free_by_disk.get(num, {})
        health_raw = (d.get("HealthStatus") or "").lower()
        op = (d.get("OperationalStatus") or "").lower()
        if health_raw and health_raw != "healthy":
            verdict = "Health Issue"
        elif "online" not in op and op:
            verdict = "Connection Failure"
        else:
            verdict = "Connected"
        storage.append({
            "name": d.get("FriendlyName"),
            "model": d.get("FriendlyName"),
            "bus_type": d.get("BusType"),
            "serial_number": (str(d.get("SerialNumber") or "")).strip() or None,
            "capacity_gb": bytes_to_gb(d.get("Size")),
            "free_gb": bytes_to_gb(agg.get("free")) if agg.get("size") else None,
            "drive_letters": agg.get("drives") or [],
            "smart_health": d.get("HealthStatus"),
            "operational_status": d.get("OperationalStatus"),
            "health": verdict,
        })
    return {"devices": storage, "count": len(storage)}


# --------------------------------------------------------------------------- #
#  Docking stations & Thunderbolt
# --------------------------------------------------------------------------- #
def _docks_thunderbolt() -> dict:
    rows = as_list(ps_json(
        "Get-PnpDevice -PresentOnly -ErrorAction SilentlyContinue | "
        "Where-Object { $_.FriendlyName -match 'dock|thunderbolt|wd19|wd15|tb3|tb4|usb4' } | "
        "Select-Object FriendlyName,Manufacturer,Class,"
        "@{N='Status';E={$_.Status.ToString()}} | ConvertTo-Json -Compress",
        timeout=20.0,
    ))
    docks: list[dict] = []
    thunderbolt: list[dict] = []
    for r in rows:
        name = r.get("FriendlyName")
        if not name:
            continue
        entry = {
            "name": name,
            "manufacturer": (r.get("Manufacturer") or "").strip() or None,
            "status": r.get("Status"),
            "health": _status_health(r.get("Status"), None),
        }
        if re.search(r"thunderbolt|tb3|tb4|usb4", name, re.I):
            thunderbolt.append(entry)
        else:
            docks.append(entry)
    return {
        "docking_stations": docks,
        "thunderbolt_devices": thunderbolt,
        "dock_count": len(docks),
        "thunderbolt_count": len(thunderbolt),
    }


# --------------------------------------------------------------------------- #
#  PCI / expansion devices
# --------------------------------------------------------------------------- #
_PCI_INTEREST = re.compile(
    r"raid|capture|sound|audio|network|ethernet|nic|sata|nvme controller|tv tuner|"
    r"fibre|sas|usb controller|host controller",
    re.I,
)


def _pci_devices() -> dict:
    rows = as_list(ps_json(
        "Get-PnpDevice -PresentOnly -ErrorAction SilentlyContinue | "
        "Where-Object { $_.InstanceId -match '^PCI' } | "
        "Select-Object FriendlyName,Class,Manufacturer,"
        "@{N='Status';E={$_.Status.ToString()}} | ConvertTo-Json -Compress",
        timeout=25.0,
    ))
    devices: list[dict] = []
    for r in rows:
        name = r.get("FriendlyName")
        if not name or not _PCI_INTEREST.search(name):
            continue
        devices.append({
            "name": name,
            "class": r.get("Class"),
            "manufacturer": (r.get("Manufacturer") or "").strip() or None,
            "status": r.get("Status"),
        })
    return {"devices": devices, "count": len(devices)}


# --------------------------------------------------------------------------- #
#  Network hardware (LAN neighbours)
# --------------------------------------------------------------------------- #
def _network_devices() -> dict:
    gateway = ps_json(
        "(Get-NetRoute -DestinationPrefix '0.0.0.0/0' -ErrorAction SilentlyContinue | "
        "Sort-Object RouteMetric | Select-Object -First 1).NextHop | ConvertTo-Json -Compress"
    )
    neighbours = as_list(ps_json(
        "Get-NetNeighbor -AddressFamily IPv4 -ErrorAction SilentlyContinue | "
        "Where-Object { $_.State -eq 'Reachable' -and $_.LinkLayerAddress -ne '' } | "
        "Select-Object IPAddress,LinkLayerAddress,@{N='State';E={$_.State.ToString()}} | "
        "ConvertTo-Json -Compress",
        timeout=20.0,
    ))
    devices: list[dict] = []
    for n in neighbours[:40]:
        mac = (n.get("LinkLayerAddress") or "").upper()
        if not mac or mac.startswith("FF") or mac == "00-00-00-00-00-00":
            continue
        devices.append({
            "ip_address": n.get("IPAddress"),
            "mac_address": mac,
            "manufacturer": _oui_vendor(mac),
            "is_gateway": n.get("IPAddress") == (gateway if isinstance(gateway, str) else None),
        })
    return {
        "gateway": gateway if isinstance(gateway, str) else None,
        "lan_devices": devices,
        "count": len(devices),
    }


# A tiny OUI prefix -> vendor map for the most common router/AP/device makers.
_OUI = {
    "00-1A-11": "Google", "00-50-F2": "Microsoft", "00-1D-7E": "Cisco-Linksys",
    "00-18-4D": "Netgear", "00-14-BF": "Cisco-Linksys", "00-25-9C": "Cisco-Linksys",
    "B8-27-EB": "Raspberry Pi", "DC-A6-32": "Raspberry Pi", "00-1B-63": "Apple",
    "F0-9F-C2": "Ubiquiti", "FC-EC-DA": "Ubiquiti", "00-0C-29": "VMware",
    "AC-DE-48": "Private", "00-1C-DF": "Belkin", "00-24-B2": "Netgear",
    "C0-56-27": "Belkin", "20-E5-2A": "Netgear", "00-90-A9": "Western Digital",
}


def _oui_vendor(mac: str) -> str | None:
    return _OUI.get(mac[:8])


# --------------------------------------------------------------------------- #
#  Relationship map + health summary
# --------------------------------------------------------------------------- #
def _build_relationship_map(report: dict) -> dict:
    """Computer -> peripheral dependency tree (best-effort, name-based)."""
    children: list[dict] = []

    docks = (report.get("docking_stations") or {}).get("docking_stations") or []
    monitors = (report.get("monitors") or {}).get("monitors") or []
    if docks:
        dock = docks[0]
        dock_node = {"name": dock.get("name"), "type": "Docking Station", "children": []}
        for m in monitors:
            dock_node["children"].append({
                "name": m.get("model") or "Monitor", "type": "Monitor"
            })
        children.append(dock_node)
    else:
        for m in monitors:
            children.append({"name": m.get("model") or "Monitor", "type": "Monitor"})

    for d in (report.get("usb") or {}).get("devices", []):
        children.append({"name": d.get("name"), "type": d.get("type")})

    for b in (report.get("bluetooth") or {}).get("devices", []):
        if b.get("connected"):
            children.append({"name": b.get("name"), "type": f"Bluetooth {b.get('device_type')}"})

    for p in (report.get("printers") or {}).get("printers", []):
        if p.get("is_virtual"):
            continue
        children.append({
            "name": p.get("name"),
            "type": f"{p.get('connection')} Printer",
        })

    return {"root": "This PC", "children": children}


def _health_summary(report: dict) -> dict:
    issues: list[str] = []

    offline_printers = [
        p["name"] for p in (report.get("printers") or {}).get("printers", [])
        if p.get("is_physical") and p.get("health") == "Offline"
    ]
    for name in offline_printers:
        issues.append(f"Printer offline: {name}")
    if not (report.get("printers") or {}).get("spooler_running", True):
        issues.append("Print Spooler service is not running.")

    for d in (report.get("usb") or {}).get("problem_devices", []):
        issues.append(f"USB device issue: {d.get('name')} ({d.get('health')}).")

    for c in (report.get("cameras") or {}).get("cameras", []):
        if c.get("is_virtual"):
            continue
        if c.get("health") in ("Disabled", "Communication Issue", "Driver Missing"):
            issues.append(f"Camera issue: {c.get('name')} ({c.get('health')}).")

    for s in (report.get("external_storage") or {}).get("devices", []):
        if s.get("health") != "Connected":
            issues.append(f"External storage: {s.get('name')} ({s.get('health')}).")

    for d in (report.get("audio") or {}).get("input_devices", []) + \
            (report.get("audio") or {}).get("output_devices", []):
        if d.get("is_virtual"):
            continue
        if d.get("health") == "Disabled":
            issues.append(f"Audio device disabled: {d.get('name')}.")

    total = (
        (report.get("usb") or {}).get("peripheral_count", 0)
        + (report.get("monitors") or {}).get("count", 0)
        + (report.get("printers") or {}).get("physical_count", 0)
        + (report.get("scanners") or {}).get("physical_count", 0)
        + (report.get("cameras") or {}).get("physical_count", 0)
        + (report.get("bluetooth") or {}).get("connected_count", 0)
        + (report.get("external_storage") or {}).get("count", 0)
    )
    return {
        "total_external_devices": total,
        "issue_count": len(issues),
        "issues": issues[:12],
    }


def _physical_inventory(report: dict) -> dict:
    """Roll-up of physically connected peripherals (excludes virtual/software devices)."""
    printers = report.get("printers") or {}
    audio = report.get("audio") or {}
    cameras = report.get("cameras") or {}
    monitors = report.get("monitors") or {}
    usb = report.get("usb") or {}
    bt = report.get("bluetooth") or {}
    scanners = report.get("scanners") or {}
    storage = report.get("external_storage") or {}

    return {
        "printer": {
            "physical": printers.get("physical_count", 0),
            "connected": printers.get("physical_ready_count", 0),
            "virtual": printers.get("virtual_count", 0),
        },
        "microphone": {
            "physical": audio.get("physical_input_count", 0),
            "connected": int(audio.get("has_connected_physical_input", False)),
            "virtual": audio.get("virtual_input_count", 0),
        },
        "speaker": {
            "physical": audio.get("physical_output_count", 0),
            "connected": int(audio.get("has_connected_physical_output", False)),
            "virtual": audio.get("virtual_output_count", 0),
        },
        "camera": {
            "physical": cameras.get("physical_count", 0),
            "connected": cameras.get("connected_physical_count", 0),
            "virtual": cameras.get("virtual_count", 0),
        },
        "display_external": {
            "physical": monitors.get("external_count", 0),
            "connected": monitors.get("external_count", 0),
            "internal": monitors.get("internal_count", 0),
        },
        "usb_peripheral": {
            "physical": usb.get("peripheral_count", 0),
            "connected": usb.get("connected_peripheral_count", 0),
        },
        "bluetooth": {
            "paired": bt.get("paired_count", 0),
            "connected": bt.get("connected_count", 0),
        },
        "scanner": {
            "physical": scanners.get("physical_count", 0),
            "connected": scanners.get("connected_physical_count", 0),
        },
        "external_storage": {
            "physical": storage.get("count", 0),
            "connected": sum(
                1 for d in (storage.get("devices") or []) if d.get("health") == "Connected"
            ),
        },
    }


# --------------------------------------------------------------------------- #
#  Entry point
# --------------------------------------------------------------------------- #
# Map issue domains to the external-device sub-scanners they actually need.
_DOMAIN_EXTERNAL_JOBS: dict[str, list[str]] = {
    "bluetooth": ["bluetooth"],
    "usb": ["usb", "external_storage"],
    "mouse": ["usb", "bluetooth"],
    "keyboard": ["usb", "bluetooth"],
    "printer": ["printers", "scanners"],
    "webcam": ["cameras"],
    "audio": ["audio"],
    "display": ["monitors"],
}


def _external_jobs_for_domains(domains: list[str] | None) -> dict:
    all_jobs = {
        "usb": lambda drivers: _usb_devices(drivers),
        "monitors": _monitors,
        "printers": _printers,
        "scanners": _scanners,
        "audio": _audio_devices,
        "cameras": _cameras,
        "bluetooth": _bluetooth,
        "external_storage": _external_storage,
        "docking_stations": _docks_thunderbolt,
        "pci_devices": _pci_devices,
        "network_devices": _network_devices,
    }
    if domains is None:
        jobs: dict = {}
        for key, fn in all_jobs.items():
            if key == "usb":
                jobs[key] = lambda drivers, fn=fn: fn(drivers)
            else:
                jobs[key] = fn
        return jobs

    keys: list[str] = []
    for domain in domains:
        for key in _DOMAIN_EXTERNAL_JOBS.get(domain, []):
            if key not in keys:
                keys.append(key)
    if not keys:
        keys = ["bluetooth", "usb"]

    jobs: dict = {}
    for key in keys:
        fn = all_jobs[key]
        if key == "usb":
            jobs[key] = lambda drivers, fn=fn: fn(drivers)
        else:
            jobs[key] = fn
    return jobs


@safe_scan("external_devices")
def scan(domains: list[str] | None = None) -> dict:
    if not IS_WINDOWS:
        return {"available": False, "note": "External device discovery requires Windows."}

    jobs = _external_jobs_for_domains(domains)
    needs_drivers = domains is None or "usb" in jobs
    drivers = _driver_map() if needs_drivers else {}

    out: dict[str, Any] = {"available": True}
    with ThreadPoolExecutor(max_workers=max(len(jobs), 1)) as pool:
        futures: dict = {}
        for key, fn in jobs.items():
            if key == "usb":
                futures[pool.submit(fn, drivers)] = key
            else:
                futures[pool.submit(fn)] = key
        for fut, key in futures.items():
            try:
                out[key] = fut.result(timeout=45)
            except Exception as exc:  # pragma: no cover - host dependent
                out[key] = {"error": str(exc)}

    out["relationship_map"] = _build_relationship_map(out)
    out["physical_inventory"] = _physical_inventory(out)
    out["summary"] = _health_summary(out)
    return out
