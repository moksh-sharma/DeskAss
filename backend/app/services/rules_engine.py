"""Deterministic rules engine — IF/THEN diagnostics with no LLM.

Rules evaluate live scan data and telemetry. Each rule produces zero or one
``TroubleshooterFinding`` with a stable ``rule_id`` for auditability.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from app.models.schemas import IssueProfile, Severity, TroubleshooterFinding

RuleFn = Callable[[dict[str, Any], IssueProfile, str], TroubleshooterFinding | None]


@dataclass(frozen=True)
class DiagnosticRule:
    rule_id: str
    title: str
    evaluate: RuleFn


def _num(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _finding(
    rule_id: str,
    title: str,
    area: str,
    severity: Severity,
    detected: str,
    cause: str,
    steps: list[str],
) -> TroubleshooterFinding:
    return TroubleshooterFinding(
        id=f"rule_{rule_id}",
        title=title,
        area=area,
        severity=severity,
        detected=detected,
        likely_cause=cause,
        resolution_steps=steps,
        ask_ai_prompt="",
    )


def _rule_cpu_saturation(hw: dict, _profile: IssueProfile, _msg: str) -> TroubleshooterFinding | None:
    perf = (hw.get("performance") or {}) if isinstance(hw, dict) else {}
    cpu = _num(perf.get("cpu_usage_percent") or perf.get("current_usage_pct"))
    if cpu is None:
        cpu = _num(((hw.get("cpu") or {}).get("current_usage_pct")))
    if cpu is None or cpu < 90:
        return None
    procs = (perf.get("top_cpu") or [])[:5]
    lines = [
        f"{p.get('name', '?')}: {_num(p.get('cpu_pct')) or '?'}%"
        for p in procs
        if p.get("name")
    ]
    detail = f"CPU at {cpu:.0f}%."
    if lines:
        detail += " Top consumers: " + ", ".join(lines) + "."
    return _finding(
        "cpu_saturation",
        "CPU Saturation",
        "Performance",
        Severity.critical if cpu >= 95 else Severity.warning,
        detected=detail,
        cause="Sustained high CPU usage limits responsiveness.",
        steps=[
            "Open Task Manager > Processes and end unnecessary high-CPU tasks.",
            "Close unused browser tabs or restart the heaviest application.",
            "Restart the PC if CPU stays high with no clear cause.",
        ],
    )


def _rule_storage_exhaustion(hw: dict, profile: IssueProfile, _msg: str) -> TroubleshooterFinding | None:
    drives = ((hw.get("storage") or {}).get("logical_drives") or [])
    if not drives and isinstance(hw.get("disks"), list):
        drives = hw.get("disks") or []
    target = (profile.target_drive or "").rstrip(":").upper()
    worst = None
    for d in drives:
        used = _num(d.get("usage_percent"))
        if used is None:
            total = _num(d.get("total_gb"))
            free = _num(d.get("free_gb"))
            if total and free is not None:
                used = ((total - free) / total) * 100
        letter = str(d.get("drive") or d.get("name") or "").upper()
        if target and target not in letter:
            continue
        if used is not None and (worst is None or used > worst[0]):
            worst = (used, letter or "drive")
    if not worst or worst[0] < 95:
        return None
    used_pct, label = worst
    return _finding(
        "storage_exhaustion",
        "Storage Exhaustion",
        "Storage",
        Severity.critical,
        detected=f"Drive {label} is {used_pct:.0f}% full.",
        cause="Very low free disk space causes slowdowns, update failures, and crashes.",
        steps=[
            "Run Disk Cleanup (cleanmgr) on the affected drive.",
            "Remove large downloads, old installers, and unused applications.",
            "Move personal files to another drive or cloud storage.",
        ],
    )


def _rule_battery_degradation(hw: dict, _profile: IssueProfile, _msg: str) -> TroubleshooterFinding | None:
    bat = (hw.get("battery") or {}) if isinstance(hw, dict) else {}
    wear = _num(bat.get("wear_percent"))
    health = _num(bat.get("health_percent"))
    degradation = wear if wear is not None else (100 - health if health is not None else None)
    if degradation is None or degradation < 30:
        return None
    return _finding(
        "battery_degradation",
        "Battery Degradation",
        "Hardware",
        Severity.warning,
        detected=f"Battery wear/degradation estimated at {degradation:.0f}%.",
        cause="Aged batteries hold less charge and can cause unexpected shutdowns.",
        steps=[
            "Check battery health in Settings > System > Power & battery.",
            "Reduce background apps when on battery power.",
            "Plan for battery replacement if runtime is insufficient.",
        ],
    )


def _rule_display_driver_failure(_hw: dict, _profile: IssueProfile, _msg: str) -> TroubleshooterFinding | None:
    sw = _hw if False else {}  # event data passed via report in evaluate_all
    return None  # handled via event-log rule below


def _rule_event_4101(sw: dict, _profile: IssueProfile, _msg: str) -> TroubleshooterFinding | None:
    logs = (sw.get("event_logs") or {}) if isinstance(sw, dict) else {}
    for bucket in ("system", "application"):
        for entry in logs.get(bucket) or []:
            eid = entry.get("event_id") or entry.get("EventID")
            if str(eid) == "4101":
                return _finding(
                    "display_driver_failure",
                    "Display Driver Failure",
                    "Drivers",
                    Severity.warning,
                    detected=f"Event ID 4101 in {entry.get('log_name', 'System')} log: "
                    f"{entry.get('message', 'Display driver stopped responding')[:120]}.",
                    cause="GPU/display driver reset — often driver bug, overheating, or power state.",
                    steps=[
                        "Update graphics drivers from the PC or GPU vendor site.",
                        "Disable hardware acceleration in apps that trigger the crash.",
                        "Check GPU temperature and ensure adequate cooling.",
                    ],
                )
    return None


def _rule_ram_pressure(hw: dict, _profile: IssueProfile, _msg: str) -> TroubleshooterFinding | None:
    perf = (hw.get("performance") or {})
    ram = _num(perf.get("memory_usage_percent"))
    if ram is None:
        mem = hw.get("memory") or {}
        total = _num(mem.get("total_gb"))
        used = _num(mem.get("used_gb"))
        if total and used is not None:
            ram = (used / total) * 100
    if ram is None or ram < 90:
        return None
    return _finding(
        "ram_pressure",
        "Memory Pressure",
        "Performance",
        Severity.warning,
        detected=f"RAM usage at {ram:.0f}%.",
        cause="High memory use causes paging, freezes, and application crashes.",
        steps=[
            "Close unused applications and browser tabs.",
            "Check Task Manager > Memory for the largest consumers.",
            "Restart the PC to clear leaked memory.",
        ],
    )


# Registry of deterministic rules (order = priority).
RULES: list[DiagnosticRule] = [
    DiagnosticRule("cpu_saturation", "CPU Saturation", _rule_cpu_saturation),
    DiagnosticRule("ram_pressure", "Memory Pressure", _rule_ram_pressure),
    DiagnosticRule("storage_exhaustion", "Storage Exhaustion", _rule_storage_exhaustion),
    DiagnosticRule("battery_degradation", "Battery Degradation", _rule_battery_degradation),
]


def evaluate_rules(
    report: dict[str, Any],
    profile: IssueProfile,
    message: str = "",
) -> list[TroubleshooterFinding]:
    """Run all rules against a scan report; return new findings (deduped by rule_id)."""
    hw = report.get("hardware") or {}
    sw = report.get("software") or {}
    out: list[TroubleshooterFinding] = []
    seen: set[str] = set()

    for rule in RULES:
        try:
            finding = rule.evaluate(hw, profile, message)
        except Exception:
            finding = None
        if finding and finding.id not in seen:
            seen.add(finding.id)
            out.append(finding)

    ev = _rule_event_4101(sw, profile, message)
    if ev and ev.id not in seen:
        out.append(ev)

    return out
