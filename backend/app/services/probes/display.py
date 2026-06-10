"""Display/GPU live probe pack: graphics adapters, driver status, monitors."""
from __future__ import annotations

from app.models.schemas import ProbeCheck, ProbeResult, Severity, TroubleshooterFinding
from app.services.probes.base import (
    IS_WINDOWS,
    ProbeContext,
    ProbeOutcome,
    as_list,
    is_real_device_problem,
    ps_json,
    unavailable,
)

DOMAIN = "display"
TITLE = "Display & Graphics"


def _gpus() -> list[dict]:
    return as_list(ps_json(
        "Get-PnpDevice -Class Display -ErrorAction SilentlyContinue | "
        "Select-Object FriendlyName,Status,Problem,ProblemDescription | ConvertTo-Json -Compress"
    ))


def _monitors() -> list[dict]:
    return as_list(ps_json(
        "Get-PnpDevice -Class Monitor -ErrorAction SilentlyContinue | "
        "Where-Object { $_.Status -eq 'OK' } | "
        "Select-Object FriendlyName,Status | ConvertTo-Json -Compress"
    ))


def investigate(ctx: ProbeContext) -> ProbeOutcome:
    if not IS_WINDOWS:
        return unavailable(DOMAIN, TITLE, "Display probe only runs on Windows.")

    checks: list[ProbeCheck] = []
    findings: list[TroubleshooterFinding] = []

    gpus = _gpus()
    if not gpus:
        checks.append(ProbeCheck(label="Graphics adapter", value="None found", status=Severity.warning))
    for g in gpus:
        name = g.get("FriendlyName") or "GPU"
        status = str(g.get("Status", ""))
        real_problem = is_real_device_problem(status, g.get("Problem"))
        ok = not real_problem
        checks.append(ProbeCheck(
            label=f"GPU: {name}",
            value=status + (f" (code {g.get('Problem')})" if g.get("Problem") and real_problem else ""),
            status=Severity.healthy if ok else Severity.critical,
            detail=g.get("ProblemDescription"),
        ))
        if real_problem:
            findings.append(TroubleshooterFinding(
                id="display_gpu_problem",
                title=f"Graphics Driver Problem: {name}",
                area="Display",
                severity=Severity.critical,
                detected=f"GPU '{name}' status is '{status}'"
                + (f", code {g.get('Problem')}" if g.get("Problem") else "") + ".",
                likely_cause="A corrupt, missing, or incompatible graphics driver (often after an update).",
                resolution_steps=[
                    f"Device Manager > Display adapters > '{name}' > Update driver.",
                    "If it started after an update, roll back the driver (Driver tab > Roll Back Driver).",
                    "Download the latest driver from Intel/NVIDIA/AMD or your PC maker.",
                    "Uninstall the device and Scan for hardware changes to reinstall.",
                    "Restart the PC.",
                ],
                ask_ai_prompt=f"My graphics adapter '{name}' shows a driver problem. How do I fix the display driver?",
            ))

    monitors = _monitors()
    checks.append(ProbeCheck(
        label="Monitors detected",
        value=str(len(monitors)),
        status=Severity.healthy if monitors else Severity.warning,
    ))

    # If user reports an external monitor not detected and only one monitor is present.
    wants_external = any(w in ctx.message.lower() for w in ("external", "second", "hdmi", "monitor", "no signal"))
    if wants_external and len(monitors) <= 1 and gpus:
        findings.append(TroubleshooterFinding(
            id="display_external_not_detected",
            title="External Monitor May Not Be Detected",
            area="Display",
            severity=Severity.warning,
            detected=f"Only {len(monitors)} active monitor detected while an external display issue was reported.",
            likely_cause="Cable/input mismatch, the second screen isn't selected, or a display driver issue.",
            resolution_steps=[
                "Press Win+P and choose 'Extend' or 'Duplicate'.",
                "Force a detect: Settings > System > Display > Multiple displays > Detect.",
                "Try a different cable/port (HDMI/DisplayPort) and confirm the monitor's input source.",
                "Update the graphics driver.",
            ],
            ask_ai_prompt="My external monitor isn't detected. How do I get Windows to see the second screen?",
        ))

    return ProbeOutcome(
        result=ProbeResult(domain=DOMAIN, title=TITLE, available=True, checks=checks),
        findings=findings,
    )
