"""Hardware scanner: CPU, RAM, storage, disk health, GPU, battery, board, devices."""
from __future__ import annotations

import platform

import psutil

from app.services.scanners.base import (
    GB,
    IS_WINDOWS,
    as_list,
    bytes_to_gb,
    bytes_to_mb,
    cim,
    cim_one,
    pct,
    ps_json,
    safe_scan,
    to_float,
    to_int,
)

_MEMORY_FORM_FACTORS = {
    8: "DIMM", 12: "SODIMM", 0: "Unknown",
}
_MEMORY_TYPES = {
    20: "DDR", 21: "DDR2", 24: "DDR3", 26: "DDR4", 34: "DDR5", 0: "Unknown",
}


def _cpu() -> dict:
    freq = None
    try:
        freq = psutil.cpu_freq()
    except Exception:
        freq = None
    info = cim_one("Win32_Processor", "Name,Manufacturer,MaxClockSpeed,NumberOfCores,"
                   "NumberOfLogicalProcessors,Architecture,CurrentClockSpeed") or {}
    arch_map = {0: "x86", 5: "ARM", 6: "Itanium", 9: "x64", 12: "ARM64"}
    # 5-sample short load history (non-blocking-ish).
    load_history = []
    try:
        load_history = [round(psutil.cpu_percent(interval=0.15), 1) for _ in range(5)]
    except Exception:
        pass
    return {
        "processor_name": info.get("Name") or platform.processor() or "Unknown",
        "manufacturer": info.get("Manufacturer"),
        "architecture": arch_map.get(info.get("Architecture"), platform.machine()),
        "physical_cores": psutil.cpu_count(logical=False) or info.get("NumberOfCores"),
        "logical_cores": psutil.cpu_count(logical=True) or info.get("NumberOfLogicalProcessors"),
        "current_usage_pct": round(psutil.cpu_percent(interval=0.3), 1),
        "current_frequency_mhz": round(freq.current) if freq else info.get("CurrentClockSpeed"),
        "max_frequency_mhz": round(freq.max) if freq and freq.max else info.get("MaxClockSpeed"),
        "temperature_c": _cpu_temperature(),
        "per_core_usage_pct": _per_core(),
        "load_history_pct": load_history,
    }


def _per_core() -> list[float]:
    try:
        return [round(x, 1) for x in psutil.cpu_percent(interval=0.2, percpu=True)]
    except Exception:
        return []


def _cpu_temperature() -> float | None:
    # psutil sensors aren't available on Windows; try WMI thermal zone (often N/A).
    if not IS_WINDOWS:
        try:
            temps = psutil.sensors_temperatures()  # type: ignore[attr-defined]
            for entries in temps.values():
                if entries:
                    return round(entries[0].current, 1)
        except Exception:
            return None
        return None
    rec = cim_one("MSAcpi_ThermalZoneTemperature", "CurrentTemperature",
                  namespace="root/wmi")
    if rec and rec.get("CurrentTemperature"):
        # Tenths of Kelvin -> Celsius.
        return round(to_float(rec["CurrentTemperature"]) / 10 - 273.15, 1)
    return None


def _ram() -> dict:
    vm = psutil.virtual_memory()
    modules = []
    for m in cim("Win32_PhysicalMemory", "Capacity,Speed,Manufacturer,PartNumber,"
                 "DeviceLocator,MemoryType,SMBIOSMemoryType,FormFactor,ConfiguredClockSpeed"):
        mtype = _MEMORY_TYPES.get(m.get("SMBIOSMemoryType") or m.get("MemoryType"), None)
        modules.append({
            "capacity_gb": bytes_to_gb(m.get("Capacity")),
            "speed_mhz": m.get("ConfiguredClockSpeed") or m.get("Speed"),
            "manufacturer": (m.get("Manufacturer") or "").strip() or None,
            "part_number": (m.get("PartNumber") or "").strip() or None,
            "slot": (m.get("DeviceLocator") or "").strip() or None,
            "form_factor": _MEMORY_FORM_FACTORS.get(m.get("FormFactor")),
            "type": mtype,
        })
    slots = cim_one("Win32_PhysicalMemoryArray", "MemoryDevices")
    return {
        "total_gb": bytes_to_gb(vm.total),
        "used_gb": bytes_to_gb(vm.used),
        "available_gb": bytes_to_gb(vm.available),
        "utilization_pct": vm.percent,
        "modules": modules,
        "module_count": len(modules),
        "slots_total": (slots or {}).get("MemoryDevices"),
        "speed_mhz": modules[0]["speed_mhz"] if modules else None,
    }


def _storage() -> dict:
    drives = []
    io_per_disk = {}
    try:
        io_per_disk = psutil.disk_io_counters(perdisk=True) or {}
    except Exception:
        io_per_disk = {}
    fs_by_letter = {}
    for ld in cim("Win32_LogicalDisk", "DeviceID,FileSystem,VolumeName,DriveType",
                  where="DriveType=3"):
        fs_by_letter[(ld.get("DeviceID") or "").upper()] = ld

    for part in psutil.disk_partitions(all=False):
        if IS_WINDOWS and "cdrom" in (part.opts or ""):
            continue
        try:
            usage = psutil.disk_usage(part.mountpoint)
        except (PermissionError, OSError):
            continue
        letter = (part.device or "").rstrip("\\").upper()
        meta = fs_by_letter.get(letter, {})
        drives.append({
            "drive": part.device,
            "mountpoint": part.mountpoint,
            "volume_name": (meta.get("VolumeName") or "").strip() or None,
            "file_system": part.fstype or meta.get("FileSystem"),
            "total_gb": bytes_to_gb(usage.total),
            "used_gb": bytes_to_gb(usage.used),
            "free_gb": bytes_to_gb(usage.free),
            "usage_pct": usage.percent,
        })

    # Physical disk media type (SSD vs HDD).
    physical = []
    for pd in cim("MSFT_PhysicalDisk", "FriendlyName,MediaType,Size,BusType,SpindleSpeed,HealthStatus",
                  namespace="root/microsoft/windows/storage"):
        media = {3: "HDD", 4: "SSD", 5: "SCM", 0: "Unspecified"}.get(pd.get("MediaType"), "Unknown")
        physical.append({
            "name": pd.get("FriendlyName"),
            "media_type": media,
            "size_gb": bytes_to_gb(pd.get("Size")),
            "health_status": pd.get("HealthStatus"),
        })

    return {
        "logical_drives": drives,
        "physical_disks": physical,
        "drive_count": len(drives),
    }


def _disk_health() -> dict:
    disks = []
    if not IS_WINDOWS:
        return {"available": False, "disks": disks, "note": "SMART health requires Windows."}
    phys = cim("MSFT_PhysicalDisk",
               "DeviceId,FriendlyName,HealthStatus,OperationalStatus,MediaType",
               namespace="root/microsoft/windows/storage")
    for pd in phys:
        device_id = pd.get("DeviceId")
        reliability = cim_one(
            "MSFT_StorageReliabilityCounter",
            "Temperature,Wear,ReadErrorsTotal,WriteErrorsTotal,PowerOnHours",
            namespace="root/microsoft/windows/storage",
        ) if device_id is None else None
        # Per-disk reliability is best fetched via association; fall back to first.
        rel = reliability or {}
        health_map = {0: "Healthy", 1: "Warning", 2: "Unhealthy"}
        disks.append({
            "name": pd.get("FriendlyName"),
            "media_type": {3: "HDD", 4: "SSD"}.get(pd.get("MediaType"), "Unknown"),
            "smart_health": health_map.get(pd.get("HealthStatus"), str(pd.get("HealthStatus"))),
            "temperature_c": rel.get("Temperature"),
            "wear_pct": rel.get("Wear"),
            "read_errors": rel.get("ReadErrorsTotal"),
            "write_errors": rel.get("WriteErrorsTotal"),
            "power_on_hours": rel.get("PowerOnHours"),
        })
    return {"available": bool(disks), "disks": disks}


def _gpu() -> dict:
    gpus = []
    for v in cim("Win32_VideoController", "Name,AdapterCompatibility,DriverVersion,"
                 "AdapterRAM,DriverDate,VideoProcessor,CurrentHorizontalResolution,"
                 "CurrentVerticalResolution"):
        gpus.append({
            "model": v.get("Name"),
            "manufacturer": v.get("AdapterCompatibility"),
            "driver_version": v.get("DriverVersion"),
            "vram_gb": bytes_to_gb(v.get("AdapterRAM")) if v.get("AdapterRAM") else None,
            "video_processor": v.get("VideoProcessor"),
            "resolution": (
                f"{v.get('CurrentHorizontalResolution')}x{v.get('CurrentVerticalResolution')}"
                if v.get("CurrentHorizontalResolution") else None
            ),
        })
    return {"gpus": gpus, "gpu_count": len(gpus)}


def _battery() -> dict:
    try:
        batt = psutil.sensors_battery()
    except Exception:
        batt = None
    if batt is None:
        return {"present": False, "note": "No battery detected (likely a desktop)."}
    secs = batt.secsleft
    remaining = None
    if secs not in (psutil.POWER_TIME_UNLIMITED, psutil.POWER_TIME_UNKNOWN) and secs and secs > 0:
        remaining = f"{secs // 3600}h {(secs % 3600) // 60}m"

    design = full = health = None
    static = cim_one("BatteryStaticData", "DesignedCapacity",
                     namespace="root/wmi")
    fullcap = cim_one("BatteryFullChargedCapacity", "FullChargedCapacity",
                      namespace="root/wmi")
    if static and fullcap:
        design = to_int(static.get("DesignedCapacity"))
        full = to_int(fullcap.get("FullChargedCapacity"))
        if design and full:
            health = round((full / design) * 100, 1)
    return {
        "present": True,
        "percentage": round(batt.percent, 1),
        "charging": batt.power_plugged,
        "design_capacity_mwh": design,
        "current_capacity_mwh": full,
        "battery_health_pct": health,
        "estimated_remaining": remaining,
    }


def _motherboard() -> dict:
    board = cim_one("Win32_BaseBoard", "Manufacturer,Product,SerialNumber") or {}
    bios = cim_one("Win32_BIOS", "Manufacturer,SMBIOSBIOSVersion,ReleaseDate,SerialNumber") or {}
    return {
        "manufacturer": board.get("Manufacturer"),
        "model": board.get("Product"),
        "serial_number": board.get("SerialNumber"),
        "bios_version": bios.get("SMBIOSBIOSVersion"),
        "bios_manufacturer": bios.get("Manufacturer"),
        "bios_release_date": _cim_date(bios.get("ReleaseDate")),
    }


def _cim_date(value) -> str | None:
    # CIM dates look like /Date(1700000000000)/ or yyyymmdd...
    if not value:
        return None
    s = str(value)
    if "Date(" in s:
        try:
            import datetime
            ms = int(s.split("Date(")[1].split(")")[0].split("+")[0].split("-")[0])
            return datetime.datetime.utcfromtimestamp(ms / 1000).strftime("%Y-%m-%d")
        except Exception:
            return s
    if len(s) >= 8 and s[:8].isdigit():
        return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
    return s


# Friendly labels for the most common PnP device classes.
_DEVICE_CLASS_LABELS = {
    "Processor": "Processors",
    "DiskDrive": "Disk drives",
    "Display": "Display adapters",
    "Monitor": "Monitors",
    "Net": "Network adapters",
    "Media": "Audio devices",
    "AudioEndpoint": "Audio endpoints",
    "Camera": "Cameras",
    "Image": "Imaging devices",
    "Printer": "Printers",
    "Keyboard": "Keyboards",
    "Mouse": "Mice & pointing devices",
    "HIDClass": "Human interface devices",
    "Bluetooth": "Bluetooth",
    "USB": "USB controllers & hubs",
    "Battery": "Batteries",
    "Biometric": "Biometric devices",
    "SmartCardReader": "Smart-card readers",
    "SoftwareDevice": "Software devices",
    "System": "System devices",
    "Volume": "Storage volumes",
    "WPD": "Portable devices",
}


def _all_devices() -> dict:
    """Full inventory of every present device/component via PnP (Device Manager)."""
    rows = as_list(ps_json(
        "Get-PnpDevice -PresentOnly -ErrorAction SilentlyContinue | "
        "Select-Object FriendlyName,Class,Manufacturer,"
        "@{N='Status';E={$_.Status.ToString()}},@{N='Problem';E={[int]$_.Problem}} | "
        "ConvertTo-Json -Compress",
        timeout=30.0,
    ))
    devices: list[dict] = []
    by_category: dict[str, list[dict]] = {}
    problem_devices: list[dict] = []
    for r in rows:
        name = r.get("FriendlyName")
        if not name:
            continue
        cls = r.get("Class") or "Other"
        status = r.get("Status")
        problem = r.get("Problem")
        # A genuine fault: Error status with a real problem code (0 = OK, 45 = not
        # currently connected, which -PresentOnly already filters out anyway).
        has_fault = status == "Error" and problem not in (0, 45, None)
        dev = {
            "name": name,
            "class": cls,
            "category": _DEVICE_CLASS_LABELS.get(cls, cls),
            "manufacturer": r.get("Manufacturer"),
            "status": status,
            "problem_code": problem,
            "working": not has_fault,
        }
        devices.append(dev)
        by_category.setdefault(dev["category"], []).append(dev)
        if has_fault:
            problem_devices.append(dev)
    devices.sort(key=lambda d: (d.get("category") or "", d.get("name") or ""))
    return {
        "all": devices,
        "by_category": by_category,
        "total_count": len(devices),
        "problem_count": len(problem_devices),
        "problem_devices": problem_devices,
    }


def _peripherals() -> dict:
    """Curated peripheral lists (printers, external displays, external storage)."""
    printers = [p.get("Name") for p in cim("Win32_Printer", "Name") if p.get("Name")]
    monitors = [m.get("Name") for m in cim("Win32_DesktopMonitor", "Name") if m.get("Name")]
    external_storage = []
    for d in cim("Win32_DiskDrive", "Model,InterfaceType,Size", where="InterfaceType='USB'"):
        external_storage.append({"model": d.get("Model"), "size_gb": bytes_to_gb(d.get("Size"))})
    return {
        "printers": printers,
        "external_displays": monitors,
        "external_storage": external_storage,
    }


def _network_adapters() -> list[dict]:
    """Physical network interface cards (hardware-level)."""
    rows = cim(
        "Win32_NetworkAdapter",
        "Name,Manufacturer,MACAddress,AdapterType,Speed,NetConnectionStatus",
        where="PhysicalAdapter=True",
    )
    out = []
    for r in rows:
        speed = to_int(r.get("Speed"))
        out.append({
            "name": r.get("Name"),
            "manufacturer": r.get("Manufacturer"),
            "mac": r.get("MACAddress"),
            "type": r.get("AdapterType"),
            "speed_mbps": round(speed / 1_000_000) if speed else None,
            "connected": r.get("NetConnectionStatus") == 2,
        })
    return out


@safe_scan("hardware")
def scan() -> dict:
    # Each sub-probe makes its own (blocking) CIM/PowerShell calls; run them in
    # parallel so total time is the slowest probe rather than their sum.
    from concurrent.futures import ThreadPoolExecutor

    jobs = {
        "cpu": _cpu,
        "ram": _ram,
        "storage": _storage,
        "disk_health": _disk_health,
        "gpu": _gpu,
        "battery": _battery,
        "motherboard": _motherboard,
        "devices": _all_devices,
        "peripherals": _peripherals,
        "network_adapters": _network_adapters,
    }
    out: dict = {}
    with ThreadPoolExecutor(max_workers=len(jobs)) as pool:
        futures = {pool.submit(fn): key for key, fn in jobs.items()}
        for fut, key in futures.items():
            try:
                out[key] = fut.result(timeout=40)
            except Exception as exc:  # pragma: no cover
                out[key] = {"error": str(exc)}

    # Consolidate everything device-related under a single `devices` block.
    devices = out.pop("devices", {}) or {}
    peripherals = out.pop("peripherals", {}) or {}
    if isinstance(devices, dict):
        devices.update(peripherals)
        devices["network_adapters"] = out.pop("network_adapters", [])
        out["devices"] = devices
    return out
