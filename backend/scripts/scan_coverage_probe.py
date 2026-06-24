#!/usr/bin/env python3
"""Regression probe: intent classification + scan-only answers for common questions."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.issue_parser import parse_issue
from app.services.machine_scan_findings import build_findings_from_scan
from app.services.question_intent import intent_label

QUESTIONS = [
    "is my laptop connected to any wifi",
    "is my laptop connected to any printer",
    "tell me the audio devices connected",
    "what CPU do I have",
    "how many printers are on my network",
    "what is my compliance score",
    "what is my machine health score",
    "my printer wont print",
    "list usb devices connected",
    "which drivers are failing",
    "what drivers are failing",
    "list all the drivers",
    "audio devices",
    "what processes are running",
    "which application is using more CPU",
    "which application is using more RAM",
    "which file is taking the most space in my laptop",
]

# Minimal synthetic report with audio/usb data
REPORT = {
    "hardware": {
        "cpu": {"processor_name": "Intel Core i7", "current_usage_pct": 12},
        "external_devices": {
            "audio": {
                "input_devices": [{"name": "Mic Array", "is_physical": True, "connected": True, "health": "Connected"}],
                "output_devices": [{"name": "Speakers", "is_physical": True, "connected": True, "health": "Connected"}],
            },
            "usb": {"devices": [{"name": "USB Keyboard", "type": "USB Keyboard", "health": "Connected"}]},
            "printers": {"printers": []},
        },
        "drivers": {
            "installed_count": 3,
            "installed_drivers": [
                {"name": "Realtek Audio", "class": "MEDIA", "version": "6.0.9600.1", "manufacturer": "Realtek"},
                {"name": "Intel Wi-Fi 6", "class": "NET", "version": "22.240.0.6", "manufacturer": "Intel"},
                {"name": "NVIDIA GeForce RTX", "class": "DISPLAY", "version": "551.23", "manufacturer": "NVIDIA"},
            ],
            "problem_devices": [
                {"name": "Realtek Audio", "problem": "Failed to start", "problem_code": 10, "class": "MEDIA"},
            ],
        },
    },
    "software": {
        "network": {"wifi": {"connected": True, "ssid": "Office"}, "ip_config": {"ip_address": "10.0.0.2"}},
        "compliance": {"score": 88, "verdicts": []},
        "running_processes": {
            "total_count": 120,
            "top_cpu": [
                {"name": "chrome.exe", "cpu_pct": 5, "memory_mb": 400},
                {"name": "python.exe", "cpu_pct": 3, "memory_mb": 200},
            ],
            "top_memory": [
                {"name": "chrome.exe", "cpu_pct": 5, "memory_mb": 1200},
                {"name": "Cursor.exe", "cpu_pct": 2, "memory_mb": 800},
            ],
        },
        "storage_deep": {
            "mode": "deep",
            "scanned_drive": "C:",
            "tree": {
                "top_files": [
                    {"path": "C:\\Users\\me\\Downloads\\installer.iso", "size_gb": 8.4},
                    {"path": "C:\\Users\\me\\Videos\\movie.mkv", "size_gb": 4.2},
                ],
                "top_folders": [
                    {"path": "C:\\Users\\me\\Downloads", "size_gb": 22.1},
                ],
            },
        },
        "dev_environment": {"installed_tools": ["git", "python"], "tools": {"git": {"version": "2.43"}, "python": {"version": "3.12"}}},
    },
    "health_report": {"overall_score": 82, "overall_status": "Healthy", "categories": {"security": {"score": 90}}},
}


def main() -> int:
    failed = 0
    for q in QUESTIONS:
        p = parse_issue(q)
        findings = build_findings_from_scan(REPORT, p, q)
        ok = bool(findings) and not any(
            "Could not determine" in (f.detected or "") for f in findings
        )
        if q == "my printer wont print":
            ok = any(not f.id.startswith("info_") for f in findings)
        elif "failing" in q and "driver" in q:
            ok = "Realtek" in (findings[0].detected or "") or "no drivers are currently failing" in (findings[0].detected or "").lower()
        elif q == "list all the drivers":
            items = getattr(findings[0], "inventory_items", None) or []
            ok = (
                findings[0].id == "info_driver_list"
                and "installed driver" in (findings[0].detected or "").lower()
                and len(items) >= 1
                and any("Intel" in (it.name or "") for it in items)
                and len(findings) == 1
            )
        elif q == "which application is using more CPU":
            det = (findings[0].detected or "").lower()
            ok = (
                findings[0].id == "info_top_cpu_app"
                and ("chrome" in det or "using the most cpu" in det)
                and len(findings) == 1
            )
        elif q == "which application is using more RAM":
            det = (findings[0].detected or "").lower()
            ok = (
                findings[0].id == "info_top_ram_app"
                and ("chrome" in det or "using the most ram" in det)
                and "using the most cpu" not in det
                and len(findings) == 1
            )
        elif q == "which file is taking the most space in my laptop":
            det = findings[0].detected or ""
            ok = (
                findings[0].id == "info_largest_file"
                and "installer.iso" in det
                and "8.4" in det
                and len(findings) == 1
            )
        elif q == "audio devices":
            items = getattr(findings[0], "inventory_items", None) or []
            ok = (
                p.query_intent == "inventory"
                and findings[0].id == "info_audio_device_list"
                and len(items) >= 1
                and not any("No Audio Output" in (f.title or "") for f in findings)
                and len(findings) == 1
            )
        status = "PASS" if ok else "FAIL"
        if not ok:
            failed += 1
        detail = findings[0].detected[:70] if findings else "(none)"
        print(f"{status} [{intent_label(p.query_intent)}] {q!r} -> {findings[0].id if findings else '-'}: {detail}")
    print(f"\n{len(QUESTIONS) - failed}/{len(QUESTIONS)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
