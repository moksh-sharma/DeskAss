"""Storage live probe pack: per-disk free space and SMART health hints."""
from __future__ import annotations

import psutil

from app.models.schemas import ProbeCheck, ProbeResult, Severity, TroubleshooterFinding
from app.services.probes.base import IS_WINDOWS, ProbeContext, ProbeOutcome, as_list, ps_json

DOMAIN = "storage"
TITLE = "Storage"

GB = 1024 ** 3
WARN = 85.0
CRIT = 95.0


def _smart() -> list[dict]:
    if not IS_WINDOWS:
        return []
    return as_list(ps_json(
        "Get-PhysicalDisk -ErrorAction SilentlyContinue | "
        "Select-Object FriendlyName,HealthStatus,MediaType | ConvertTo-Json -Compress"
    ))


def investigate(ctx: ProbeContext) -> ProbeOutcome:
    checks: list[ProbeCheck] = []
    findings: list[TroubleshooterFinding] = []

    for part in psutil.disk_partitions(all=False):
        if IS_WINDOWS and "cdrom" in part.opts:
            continue
        try:
            usage = psutil.disk_usage(part.mountpoint)
        except (PermissionError, OSError):
            continue
        pct = usage.percent
        free_gb = round(usage.free / GB, 1)
        sev = Severity.healthy
        if pct >= CRIT:
            sev = Severity.critical
        elif pct >= WARN:
            sev = Severity.warning
        checks.append(ProbeCheck(
            label=f"Drive {part.device}",
            value=f"{pct}% used, {free_gb} GB free",
            status=sev,
        ))
        if sev != Severity.healthy:
            findings.append(TroubleshooterFinding(
                id=f"storage_low_{part.device.strip(':/\\\\').lower() or 'x'}",
                title=f"Low Disk Space on {part.device}",
                area="Storage",
                severity=sev,
                detected=f"Drive {part.device} is {pct}% full ({free_gb} GB free).",
                likely_cause="Temporary files, Windows Update leftovers, large downloads, or synced cloud files.",
                resolution_steps=[
                    "Open Settings > System > Storage to see what's using space.",
                    "Run Disk Cleanup (`cleanmgr`) - tick 'Temporary files' and 'Windows Update Cleanup'.",
                    "Empty the Recycle Bin and clear `%TEMP%`.",
                    "Uninstall unused apps: Settings > Apps > Installed apps.",
                    "Enable Storage Sense to auto-clean.",
                ],
                ask_ai_prompt=f"My drive {part.device} is {pct}% full. How do I safely free up space?",
            ))

    for d in _smart():
        health = str(d.get("HealthStatus", ""))
        ok = health.lower() == "healthy"
        checks.append(ProbeCheck(
            label=f"Disk health: {d.get('FriendlyName','disk')}",
            value=f"{health} ({d.get('MediaType','?')})",
            status=Severity.healthy if ok else Severity.critical,
        ))
        if not ok and health:
            findings.append(TroubleshooterFinding(
                id="storage_smart_unhealthy",
                title="Drive Health Warning (SMART)",
                area="Storage",
                severity=Severity.critical,
                detected=f"Physical disk '{d.get('FriendlyName')}' reports health '{health}'.",
                likely_cause="The drive may be failing.",
                resolution_steps=[
                    "Back up important data immediately.",
                    "Check SMART details with the vendor tool or CrystalDiskInfo.",
                    "Run `chkdsk C: /f /r` (schedules on next reboot for the system drive).",
                    "Plan to replace the drive if health doesn't recover.",
                ],
                ask_ai_prompt="My drive reports an unhealthy SMART status. Is it failing and what do I do?",
            ))

    return ProbeOutcome(
        result=ProbeResult(domain=DOMAIN, title=TITLE, available=True, checks=checks),
        findings=findings,
    )
