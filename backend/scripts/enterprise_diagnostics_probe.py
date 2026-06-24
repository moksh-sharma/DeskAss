#!/usr/bin/env python3
"""Enterprise diagnostics probe — intents, engines, determinism."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.issue_parser import parse_issue
from app.services.rules_engine import evaluate_rules, RULES
from app.services.scan_orchestrator import (
    ENTERPRISE_INTENTS,
    SCAN_DEPTH_BUDGET_SECONDS,
    build_scan_plan,
    classify_enterprise_intents,
)

SPEC_INTENTS = [
    "hardware_inventory",
    "hardware_health",
    "software_inventory",
    "software_analysis",
    "performance_analysis",
    "storage_analysis",
    "network_analysis",
    "network_discovery",
    "printer_discovery",
    "device_analysis",
    "driver_analysis",
    "security_analysis",
    "battery_analysis",
    "windows_health",
    "event_log_analysis",
    "crash_analysis",
    "change_analysis",
    "incident_reconstruction",
    "recommendation",
    "reporting",
    "full_system_scan",
]

QUESTIONS = [
    ("What CPU do I have?", "hardware_inventory"),
    ("Why is Chrome slow?", "application_troubleshooting"),
    ("What printers are available?", "printer_discovery"),
    ("Why is my laptop slow?", "performance_analysis"),
    ("Full System Scan", "full_system_scan"),
]


def main() -> int:
    failed = 0

    for intent in SPEC_INTENTS:
        if intent not in ENTERPRISE_INTENTS:
            print(f"FAIL missing intent label: {intent}")
            failed += 1

    for q, expected in QUESTIONS:
        p = parse_issue(q)
        intents = classify_enterprise_intents(q, p)
        plan = build_scan_plan(q, p)
        ok = expected in intents or (expected == "application_troubleshooting" and "application_troubleshooting" in intents)
        status = "PASS" if ok else "FAIL"
        if not ok:
            failed += 1
        scanners = "ALL" if plan.scanners is None else ",".join(sorted(plan.scanners))
        print(f"{status} {q!r} -> intents={intents} depth={plan.depth} scanners={scanners}")

    print(f"\nRules registered: {len(RULES)}")
    print(f"Scan depth budgets: {SCAN_DEPTH_BUDGET_SECONDS}")

    sample_report = {
        "hardware": {
            "performance": {"cpu_usage_percent": 96, "top_cpu": [{"name": "chrome.exe", "cpu_pct": 65}]},
            "storage": {"logical_drives": [{"drive": "C:", "usage_percent": 97}]},
        },
        "software": {},
    }
    p = parse_issue("why is my pc slow")
    hits = evaluate_rules(sample_report, p, "why is my pc slow")
    if not hits:
        print("FAIL rules_engine produced no findings for saturated CPU/disk")
        failed += 1
    else:
        print(f"PASS rules_engine -> {[h.title for h in hits]}")

    print(f"\n{len(SPEC_INTENTS) + len(QUESTIONS) + 1 - failed} checks passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
