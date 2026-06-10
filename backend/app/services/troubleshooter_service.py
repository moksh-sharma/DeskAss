"""Windows Troubleshooter-style full system scan.

Runs a broad set of deterministic checks over the collected diagnostics and
Windows event logs and, for every problem found, produces a structured finding
with what was detected, the likely cause, and step-by-step resolution. Each
finding is enriched with the most relevant knowledge base article and a prompt
the user can send to the AI assistant for a deeper, tailored fix.
"""
from __future__ import annotations

import sys
from collections import Counter
from datetime import datetime

import psutil

from app.core.logging import get_logger
from app.models.schemas import (
    EventLogSummary,
    Severity,
    SystemDiagnostics,
    TroubleshooterFinding,
)
from app.services.diagnostics_service import (
    CPU_CRIT,
    CPU_WARN,
    DISK_CRIT,
    DISK_WARN,
    RAM_CRIT,
    RAM_WARN,
)

logger = get_logger(__name__)

IS_WINDOWS = sys.platform == "win32"

UPTIME_WARN_HOURS = 72.0      # suggest a restart beyond 3 days of uptime
STARTUP_WARN_COUNT = 8        # many startup apps slow boot
BATTERY_LOW_PERCENT = 20.0
EVENTLOG_APP_REPEAT = 2       # an app/source crashing this many times = finding


class TroubleshooterService:
    """Analyses a system snapshot and returns prioritised troubleshooter findings."""

    def __init__(self, rag=None) -> None:  # type: ignore[no-untyped-def]
        self._rag = rag

    # ------------------------------------------------------------------ #
    #  Public API
    # ------------------------------------------------------------------ #
    def analyze(self, diagnostics: SystemDiagnostics, event_logs: EventLogSummary) -> list[TroubleshooterFinding]:
        findings: list[TroubleshooterFinding] = []

        findings += self._check_cpu(diagnostics)
        findings += self._check_memory(diagnostics)
        findings += self._check_disks(diagnostics)
        findings += self._check_network(diagnostics)
        findings += self._check_battery(diagnostics)
        findings += self._check_uptime()
        findings += self._check_startup(diagnostics)
        findings += self._check_event_logs(event_logs)
        findings += self._check_windows_servicing()

        # Order by severity (critical first), then by area.
        rank = {Severity.critical: 0, Severity.warning: 1, Severity.info: 2, Severity.healthy: 3}
        findings.sort(key=lambda f: (rank.get(f.severity, 9), f.area))

        for f in findings:
            f.references = self._kb(f.title)
        return findings

    # ------------------------------------------------------------------ #
    #  Individual checks
    # ------------------------------------------------------------------ #
    def _check_cpu(self, d: SystemDiagnostics) -> list[TroubleshooterFinding]:
        usage = d.cpu.usage_percent
        if usage < CPU_WARN:
            return []
        sev = Severity.critical if usage >= CPU_CRIT else Severity.warning
        top = d.top_cpu_processes[0] if d.top_cpu_processes else None
        top_txt = f"{top.name} ({top.cpu_percent}%)" if top else "an unknown process"
        return [
            TroubleshooterFinding(
                id="cpu_high",
                title="High CPU Usage",
                area="Performance",
                severity=sev,
                detected=f"CPU is at {usage}% (top process: {top_txt}).",
                likely_cause="A process is consuming excessive CPU, or many background tasks "
                "(updates, antivirus scan, indexer) are running at once.",
                resolution_steps=[
                    "Open Task Manager (Ctrl+Shift+Esc) and click the CPU column to sort by usage.",
                    f"Identify the top consumer (currently {top_txt}); if it is not essential, select it and click 'End task'.",
                    "Check if Windows Update or an antivirus scan is running and let it finish.",
                    "Disable unneeded startup apps: Task Manager > Startup apps tab > Disable.",
                    "Restart the PC if usage stays high after closing heavy processes.",
                    "If a specific app always pins the CPU, update or reinstall it.",
                ],
                ask_ai_prompt=f"My PC has high CPU usage at {usage}% with {top_txt} at the top. "
                "What is causing this and how do I fix it?",
            )
        ]

    def _check_memory(self, d: SystemDiagnostics) -> list[TroubleshooterFinding]:
        usage = d.memory.usage_percent
        if usage < RAM_WARN:
            return []
        sev = Severity.critical if usage >= RAM_CRIT else Severity.warning
        top = d.top_memory_processes[0] if d.top_memory_processes else None
        top_txt = f"{top.name} ({top.memory_mb} MB)" if top else "an unknown process"
        return [
            TroubleshooterFinding(
                id="ram_high",
                title="High Memory Usage",
                area="Performance",
                severity=sev,
                detected=f"RAM is at {usage}% used, only {d.memory.available_gb} GB free "
                f"(top process: {top_txt}).",
                likely_cause="Too many apps/tabs are open, or an app has a memory leak, forcing "
                "Windows to page to disk and slow down.",
                resolution_steps=[
                    "Open Task Manager (Ctrl+Shift+Esc) and sort by Memory.",
                    f"Close memory-heavy apps you don't need (currently {top_txt}).",
                    "Reduce open browser tabs; restart the browser to release leaked memory.",
                    "Restart the PC to clear memory if uptime is high.",
                    "Disable unnecessary startup apps to lower idle memory use.",
                    "If memory is consistently full, consider adding more RAM.",
                ],
                ask_ai_prompt=f"My PC memory is at {usage}% with only {d.memory.available_gb} GB free "
                f"and {top_txt} using the most. How do I fix high memory usage?",
            )
        ]

    def _check_disks(self, d: SystemDiagnostics) -> list[TroubleshooterFinding]:
        out: list[TroubleshooterFinding] = []
        for disk in d.disks:
            if disk.usage_percent < DISK_WARN:
                continue
            sev = Severity.critical if disk.usage_percent >= DISK_CRIT else Severity.warning
            out.append(
                TroubleshooterFinding(
                    id=f"disk_low_{disk.device.strip(':\\/').lower() or 'x'}",
                    title="Low Disk Space",
                    area="Storage",
                    severity=sev,
                    detected=f"Drive {disk.device} is {disk.usage_percent}% full "
                    f"({disk.free_gb} GB free of {disk.total_gb} GB).",
                    likely_cause="Temporary files, Windows Update leftovers, large downloads, or "
                    "locally-synced cloud files are filling the drive.",
                    resolution_steps=[
                        "Open Settings > System > Storage to see what is using space.",
                        "Run Disk Cleanup (`cleanmgr`) and tick 'Temporary files' and 'Windows Update Cleanup'.",
                        "Empty the Recycle Bin and clear %TEMP%.",
                        "Uninstall unused apps: Settings > Apps > Installed apps.",
                        "Move large folders (Downloads, videos) to another drive; set OneDrive to 'online-only'.",
                        "Turn on Storage Sense to auto-clean temporary files.",
                    ],
                    ask_ai_prompt=f"My drive {disk.device} is {disk.usage_percent}% full with only "
                    f"{disk.free_gb} GB free. How do I free up space safely?",
                )
            )
        return out

    def _check_network(self, d: SystemDiagnostics) -> list[TroubleshooterFinding]:
        if d.network.internet_connected:
            return []
        return [
            TroubleshooterFinding(
                id="no_internet",
                title="No Internet Connectivity",
                area="Network",
                severity=Severity.warning,
                detected="The system could not reach the internet during the scan.",
                likely_cause="Wi-Fi/Ethernet is down, DHCP/DNS failed, or a VPN/proxy is misconfigured.",
                resolution_steps=[
                    "Confirm Wi-Fi is on / the Ethernet cable is connected; check other devices for internet.",
                    "Run the Network troubleshooter: Settings > Network & internet > Status.",
                    "Renew the connection in an elevated prompt: `ipconfig /release`, `ipconfig /renew`, `ipconfig /flushdns`.",
                    "Reset the network stack: `netsh winsock reset`, `netsh int ip reset`, then restart.",
                    "Temporarily disable VPN/proxy to test.",
                    "Reboot the router/modem (power off 30 seconds).",
                ],
                ask_ai_prompt="My PC has no internet connection. How do I diagnose and fix it?",
            )
        ]

    def _check_battery(self, d: SystemDiagnostics) -> list[TroubleshooterFinding]:
        b = d.battery
        if not b.present or b.percent is None:
            return []
        if b.percent >= BATTERY_LOW_PERCENT or b.charging:
            return []
        return [
            TroubleshooterFinding(
                id="battery_low",
                title="Battery Low / Not Charging",
                area="Power",
                severity=Severity.warning,
                detected=f"Battery is at {b.percent}% and not charging.",
                likely_cause="The charger isn't connected/working, or the battery is degraded.",
                resolution_steps=[
                    "Connect a known-good charger and confirm the charging indicator turns on.",
                    "Inspect the charging port and cable for damage or debris.",
                    "Generate a battery health report: run `powercfg /batteryreport` and compare full-charge vs design capacity.",
                    "Reinstall the battery driver: Device Manager > Batteries > 'Microsoft ACPI-Compliant Control Method Battery' > uninstall > scan for hardware changes.",
                    "Update BIOS/UEFI and chipset drivers from the manufacturer.",
                    "Replace the battery if capacity is badly degraded.",
                ],
                ask_ai_prompt=f"My laptop battery is at {b.percent}% and not charging. How do I fix charging problems?",
            )
        ]

    def _check_uptime(self) -> list[TroubleshooterFinding]:
        try:
            boot = psutil.boot_time()
            hours = (datetime.now().timestamp() - boot) / 3600.0
        except Exception:
            return []
        if hours < UPTIME_WARN_HOURS:
            return []
        days = round(hours / 24.0, 1)
        return [
            TroubleshooterFinding(
                id="high_uptime",
                title="PC Needs a Restart",
                area="Performance",
                severity=Severity.info,
                detected=f"The PC has been running for about {days} days without a restart.",
                likely_cause="Long uptime lets memory leaks accumulate and leaves updates pending, "
                "which can cause slowness and instability.",
                resolution_steps=[
                    "Save your work and close apps.",
                    "Restart the PC (Start > Power > Restart) - this clears memory and applies pending updates.",
                    "After restart, check Windows Update: Settings > Windows Update > Check for updates.",
                ],
                ask_ai_prompt=f"My PC has been on for {days} days and feels slow. Should I restart and what else should I check?",
            )
        ]

    def _check_startup(self, d: SystemDiagnostics) -> list[TroubleshooterFinding]:
        count = len(d.startup_programs)
        if count < STARTUP_WARN_COUNT:
            return []
        names = ", ".join(p.name for p in d.startup_programs[:5])
        return [
            TroubleshooterFinding(
                id="many_startup_apps",
                title="Too Many Startup Programs",
                area="Startup",
                severity=Severity.info,
                detected=f"{count} programs are set to launch at startup (e.g. {names}).",
                likely_cause="Many auto-start apps slow boot and consume CPU/RAM in the background.",
                resolution_steps=[
                    "Open Task Manager (Ctrl+Shift+Esc) > Startup apps tab.",
                    "Review the 'Startup impact' column and disable apps you don't need at boot (right-click > Disable).",
                    "Keep security and essential drivers enabled; disable updaters, chat, and media apps.",
                    "Restart and confirm boot is faster.",
                ],
                ask_ai_prompt=f"I have {count} startup programs and slow boot. Which are safe to disable?",
            )
        ]

    def _check_event_logs(self, logs: EventLogSummary) -> list[TroubleshooterFinding]:
        if not logs.available or not logs.entries:
            return []
        out: list[TroubleshooterFinding] = []
        errors = [e for e in logs.entries if e.level == "Error"]

        # 1. App crash/hang clusters by source.
        crash_sources = Counter(
            e.source for e in errors if e.category in ("Application Crash", "Application Hang")
        )
        for source, n in crash_sources.items():
            if n < EVENTLOG_APP_REPEAT:
                continue
            out.append(
                TroubleshooterFinding(
                    id=f"app_crash_{source.lower()}",
                    title=f"App Repeatedly Crashing: {source}",
                    area="Stability",
                    severity=Severity.warning,
                    detected=f"{n} crash/hang error events from '{source}' in recent logs.",
                    likely_cause="A corrupt installation, faulty add-in/plugin, missing runtime, or "
                    "incompatible driver is causing the application to crash.",
                    resolution_steps=[
                        f"Update {source} to the latest version and restart the PC.",
                        f"Repair the app: Settings > Apps > Installed apps > {source} > Modify/Advanced options > Repair.",
                        "Disable add-ins/plugins, then re-enable one at a time to find the culprit.",
                        "Install the latest Visual C++ Redistributables and .NET Desktop Runtime.",
                        "Clear the app's cache/settings folder (back it up first).",
                        "Test in a new Windows user profile to rule out profile corruption.",
                    ],
                    ask_ai_prompt=f"The app '{source}' is crashing repeatedly ({n} error events in my Windows logs). "
                    "What is causing this and how do I resolve it?",
                )
            )

        # 2. Disk / NTFS errors -> possible failing drive.
        disk_errs = [e for e in errors if e.category == "Disk"]
        if len(disk_errs) >= EVENTLOG_APP_REPEAT:
            out.append(
                TroubleshooterFinding(
                    id="disk_errors",
                    title="Disk / File System Errors",
                    area="Storage",
                    severity=Severity.critical,
                    detected=f"{len(disk_errs)} disk/NTFS error events in recent logs.",
                    likely_cause="Bad sectors, a failing drive, or a loose connection are causing I/O errors.",
                    resolution_steps=[
                        "Back up important data immediately - a failing drive can fail without warning.",
                        "Check drive health/SMART with the vendor tool (e.g. CrystalDiskInfo).",
                        "Run `chkdsk C: /f /r` (it will schedule on next reboot for the system drive).",
                        "Reseat SATA/NVMe and power cables (desktops); try another port.",
                        "Update storage drivers and the SSD firmware.",
                        "Replace the drive if SMART shows failures or errors persist.",
                    ],
                    ask_ai_prompt=f"My Windows logs show {len(disk_errs)} disk/NTFS errors. "
                    "Is my drive failing and how do I fix it?",
                )
            )

        # 3. Unexpected shutdowns (Kernel-Power 41 pattern).
        power_errs = [
            e for e in errors
            if (e.event_id == 41) or ("kernel-power" in (e.source or "").lower())
            or ("unexpected" in (e.message or "").lower() and "shut" in (e.message or "").lower())
        ]
        if power_errs:
            out.append(
                TroubleshooterFinding(
                    id="unexpected_shutdown",
                    title="Unexpected Shutdowns / Restarts",
                    area="Stability",
                    severity=Severity.warning,
                    detected=f"{len(power_errs)} unexpected shutdown/power events (e.g. Kernel-Power 41).",
                    likely_cause="Overheating, a failing power supply/battery, unstable RAM, or a driver "
                    "fault is causing the system to reset without a clean shutdown.",
                    resolution_steps=[
                        "Check CPU/GPU temperatures under load; clean dust from fans and vents.",
                        "Test memory: run Windows Memory Diagnostic (`mdsched.exe`).",
                        "Update chipset, GPU, and storage drivers; roll back any recent driver.",
                        "For desktops, reseat power connectors and test the PSU; for laptops, test the charger and check battery health.",
                        "Remove any overclock; reset BIOS/UEFI to defaults.",
                        "Disable automatic restart to capture any blue-screen code: System Properties > Advanced > Startup and Recovery.",
                    ],
                    ask_ai_prompt=f"My PC has {len(power_errs)} unexpected shutdown events (Kernel-Power 41) in the logs. "
                    "What causes this and how do I fix it?",
                )
            )

        # 4. Generic high error volume (only if nothing more specific was found).
        if not out and logs.error_count >= 10:
            out.append(
                TroubleshooterFinding(
                    id="many_errors",
                    title="High Volume of Error Events",
                    area="Stability",
                    severity=Severity.warning,
                    detected=f"{logs.error_count} error events and {logs.warning_count} warnings in recent logs.",
                    likely_cause="Multiple components are logging errors; system files or a service may be unhealthy.",
                    resolution_steps=[
                        "Open Event Viewer (`eventvwr.msc`) > Windows Logs > Application and System to review the errors.",
                        "Run `sfc /scannow` then `DISM /Online /Cleanup-Image /RestoreHealth`.",
                        "Install pending Windows Updates and restart.",
                        "Note any repeating source/Event ID and address that component specifically.",
                    ],
                    ask_ai_prompt=f"My Windows logs have {logs.error_count} errors and {logs.warning_count} warnings. "
                    "How do I find and fix the underlying problems?",
                )
            )
        return out

    def _check_windows_servicing(self) -> list[TroubleshooterFinding]:
        if not IS_WINDOWS:
            return []
        out: list[TroubleshooterFinding] = []

        if self._pending_reboot():
            out.append(
                TroubleshooterFinding(
                    id="pending_reboot",
                    title="Restart Required to Finish Updates",
                    area="System",
                    severity=Severity.info,
                    detected="Windows has a pending reboot from updates or installs.",
                    likely_cause="Updates or software changes are staged and need a restart to complete.",
                    resolution_steps=[
                        "Save your work and restart the PC (Start > Power > Restart).",
                        "After restart, check Settings > Windows Update for any remaining updates.",
                    ],
                    ask_ai_prompt="Windows says a restart is pending for updates. What should I do?",
                )
            )

        wu = self._service_state("wuauserv")
        if wu == "stopped_disabled":
            out.append(
                TroubleshooterFinding(
                    id="windows_update_disabled",
                    title="Windows Update Service Disabled",
                    area="Security",
                    severity=Severity.warning,
                    detected="The Windows Update service (wuauserv) is disabled.",
                    likely_cause="The update service was turned off (by a tool, policy, or malware), so the "
                    "PC won't receive security patches.",
                    resolution_steps=[
                        "Open Services (`services.msc`) and find 'Windows Update'.",
                        "Set Startup type to 'Manual' (or Automatic) and click Start.",
                        "Run the Windows Update troubleshooter: Settings > System > Troubleshoot > Other troubleshooters.",
                        "Check Settings > Windows Update and install available updates.",
                        "Scan for malware if the service keeps getting disabled.",
                    ],
                    ask_ai_prompt="My Windows Update service is disabled. How do I re-enable it and get updates working?",
                )
            )
        return out

    # ------------------------------------------------------------------ #
    #  Windows probes (defensive)
    # ------------------------------------------------------------------ #
    @staticmethod
    def _pending_reboot() -> bool:
        try:
            import winreg  # type: ignore
        except Exception:
            return False
        checks = [
            (winreg.HKEY_LOCAL_MACHINE,
             r"SOFTWARE\Microsoft\Windows\CurrentVersion\Component Based Servicing\RebootPending"),
            (winreg.HKEY_LOCAL_MACHINE,
             r"SOFTWARE\Microsoft\Windows\CurrentVersion\WindowsUpdate\Auto Update\RebootRequired"),
        ]
        for hive, path in checks:
            try:
                with winreg.OpenKey(hive, path):
                    return True
            except FileNotFoundError:
                continue
            except OSError:
                continue
        # PendingFileRenameOperations on the Session Manager key.
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                                r"SYSTEM\CurrentControlSet\Control\Session Manager") as key:
                value, _ = winreg.QueryValueEx(key, "PendingFileRenameOperations")
                if value:
                    return True
        except (FileNotFoundError, OSError):
            pass
        return False

    @staticmethod
    def _service_state(name: str) -> str:
        """Return 'running', 'stopped', 'stopped_disabled', or 'unknown'."""
        try:
            svc = psutil.win_service_get(name)
            info = svc.as_dict()
            status = info.get("status", "")
            start = info.get("start_type", "")
            if status == "running":
                return "running"
            if start == "disabled":
                return "stopped_disabled"
            return "stopped"
        except Exception:
            return "unknown"

    # ------------------------------------------------------------------ #
    #  KB enrichment
    # ------------------------------------------------------------------ #
    def _kb(self, query: str):  # type: ignore[no-untyped-def]
        if self._rag is None:
            return []
        try:
            refs = self._rag.retrieve(query, top_k=1)
            return [r for r in refs if r.score >= 0.35]
        except Exception as exc:  # pragma: no cover
            logger.debug("KB enrichment failed for '%s': %s", query, exc)
            return []
