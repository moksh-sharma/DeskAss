"""Windows Update live probe pack: service state, pending reboot, update errors."""
from __future__ import annotations

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

DOMAIN = "windows_update"
TITLE = "Windows Update"


def _pending_reboot() -> bool:
    script = (
        "$p=$false;"
        "if (Test-Path 'HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Component Based Servicing\\RebootPending') {$p=$true};"
        "if (Test-Path 'HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\WindowsUpdate\\Auto Update\\RebootRequired') {$p=$true};"
        "$p | ConvertTo-Json -Compress"
    )
    ok, out = run_powershell(script)
    return ok and out.strip().lower() == "true"


def _recent_failed_updates() -> list[dict]:
    return as_list(ps_json(
        "Get-WinEvent -FilterHashtable @{LogName='System'; ProviderName='Microsoft-Windows-WindowsUpdateClient'; Level=2,3} "
        "-MaxEvents 10 -ErrorAction SilentlyContinue | "
        "Select-Object Id,LevelDisplayName,TimeCreated,Message | ConvertTo-Json -Compress",
        timeout=25.0,
    ))


def investigate(ctx: ProbeContext) -> ProbeOutcome:
    if not IS_WINDOWS:
        return unavailable(DOMAIN, TITLE, "Windows Update probe only runs on Windows.")

    checks: list[ProbeCheck] = []
    findings: list[TroubleshooterFinding] = []

    svc = get_service("wuauserv")
    if svc:
        status = str(svc.get("Status", ""))
        start = str(svc.get("StartType", ""))
        disabled = start.lower() == "disabled"
        checks.append(ProbeCheck(
            label="Windows Update service",
            value=f"{status} (start: {start})",
            status=Severity.warning if disabled else Severity.healthy,
        ))
        if disabled:
            findings.append(TroubleshooterFinding(
                id="wu_service_disabled",
                title="Windows Update Service Disabled",
                area="Windows Update",
                severity=Severity.warning,
                detected="The Windows Update service (wuauserv) is disabled.",
                likely_cause="The service was turned off (tool, policy, or malware), so the PC won't get patches.",
                resolution_steps=[
                    "Open Services (`services.msc`) > 'Windows Update'.",
                    "Set Startup type to Manual (or Automatic) and Start it.",
                    "Run the Windows Update troubleshooter: Settings > System > Troubleshoot.",
                    "Check Settings > Windows Update and install updates.",
                ],
                ask_ai_prompt="My Windows Update service is disabled. How do I re-enable it and get updates?",
            ))

    pending = _pending_reboot()
    checks.append(ProbeCheck(
        label="Pending reboot",
        value="Yes" if pending else "No",
        status=Severity.warning if pending else Severity.healthy,
    ))
    if pending:
        findings.append(TroubleshooterFinding(
            id="wu_pending_reboot",
            title="Restart Required to Finish Updates",
            area="Windows Update",
            severity=Severity.info,
            detected="Windows has a pending reboot from updates or installs.",
            likely_cause="Updates are staged and need a restart to complete; this can cause odd behavior until done.",
            resolution_steps=[
                "Save your work and restart the PC (Start > Power > Restart).",
                "After restart, check Settings > Windows Update for remaining updates.",
            ],
            ask_ai_prompt="Windows says a restart is pending for updates. What should I do?",
        ))

    failed = _recent_failed_updates()
    if failed:
        top = failed[0]
        checks.append(ProbeCheck(
            label="Recent update issues",
            value=f"{len(failed)} event(s)",
            status=Severity.warning,
            detail=f"ID {top.get('Id')}: {str(top.get('Message',''))[:120]}",
        ))
        findings.append(TroubleshooterFinding(
            id="wu_update_failures",
            title="Recent Windows Update Failures",
            area="Windows Update",
            severity=Severity.warning,
            detected=f"{len(failed)} recent Windows Update warning/error event(s).",
            likely_cause="A failed/stuck update - corrupted update components or insufficient disk space.",
            resolution_steps=[
                "Run the Windows Update troubleshooter: Settings > System > Troubleshoot > Other troubleshooters.",
                "Free up disk space if low, then retry the update.",
                "Repair components (elevated): `DISM /Online /Cleanup-Image /RestoreHealth` then `sfc /scannow`.",
                "Restart and check for updates again.",
            ],
            ask_ai_prompt="My Windows updates keep failing. How do I fix update errors?",
        ))

    return ProbeOutcome(
        result=ProbeResult(domain=DOMAIN, title=TITLE, available=True, checks=checks),
        findings=findings,
    )
