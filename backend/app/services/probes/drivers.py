"""Driver update live probe: Windows Update availability and problem devices."""
from __future__ import annotations

from app.models.schemas import ProbeCheck, ProbeResult, Severity, TroubleshooterFinding
from app.services.probes.base import IS_WINDOWS, ProbeContext, ProbeOutcome, unavailable
from app.services.scanners import drivers as drivers_scanner


def investigate(ctx: ProbeContext) -> ProbeOutcome:
    if not IS_WINDOWS:
        return unavailable("driver", "Drivers & Updates", "Driver probe only runs on Windows.")

    data = drivers_scanner.scan()
    if not data.get("available"):
        return unavailable("driver", "Drivers & Updates", data.get("note") or "Driver scan failed.")

    checks: list[ProbeCheck] = []
    findings: list[TroubleshooterFinding] = []
    updates = data.get("available_updates") or []
    problems = data.get("problem_devices") or []
    wu_err = data.get("windows_update_error")

    if wu_err:
        checks.append(ProbeCheck(
            label="Windows Update driver check",
            value="Could not query",
            status=Severity.warning,
            detail=str(wu_err)[:160],
        ))
    else:
        checks.append(ProbeCheck(
            label="Driver updates available",
            value=str(len(updates)),
            status=Severity.warning if updates else Severity.healthy,
            detail="; ".join((u.get("title") or "?") for u in updates[:3]) or "None pending",
        ))

    checks.append(ProbeCheck(
        label="Devices with driver problems",
        value=str(len(problems)),
        status=Severity.critical if problems else Severity.healthy,
        detail="; ".join(f"{p.get('name')} ({p.get('problem')})" for p in problems[:3]) or "None",
    ))

    if updates:
        titles = ", ".join((u.get("title") or "?") for u in updates[:4])
        findings.append(TroubleshooterFinding(
            id="probe_driver_updates",
            title=f"{len(updates)} Driver Update(s) Available",
            area="Drivers",
            severity=Severity.info,
            detected=f"Windows Update has driver updates: {titles}.",
            likely_cause="Newer signed drivers are available for one or more devices.",
            resolution_steps=[
                "Settings > Windows Update > Check for updates.",
                "Advanced options > Optional updates > Driver updates.",
            ],
            ask_ai_prompt="Which drivers on my PC need updates?",
        ))
    elif problems:
        names = ", ".join(p.get("name") or "?" for p in problems[:4])
        findings.append(TroubleshooterFinding(
            id="probe_driver_problems",
            title="Device(s) With Driver Problems",
            area="Drivers",
            severity=Severity.warning,
            detected=f"Devices needing attention: {names}.",
            likely_cause="Missing, failed, or incompatible drivers.",
            resolution_steps=[
                "Open Device Manager and update or reinstall affected drivers.",
            ],
            ask_ai_prompt="Which devices on my PC have driver problems?",
        ))
    elif not wu_err:
        findings.append(TroubleshooterFinding(
            id="probe_drivers_current",
            title="No Pending Driver Updates",
            area="Drivers",
            severity=Severity.healthy,
            detected="Windows Update shows no pending driver updates and no driver errors were found.",
            likely_cause="Installed drivers appear current via Windows Update.",
            resolution_steps=[
                "Optional: check Optional updates under Windows Update for extra drivers.",
            ],
            ask_ai_prompt="Are my drivers up to date?",
        ))

    return ProbeOutcome(
        result=ProbeResult(domain="driver", title="Drivers & Updates", available=True, checks=checks),
        findings=findings,
    )
