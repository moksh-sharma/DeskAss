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
                   "NumberOfLogicalProcessors,Architecture,CurrentClockSpeed,"
                   "L2CacheSize,L3CacheSize,SocketDesignation,ProcessorId,"
                   "VirtualizationFirmwareEnabled,SecondLevelAddressTranslationExtensions") or {}
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
        "l2_cache_kb": to_int(info.get("L2CacheSize")),
        "l3_cache_kb": to_int(info.get("L3CacheSize")),
        "socket": info.get("SocketDesignation"),
        "processor_id": info.get("ProcessorId"),
        "virtualization_firmware_enabled": info.get("VirtualizationFirmwareEnabled"),
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

    # Page file / commit charge - critical for diagnosing memory pressure.
    page_files = []
    for pf in cim("Win32_PageFileUsage", "Name,AllocatedBaseSize,CurrentUsage,PeakUsage"):
        page_files.append({
            "path": pf.get("Name"),
            "allocated_mb": to_int(pf.get("AllocatedBaseSize")),
            "in_use_mb": to_int(pf.get("CurrentUsage")),
            "peak_mb": to_int(pf.get("PeakUsage")),
        })
    try:
        swap = psutil.swap_memory()
        swap_info = {
            "total_gb": bytes_to_gb(swap.total),
            "used_gb": bytes_to_gb(swap.used),
            "used_pct": swap.percent,
        }
    except Exception:
        swap_info = {}

    return {
        "total_gb": bytes_to_gb(vm.total),
        "used_gb": bytes_to_gb(vm.used),
        "available_gb": bytes_to_gb(vm.available),
        "utilization_pct": vm.percent,
        "modules": modules,
        "module_count": len(modules),
        "slots_total": (slots or {}).get("MemoryDevices"),
        "speed_mhz": modules[0]["speed_mhz"] if modules else None,
        "page_files": page_files,
        "virtual_memory": swap_info,
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

    # Physical disk inventory: media type, bus, firmware, serial, partition style.
    bus_map = {0: "Unknown", 1: "SCSI", 2: "ATAPI", 3: "ATA", 4: "IEEE1394", 5: "SSA",
               6: "FC", 7: "USB", 8: "RAID", 9: "iSCSI", 10: "SAS", 11: "SATA",
               12: "SD", 13: "MMC", 17: "NVMe"}
    physical = []
    for pd in cim("MSFT_PhysicalDisk",
                  "FriendlyName,MediaType,Size,BusType,SpindleSpeed,HealthStatus,"
                  "FirmwareVersion,SerialNumber,Model",
                  namespace="root/microsoft/windows/storage"):
        media = {3: "HDD", 4: "SSD", 5: "SCM", 0: "Unspecified"}.get(pd.get("MediaType"), "Unknown")
        physical.append({
            "name": pd.get("FriendlyName"),
            "model": pd.get("Model"),
            "media_type": media,
            "bus_type": bus_map.get(pd.get("BusType"), str(pd.get("BusType"))),
            "size_gb": bytes_to_gb(pd.get("Size")),
            "health_status": pd.get("HealthStatus"),
            "firmware_version": pd.get("FirmwareVersion"),
            "serial_number": (str(pd.get("SerialNumber") or "")).strip() or None,
            "spindle_speed_rpm": to_int(pd.get("SpindleSpeed")) or None,
        })

    # Partition layout (GPT vs MBR, boot disk).
    disk_layout = []
    for dk in as_list(ps_json(
        "Get-Disk -ErrorAction SilentlyContinue | Select-Object Number,FriendlyName,"
        "@{N='PartitionStyle';E={$_.PartitionStyle.ToString()}},NumberOfPartitions,"
        "IsBoot,IsSystem,@{N='HealthStatus';E={$_.HealthStatus.ToString()}} | "
        "ConvertTo-Json -Compress",
        timeout=20.0,
    )):
        disk_layout.append({
            "number": dk.get("Number"),
            "name": dk.get("FriendlyName"),
            "partition_style": dk.get("PartitionStyle"),
            "partitions": dk.get("NumberOfPartitions"),
            "is_boot": dk.get("IsBoot"),
            "health": dk.get("HealthStatus"),
        })

    return {
        "logical_drives": drives,
        "physical_disks": physical,
        "disk_layout": disk_layout,
        "drive_count": len(drives),
    }


def _disk_health() -> dict:
    """Per-disk SMART health + reliability counters via the proper association."""
    disks = []
    if not IS_WINDOWS:
        return {"available": False, "disks": disks, "note": "SMART health requires Windows."}
    rows = as_list(ps_json(
        "Get-PhysicalDisk -ErrorAction SilentlyContinue | ForEach-Object { "
        "$r = $_ | Get-StorageReliabilityCounter -ErrorAction SilentlyContinue; "
        "[PSCustomObject]@{ Name=$_.FriendlyName; MediaType=[string]$_.MediaType; "
        "Health=$_.HealthStatus.ToString(); OpStatus=($_.OperationalStatus -join ', '); "
        "Temp=$r.Temperature; TempMax=$r.TemperatureMax; Wear=$r.Wear; "
        "ReadErrors=$r.ReadErrorsTotal; WriteErrors=$r.WriteErrorsTotal; "
        "PowerOnHours=$r.PowerOnHours; StartStop=$r.StartStopCycleCount } } | "
        "ConvertTo-Json -Compress",
        timeout=30.0,
    ))
    for r in rows:
        disks.append({
            "name": r.get("Name"),
            "media_type": r.get("MediaType") or "Unknown",
            "smart_health": r.get("Health"),
            "operational_status": r.get("OpStatus"),
            "temperature_c": to_int(r.get("Temp")) or None,
            "temperature_max_c": to_int(r.get("TempMax")) or None,
            "wear_pct": to_int(r.get("Wear")),
            "read_errors": to_int(r.get("ReadErrors")),
            "write_errors": to_int(r.get("WriteErrors")),
            "power_on_hours": to_int(r.get("PowerOnHours")),
            "start_stop_cycles": to_int(r.get("StartStop")),
        })
    return {"available": bool(disks), "disks": disks}


def _gpu() -> dict:
    gpus = []
    for v in cim("Win32_VideoController", "Name,AdapterCompatibility,DriverVersion,"
                 "AdapterRAM,DriverDate,VideoProcessor,CurrentHorizontalResolution,"
                 "CurrentVerticalResolution,CurrentRefreshRate,Status,VideoModeDescription"):
        gpus.append({
            "model": v.get("Name"),
            "manufacturer": v.get("AdapterCompatibility"),
            "driver_version": v.get("DriverVersion"),
            "driver_date": _cim_date(v.get("DriverDate")),
            "vram_gb": bytes_to_gb(v.get("AdapterRAM")) if v.get("AdapterRAM") else None,
            "video_processor": v.get("VideoProcessor"),
            "status": v.get("Status"),
            "refresh_rate_hz": to_int(v.get("CurrentRefreshRate")) or None,
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
    board = cim_one("Win32_BaseBoard", "Manufacturer,Product,SerialNumber,Version") or {}
    bios = cim_one("Win32_BIOS", "Manufacturer,SMBIOSBIOSVersion,ReleaseDate,SerialNumber") or {}
    return {
        "manufacturer": board.get("Manufacturer"),
        "model": board.get("Product"),
        "version": board.get("Version"),
        "serial_number": board.get("SerialNumber"),
        "bios_version": bios.get("SMBIOSBIOSVersion"),
        "bios_manufacturer": bios.get("Manufacturer"),
        "bios_release_date": _cim_date(bios.get("ReleaseDate")),
        "bios_serial_number": bios.get("SerialNumber"),
    }


_CHASSIS_TYPES = {
    3: "Desktop", 4: "Low-profile desktop", 5: "Pizza box", 6: "Mini tower", 7: "Tower",
    8: "Portable", 9: "Laptop", 10: "Notebook", 11: "Hand-held", 12: "Docking station",
    13: "All-in-one", 14: "Sub-notebook", 15: "Space-saving", 16: "Lunch box",
    17: "Main server chassis", 21: "Peripheral chassis", 23: "Rack-mount chassis",
    24: "Sealed-case PC", 30: "Tablet", 31: "Convertible", 32: "Detachable",
}


def _system_identity() -> dict:
    """Asset/identity data IT teams need: make, model, serials, asset tag, chassis."""
    cs = cim_one("Win32_ComputerSystem", "Manufacturer,Model,SystemFamily,SystemSKUNumber,"
                 "PCSystemType,DomainRole,TotalPhysicalMemory") or {}
    product = cim_one("Win32_ComputerSystemProduct", "UUID,IdentifyingNumber,Vendor,Version") or {}
    enclosure = cim_one("Win32_SystemEnclosure", "ChassisTypes,SerialNumber,SMBIOSAssetTag") or {}
    chassis_codes = enclosure.get("ChassisTypes")
    if isinstance(chassis_codes, (int, float)):
        chassis_codes = [int(chassis_codes)]
    chassis = [
        _CHASSIS_TYPES.get(to_int(c), f"Type {c}") for c in (chassis_codes or [])
    ]
    pc_type = {0: "Unspecified", 1: "Desktop", 2: "Mobile/Laptop", 3: "Workstation",
               4: "Enterprise server", 5: "SOHO server", 6: "Appliance", 7: "Performance server",
               8: "Maximum"}.get(cs.get("PCSystemType"))
    domain_role = {0: "Standalone workstation", 1: "Member workstation", 2: "Standalone server",
                   3: "Member server", 4: "Backup domain controller",
                   5: "Primary domain controller"}.get(cs.get("DomainRole"))
    asset_tag = (enclosure.get("SMBIOSAssetTag") or "").strip()
    return {
        "manufacturer": cs.get("Manufacturer"),
        "model": cs.get("Model"),
        "system_family": cs.get("SystemFamily"),
        "system_sku": cs.get("SystemSKUNumber"),
        "serial_number": (product.get("IdentifyingNumber") or enclosure.get("SerialNumber") or "").strip() or None,
        "uuid": product.get("UUID"),
        "asset_tag": asset_tag if asset_tag.lower() not in ("", "no asset tag", "none") else None,
        "chassis_type": ", ".join(chassis) or None,
        "pc_type": pc_type,
        "domain_role": domain_role,
    }


def _monitors() -> list[dict]:
    """Connected display details decoded from EDID (WmiMonitorID)."""
    # Keep only printable ASCII bytes - EDID strings are padded with 0/control chars.
    decode = "[System.Text.Encoding]::ASCII.GetString([byte[]]@($_.{0} | Where-Object {{$_ -ge 32 -and $_ -le 126}})).Trim()"
    rows = as_list(ps_json(
        "Get-CimInstance -Namespace root/wmi -ClassName WmiMonitorID -ErrorAction SilentlyContinue | "
        "ForEach-Object { [PSCustomObject]@{ "
        f"Manufacturer = {decode.format('ManufacturerName')}; "
        f"Model = {decode.format('UserFriendlyName')}; "
        f"Serial = {decode.format('SerialNumberID')}; "
        "Year = $_.YearOfManufacture } } | ConvertTo-Json -Compress",
        timeout=20.0,
    ))
    return [{
        "manufacturer": r.get("Manufacturer") or None,
        "model": r.get("Model") or None,
        "serial_number": (r.get("Serial") or "").strip("0") or r.get("Serial") or None,
        "year_of_manufacture": to_int(r.get("Year")),
    } for r in rows]


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
        "system": _system_identity,
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
        "monitors": _monitors,
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
        devices["monitors"] = out.pop("monitors", [])
        out["devices"] = devices
    return out
