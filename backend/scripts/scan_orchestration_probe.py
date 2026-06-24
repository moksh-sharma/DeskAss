#!/usr/bin/env python3
"""Probe intent -> scanner mapping for dynamic scan orchestration."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.issue_parser import enrich_with_inventory, parse_issue
from app.services.scan_orchestrator import build_scan_plan, is_full_system_scan_request

CASES = [
    (
        "Why is Chrome slow?",
        {"apps": ["chrome"]},
        {"processes", "app_health", "crash_analysis", "installed_software"},
        {"battery", "external_devices", "storage_intelligence", "network"},
    ),
    (
        "What printers are available on my network?",
        {},
        {"network", "external_devices"},
        {"battery", "security", "storage_intelligence", "performance"},
    ),
    (
        "Why is battery draining?",
        {},
        {"hardware", "performance", "processes"},
        {"external_devices", "network", "drivers"},
    ),
    (
        "Why is my PC slow?",
        {},
        {"performance", "processes", "startup_programs", "event_logs"},
        {"external_devices", "network"},
    ),
    (
        "list all the drivers",
        {},
        {"drivers"},
        {"storage_intelligence", "external_devices", "network", "security"},
    ),
    (
        "Full System Scan",
        {},
        None,
        set(),
    ),
]


def main() -> int:
    failed = 0
    for question, enrich, expected, forbidden in CASES:
        profile = parse_issue(question)
        if enrich.get("apps"):
            profile = enrich_with_inventory(
                profile, question, enrich["apps"], set(enrich["apps"]),
            )
        plan = build_scan_plan(question, profile)
        scanners = None if plan.full_scan else plan.scanners
        ok = True
        if expected is None:
            ok = plan.full_scan and is_full_system_scan_request(question)
        else:
            ok = scanners == expected or expected <= (scanners or set())
            for bad in forbidden:
                if bad in (scanners or set()):
                    ok = False
        status = "PASS" if ok else "FAIL"
        if not ok:
            failed += 1
        shown = "ALL" if plan.full_scan else ",".join(sorted(scanners or []))
        print(f"{status} {question!r}")
        print(f"       intents={plan.intents} depth={plan.depth} scanners={shown}")
        if not ok:
            print(f"       expected~={expected} forbidden={forbidden}")
    print(f"\n{len(CASES) - failed}/{len(CASES)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
