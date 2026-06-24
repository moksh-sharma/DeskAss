"""Predictive analytics: deterministic risk scoring from the live scan facts.

Reads the SMART/disk-health, battery, storage, performance and crash sections
and derives forward-looking risk verdicts (SSD failure, battery failure, crash
probability, resource exhaustion, disk-full). All rule-based - no model.
"""
from __future__ import annotations

from app.services.scanners.base import safe_scan


def _risk(level: str, detail: str, evidence: list[str]) -> dict:
    return {"risk": level, "detail": detail, "evidence": evidence}


def _ssd_failure(hardware: dict) -> dict:
    disks = (hardware.get("disk_health") or {}).get("disks") or []
    worst = "low"
    detail = "No imminent disk-failure indicators."
    evidence: list[str] = []
    rank = {"low": 0, "medium": 1, "high": 2, "critical": 3}
    for d in disks:
        name = d.get("name") or "disk"
        smart = str(d.get("smart_health") or "").lower()
        wear = d.get("wear_pct")
        re_err = d.get("read_errors") or 0
        we_err = d.get("write_errors") or 0
        poh = d.get("power_on_hours")
        level = "low"
        if smart and smart not in ("healthy", "ok", "good", "", "none"):
            level = "critical"; evidence.append(f"{name}: SMART status '{d.get('smart_health')}'.")
        if isinstance(wear, (int, float)) and wear >= 80:
            level = "high" if level != "critical" else level
            evidence.append(f"{name}: {wear}% wear.")
        elif isinstance(wear, (int, float)) and wear >= 50:
            if rank[level] < rank["medium"]:
                level = "medium"
            evidence.append(f"{name}: {wear}% wear.")
        if (re_err + we_err) > 0:
            if rank[level] < rank["medium"]:
                level = "medium"
            evidence.append(f"{name}: {re_err} read / {we_err} write errors.")
        if isinstance(poh, (int, float)) and poh >= 40000:
            evidence.append(f"{name}: {int(poh)} power-on hours.")
        if rank[level] > rank[worst]:
            worst = level
    if worst != "low":
        detail = "Disk shows wear/error indicators - back up important data and monitor SMART."
    return _risk(worst, detail, evidence[:6])


def _battery_failure(hardware: dict) -> dict:
    bat = hardware.get("battery") or {}
    if not bat or bat.get("present") is False or bat.get("percentage") is None:
        return _risk("n/a", "No battery detected (desktop or no battery data).", [])
    health = bat.get("battery_health_pct")
    if not isinstance(health, (int, float)):
        return _risk("low", "Battery health data unavailable.", [])
    wear = round(100 - health, 1)
    if health < 50:
        return _risk("high", f"Battery health {health}% (≈{wear}% worn) - replacement likely soon.",
                     [f"Battery health {health}%"])
    if health < 70:
        return _risk("medium", f"Battery health {health}% (≈{wear}% worn) - degrading.",
                     [f"Battery health {health}%"])
    return _risk("low", f"Battery health {health}%.", [f"Battery health {health}%"])


def _crash_probability(software: dict) -> dict:
    crash = (software.get("crash_analysis") or {}).get("summary") or {}
    bsod = crash.get("bsod_count") or 0
    crashes = crash.get("crash_count") or 0
    evidence = []
    if bsod:
        evidence.append(f"{bsod} blue-screen event(s) in 7 days.")
    if crashes:
        evidence.append(f"{crashes} app crash(es) in 7 days.")
    if bsod >= 2 or crashes >= 8:
        return _risk("high", "Recent instability suggests further crashes are likely.", evidence)
    if bsod >= 1 or crashes >= 3:
        return _risk("medium", "Some instability observed; watch for recurrence.", evidence)
    return _risk("low", "No significant recent crash pattern.", evidence)


def _resource_exhaustion(hardware: dict, software: dict) -> dict:
    perf = hardware.get("performance") or {}
    mem = (perf.get("memory") or {}).get("current_pct")
    cpu = (perf.get("cpu") or {}).get("average_pct")
    evidence = []
    level = "low"
    if isinstance(mem, (int, float)) and mem >= 90:
        level = "high"; evidence.append(f"Memory at {mem}%.")
    elif isinstance(mem, (int, float)) and mem >= 80:
        level = "medium"; evidence.append(f"Memory at {mem}%.")
    if isinstance(cpu, (int, float)) and cpu >= 90:
        level = "high"; evidence.append(f"CPU averaging {cpu}%.")
    for d in (hardware.get("storage") or {}).get("logical_drives", []):
        if (d.get("usage_pct") or 0) >= 95:
            level = "high"; evidence.append(f"Drive {d.get('drive')} {d.get('usage_pct')}% full.")
    detail = {
        "low": "Resources have adequate headroom.",
        "medium": "Resources under pressure; close heavy apps.",
        "high": "Resource exhaustion likely - free RAM/disk or upgrade.",
    }[level]
    return _risk(level, detail, evidence[:5])


def _disk_full(hardware: dict, software: dict) -> dict:
    si = software.get("storage_intelligence") or {}
    deep = software.get("storage_deep") or {}
    growth = (deep.get("growth") or si.get("growth") or {})
    days = growth.get("days_until_full")
    evidence = []
    if isinstance(days, (int, float)):
        evidence.append(f"~{int(days)} days until full at current growth.")
        if days <= 14:
            return _risk("high", f"System drive may fill in ~{int(days)} days.", evidence)
        if days <= 60:
            return _risk("medium", f"System drive trending full (~{int(days)} days).", evidence)
    for d in (hardware.get("storage") or {}).get("logical_drives", []):
        if (d.get("usage_pct") or 0) >= 90:
            evidence.append(f"Drive {d.get('drive')} {d.get('usage_pct')}% full.")
            return _risk("medium", "A drive is nearly full.", evidence)
    return _risk("low", "No near-term disk-full risk detected.", evidence)


@safe_scan("predictive")
def build(sections: dict) -> dict:
    hardware = sections.get("_hardware_bucket") or {}
    software = sections.get("_software_bucket") or {}
    predictions = {
        "ssd_failure": _ssd_failure(hardware),
        "battery_failure": _battery_failure(hardware),
        "crash_probability": _crash_probability(software),
        "resource_exhaustion": _resource_exhaustion(hardware, software),
        "disk_full": _disk_full(hardware, software),
    }
    high = [k for k, v in predictions.items() if v.get("risk") in ("high", "critical")]
    return {
        "predictions": predictions,
        "high_risk_areas": high,
        "available": True,
    }
