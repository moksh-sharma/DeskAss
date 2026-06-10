"""Automatic system diagnostics collection (CPU, RAM, disk, network, etc.).

Uses ``psutil`` (cross-platform) with optional Windows-specific enrichment via
``wmi`` / the registry for startup programs and installed software. Every probe
is wrapped defensively so a single failing source never breaks the whole report.
"""
from __future__ import annotations

import os
import platform
import socket
import subprocess
import sys
import time
from datetime import datetime

import psutil

from app.core.logging import get_logger
from app.models.schemas import (
    BatteryInfo,
    CpuInfo,
    DiskInfo,
    InstalledSoftware,
    MemoryInfo,
    NetworkAdapter,
    NetworkInfo,
    OsInfo,
    ProcessInfo,
    StartupProgram,
    SystemDiagnostics,
)

logger = get_logger(__name__)

IS_WINDOWS = sys.platform == "win32"
GB = 1024 ** 3
MB = 1024 ** 2

# Shared severity thresholds (warn, critical) used by diagnosis + health grading.
CPU_WARN, CPU_CRIT = 75.0, 90.0
RAM_WARN, RAM_CRIT = 80.0, 92.0
DISK_WARN, DISK_CRIT = 85.0, 95.0

# Software we care about for an enterprise desktop.
_TRACKED_SOFTWARE = {
    "Microsoft Outlook": ["outlook"],
    "Microsoft Teams": ["teams"],
    "Google Chrome": ["chrome"],
    "Microsoft Edge": ["edge", "msedge"],
    "Microsoft Office": ["office", "winword", "excel"],
    "Cisco AnyConnect VPN": ["anyconnect", "cisco"],
    "GlobalProtect VPN": ["globalprotect", "palo alto"],
    "OpenVPN": ["openvpn"],
    "Zoom": ["zoom"],
}


class DiagnosticsService:
    """Collects a full snapshot of the local machine state."""

    def collect(self, *, top_n: int = 10) -> SystemDiagnostics:
        warnings: list[str] = []
        diag = SystemDiagnostics(collected_at=datetime.utcnow())
        diag.uptime_hours = round((time.time() - psutil.boot_time()) / 3600, 1)
        diag.cpu = self._safe(self._cpu, CpuInfo(), warnings, "cpu")
        diag.memory = self._safe(self._memory, MemoryInfo(), warnings, "memory")
        diag.disks = self._safe(self._disks, [], warnings, "disk")
        diag.network = self._safe(self._network, NetworkInfo(), warnings, "network")
        diag.os = self._safe(self._os, OsInfo(), warnings, "os")
        diag.battery = self._safe(self._battery, BatteryInfo(), warnings, "battery")
        cpu_procs, mem_procs = self._safe(lambda: self._processes(top_n), ([], []), warnings, "processes")
        diag.top_cpu_processes = cpu_procs
        diag.top_memory_processes = mem_procs
        diag.startup_programs = self._safe(self._startup_programs, [], warnings, "startup")
        diag.installed_software = self._safe(self._installed_software, [], warnings, "software")
        diag.warnings = warnings
        return diag

    # ------------------------------------------------------------------ #
    #  Individual probes
    # ------------------------------------------------------------------ #
    def _cpu(self) -> CpuInfo:
        freq = psutil.cpu_freq()
        return CpuInfo(
            usage_percent=psutil.cpu_percent(interval=0.5),
            physical_cores=psutil.cpu_count(logical=False),
            logical_cores=psutil.cpu_count(logical=True),
            frequency_mhz=round(freq.current, 1) if freq else None,
        )

    def _memory(self) -> MemoryInfo:
        vm = psutil.virtual_memory()
        return MemoryInfo(
            total_gb=round(vm.total / GB, 2),
            used_gb=round(vm.used / GB, 2),
            available_gb=round(vm.available / GB, 2),
            usage_percent=vm.percent,
        )

    def _disks(self) -> list[DiskInfo]:
        disks: list[DiskInfo] = []
        for part in psutil.disk_partitions(all=False):
            if IS_WINDOWS and "cdrom" in part.opts:
                continue
            try:
                usage = psutil.disk_usage(part.mountpoint)
            except (PermissionError, OSError):
                continue
            disks.append(
                DiskInfo(
                    device=part.device,
                    mountpoint=part.mountpoint,
                    total_gb=round(usage.total / GB, 2),
                    free_gb=round(usage.free / GB, 2),
                    used_gb=round(usage.used / GB, 2),
                    usage_percent=usage.percent,
                )
            )
        return disks

    def _network(self) -> NetworkInfo:
        adapters: list[NetworkAdapter] = []
        stats = psutil.net_if_stats()
        addrs = psutil.net_if_addrs()
        primary_ip = self._primary_ip()
        for name, addr_list in addrs.items():
            ipv4 = next((a.address for a in addr_list if a.family == socket.AF_INET), None)
            is_up = stats[name].isup if name in stats else False
            adapters.append(NetworkAdapter(name=name, ip_address=ipv4, is_up=is_up))
        return NetworkInfo(
            adapters=adapters,
            primary_ip=primary_ip,
            internet_connected=self._check_internet(),
        )

    def _os(self) -> OsInfo:
        build = None
        if IS_WINDOWS:
            build = platform.win32_ver()[1] if hasattr(platform, "win32_ver") else None
        return OsInfo(
            system=platform.system(),
            release=platform.release(),
            version=platform.version(),
            build=build,
            architecture=platform.machine(),
            hostname=socket.gethostname(),
        )

    def _battery(self) -> BatteryInfo:
        if not hasattr(psutil, "sensors_battery"):
            return BatteryInfo(present=False)
        batt = psutil.sensors_battery()
        if batt is None:
            return BatteryInfo(present=False)
        return BatteryInfo(
            present=True,
            percent=round(batt.percent, 1),
            charging=batt.power_plugged,
            secs_left=None if batt.secsleft in (psutil.POWER_TIME_UNLIMITED, psutil.POWER_TIME_UNKNOWN) else batt.secsleft,
        )

    def _processes(self, top_n: int) -> tuple[list[ProcessInfo], list[ProcessInfo]]:
        procs: list[ProcessInfo] = []
        # Prime cpu_percent counters.
        for p in psutil.process_iter(["pid", "name"]):
            try:
                p.cpu_percent(None)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        psutil.cpu_percent(None)
        # Tiny settle time handled by the 0.5s cpu interval already taken.
        for p in psutil.process_iter(["pid", "name", "memory_info"]):
            try:
                cpu = p.cpu_percent(None)
                mem = p.info["memory_info"].rss / MB if p.info.get("memory_info") else 0.0
                procs.append(
                    ProcessInfo(
                        pid=p.info["pid"],
                        name=p.info.get("name") or "unknown",
                        cpu_percent=round(cpu, 1),
                        memory_mb=round(mem, 1),
                    )
                )
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        ncpu = psutil.cpu_count() or 1
        by_cpu = sorted(procs, key=lambda x: x.cpu_percent, reverse=True)[:top_n]
        # Normalise cpu_percent to a 0-100 system-wide scale.
        for proc in by_cpu:
            proc.cpu_percent = round(proc.cpu_percent / ncpu, 1)
        by_mem = sorted(procs, key=lambda x: x.memory_mb, reverse=True)[:top_n]
        return by_cpu, by_mem

    def _startup_programs(self) -> list[StartupProgram]:
        if not IS_WINDOWS:
            return []
        programs: list[StartupProgram] = []
        try:
            import winreg  # type: ignore

            run_keys = [
                (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run"),
                (winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\Run"),
            ]
            for hive, path in run_keys:
                try:
                    with winreg.OpenKey(hive, path) as key:
                        idx = 0
                        while True:
                            try:
                                name, value, _ = winreg.EnumValue(key, idx)
                                programs.append(
                                    StartupProgram(name=name, command=str(value), location=path)
                                )
                                idx += 1
                            except OSError:
                                break
                except FileNotFoundError:
                    continue
        except Exception as exc:  # pragma: no cover - registry edge cases
            logger.debug("Startup program enumeration failed: %s", exc)
        return programs

    def _installed_software(self) -> list[InstalledSoftware]:
        """Detect tracked enterprise software via process names + registry."""
        found: dict[str, InstalledSoftware] = {
            name: InstalledSoftware(name=name, installed=False) for name in _TRACKED_SOFTWARE
        }
        running_names = set()
        for p in psutil.process_iter(["name"]):
            try:
                if p.info.get("name"):
                    running_names.add(p.info["name"].lower())
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        for display, keywords in _TRACKED_SOFTWARE.items():
            if any(any(k in rn for k in keywords) for rn in running_names):
                found[display].installed = True

        if IS_WINDOWS:
            self._enrich_software_from_registry(found)
        return list(found.values())

    def _enrich_software_from_registry(self, found: dict[str, InstalledSoftware]) -> None:
        try:
            import winreg  # type: ignore

            uninstall_paths = [
                (winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\Uninstall"),
                (winreg.HKEY_LOCAL_MACHINE, r"Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
            ]
            display_names: list[tuple[str, str | None]] = []
            for hive, path in uninstall_paths:
                try:
                    with winreg.OpenKey(hive, path) as key:
                        for i in range(winreg.QueryInfoKey(key)[0]):
                            try:
                                sub = winreg.EnumKey(key, i)
                                with winreg.OpenKey(key, sub) as subkey:
                                    name = self._reg_value(subkey, "DisplayName")
                                    version = self._reg_value(subkey, "DisplayVersion")
                                    if name:
                                        display_names.append((name, version))
                            except OSError:
                                continue
                except FileNotFoundError:
                    continue
            for display, keywords in _TRACKED_SOFTWARE.items():
                for name, version in display_names:
                    lname = name.lower()
                    if any(k in lname for k in keywords):
                        found[display].installed = True
                        found[display].version = version
                        break
        except Exception as exc:  # pragma: no cover
            logger.debug("Registry software enrichment failed: %s", exc)

    # ------------------------------------------------------------------ #
    #  Helpers
    # ------------------------------------------------------------------ #
    @staticmethod
    def _reg_value(key, name: str):  # type: ignore[no-untyped-def]
        try:
            import winreg  # type: ignore

            value, _ = winreg.QueryValueEx(key, name)
            return value
        except (FileNotFoundError, OSError):
            return None

    @staticmethod
    def _primary_ip() -> str | None:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.settimeout(0.5)
                s.connect(("8.8.8.8", 80))
                return s.getsockname()[0]
        except OSError:
            try:
                return socket.gethostbyname(socket.gethostname())
            except OSError:
                return None

    @staticmethod
    def _check_internet(host: str = "8.8.8.8", port: int = 53, timeout: float = 1.0) -> bool:
        try:
            with socket.create_connection((host, port), timeout=timeout):
                return True
        except OSError:
            return False

    @staticmethod
    def _safe(func, default, warnings: list[str], label: str):  # type: ignore[no-untyped-def]
        try:
            return func()
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Diagnostics probe '%s' failed: %s", label, exc)
            warnings.append(f"{label} probe failed: {exc}")
            return default
