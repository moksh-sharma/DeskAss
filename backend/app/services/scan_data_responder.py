"""Respond to user questions directly from scan report data.

Fallback layer after topic-specific regex builders in machine_scan_info.
Each responder reads the structured scan buckets (hardware / software) and
returns an informational finding, or None if data is absent.
"""
from __future__ import annotations

import re
from typing import Any, Callable

from app.models.schemas import IssueProfile, Severity, TroubleshooterFinding

Responder = Callable[[dict, dict, dict, str, IssueProfile], TroubleshooterFinding | None]


def _fact(fid: str, title: str, area: str, detected: str) -> TroubleshooterFinding:
    return TroubleshooterFinding(
        id=f"info_{fid}",
        title=title,
        area=area,
        severity=Severity.info,
        detected=detected,
        likely_cause=detected,
        resolution_steps=[],
        ask_ai_prompt=title,
    )


def _ext(hw: dict) -> dict:
    return (hw.get("external_devices") or {}) if isinstance(hw, dict) else {}


# --------------------------------------------------------------------------- #
#  Category responders
# --------------------------------------------------------------------------- #
def _respond_usb(hw, sw, meta, msg, profile) -> TroubleshooterFinding | None:
    usb = (_ext(hw).get("usb") or {})
    devs = usb.get("devices") or []
    if not devs:
        return _fact("usb_devices", "USB Devices", "USB",
                     "No USB peripherals are currently connected.")
    lines = []
    for d in devs[:15]:
        lines.append(f"{d.get('name')} ({d.get('type') or 'USB'}, {d.get('health') or d.get('status') or '?'})")
    return _fact("usb_devices", "USB Devices", "USB",
                 f"{len(devs)} USB device(s): " + "; ".join(lines) + ".")


def _respond_mouse(hw, sw, meta, msg, profile) -> TroubleshooterFinding | None:
    usb = (_ext(hw).get("usb") or {}).get("devices") or []
    mice = [d for d in usb if re.search(r"mouse|touchpad|trackpad|pointing", f"{d.get('name','')} {d.get('type','')}", re.I)]
    if mice:
        lines = [f"{d.get('name')} ({d.get('health') or 'connected'})" for d in mice]
        return _fact("mouse_devices", "Mouse / Pointing Devices", "Mouse",
                     "Connected: " + "; ".join(lines) + ".")
    return _fact("mouse_devices", "Mouse / Pointing Devices", "Mouse",
                 "No external USB mouse detected; the built-in touchpad may still be present.")


def _respond_keyboard(hw, sw, meta, msg, profile) -> TroubleshooterFinding | None:
    usb = (_ext(hw).get("usb") or {}).get("devices") or []
    kbs = [d for d in usb if re.search(r"keyboard", f"{d.get('name','')} {d.get('type','')}", re.I)]
    if kbs:
        lines = [f"{d.get('name')} ({d.get('health') or 'connected'})" for d in kbs]
        return _fact("keyboard_devices", "Keyboard Devices", "Keyboard",
                     "Connected: " + "; ".join(lines) + ".")
    return _fact("keyboard_devices", "Keyboard Devices", "Keyboard",
                 "No external USB keyboard detected; the built-in keyboard is still available.")


def _respond_docks(hw, sw, meta, msg, profile) -> TroubleshooterFinding | None:
    docks = (_ext(hw).get("docking_stations") or {}).get("docking_stations") or []
    tb = (_ext(hw).get("docking_stations") or {}).get("thunderbolt_devices") or []
    if not docks and not tb:
        return _fact("docks", "Docking / Thunderbolt", "Hardware",
                     "No docking stations or Thunderbolt peripherals detected.")
    parts = []
    for d in docks[:6]:
        parts.append(f"{d.get('name')} (dock, {d.get('health') or d.get('status') or '?'})")
    for d in tb[:6]:
        parts.append(f"{d.get('name')} (Thunderbolt)")
    return _fact("docks", "Docking / Thunderbolt", "Hardware",
                 f"{len(parts)} dock/TB device(s): " + "; ".join(parts) + ".")


def _respond_executive_health(hw, sw, meta, msg, profile) -> TroubleshooterFinding | None:
    hr = meta.get("health_report") or {}
    if not hr:
        return None
    score = hr.get("overall_score")
    status = hr.get("overall_status")
    cats = hr.get("categories") or {}
    parts = [f"Overall machine health: {score}/100 ({status})."]
    for key in ("performance", "security", "reliability", "storage", "network", "compliance"):
        c = cats.get(key) or {}
        if c.get("score") is not None:
            parts.append(f"{key.title()} {c['score']}/100.")
    actions = hr.get("recommended_actions") or []
    if actions:
        parts.append("Top action: " + actions[0])
    return _fact("executive_health", "Executive Health Scorecard", "Health", " ".join(parts))


def _respond_compliance(hw, sw, meta, msg, profile) -> TroubleshooterFinding | None:
    comp = sw.get("compliance") or {}
    if not comp:
        return None
    score = comp.get("score")
    verdicts = comp.get("verdicts") or []
    fails = [v for v in verdicts if v.get("status") in ("fail", "warning")]
    detail = f"Compliance score {score}/100. "
    if fails:
        detail += "Issues: " + "; ".join(
            f"{v.get('control')}: {v.get('status')}" for v in fails[:6]
        ) + "."
    else:
        detail += "All checked controls passed."
    return _fact("compliance", "Security Compliance", "Compliance", detail)


def _respond_predictive(hw, sw, meta, msg, profile) -> TroubleshooterFinding | None:
    pred = sw.get("predictive") or {}
    preds = pred.get("predictions") or {}
    if not preds:
        return None
    lines = []
    for k, v in preds.items():
        if isinstance(v, dict) and v.get("risk"):
            lines.append(f"{k.replace('_', ' ').title()}: {v.get('risk')} - {v.get('detail', '')}")
    if not lines:
        return None
    return _fact("predictive", "Predictive Risk", "Predictive", " | ".join(lines) + ".")


def _respond_processes(hw, sw, meta, msg, profile) -> TroubleshooterFinding | None:
    proc = sw.get("running_processes") or {}
    total = proc.get("total_count") or len(proc.get("processes") or [])
    top = proc.get("top_cpu") or proc.get("top_memory") or []
    if not total:
        return None
    lines = []
    for p in top[:8]:
        if isinstance(p, dict):
            lines.append(f"{p.get('name')} (CPU {p.get('cpu_pct')}%, RAM {p.get('memory_mb')} MB)")
    detail = f"{total} processes running."
    if lines:
        detail += " Top consumers: " + "; ".join(lines) + "."
    return _fact("processes", "Running Processes", "Processes", detail)


def _respond_services(hw, sw, meta, msg, profile) -> TroubleshooterFinding | None:
    svc = sw.get("services") or {}
    total = svc.get("total_count") or len(svc.get("services") or [])
    failed = svc.get("failed_critical") or svc.get("failed") or []
    if not total:
        return None
    detail = f"{total} Windows services inventoried."
    if failed:
        names = ", ".join(s.get("name", "?") for s in failed[:6])
        detail += f" Failed/stopped critical: {names}."
    else:
        detail += " No failed critical services."
    return _fact("services", "Windows Services", "Services", detail)


def _respond_drivers(hw, sw, meta, msg, profile) -> TroubleshooterFinding | None:
    from app.services.machine_scan_info import (
        _failing_drivers,
        _list_drivers,
        is_list_drivers_question,
    )
    if is_list_drivers_question(msg):
        return _list_drivers(hw, sw, msg)
    if re.search(
        r"\b(?:driver|drivers).{0,40}?(?:fail(?:ing|ed)|broken|error|problem)|"
        r"(?:fail(?:ing|ed)|broken|error|problem).{0,40}?(?:driver|drivers)|"
        r"\bwhich\s+drivers?\s+(?:are\s+)?(?:fail|broken|error|problem)|"
        r"\bwhat\s+drivers?\s+(?:are\s+)?(?:fail|broken|error|problem)",
        msg or "",
        re.I,
    ):
        return _failing_drivers(hw, sw, msg)
    drv = (hw.get("drivers") or {})
    total = drv.get("total_count") or len(drv.get("drivers") or [])
    problems = drv.get("problem_devices") or (hw.get("devices") or {}).get("problem_devices") or []
    if not total and not problems:
        return None
    detail = f"{total} drivers inventoried."
    if problems:
        detail += " Problem devices: " + "; ".join(
            f"{d.get('name')} (code {d.get('problem_code')})" for d in problems[:6]
        ) + "."
    return _fact("drivers", "Drivers", "Drivers", detail)


def _respond_reliability(hw, sw, meta, msg, profile) -> TroubleshooterFinding | None:
    crash = sw.get("crash_analysis") or {}
    logs = sw.get("event_logs") or {}
    bsod = len(crash.get("bsod_events") or [])
    app_c = len(crash.get("application_crashes") or [])
    crit = (logs.get("summary") or {}).get("critical_count") or 0
    if not (bsod or app_c or crit):
        return _fact("reliability", "System Reliability", "Reliability",
                     "No recent blue screens, app crashes, or critical event-log errors detected.")
    return _fact("reliability", "System Reliability", "Reliability",
                 f"Reliability signals: {bsod} BSOD(s), {app_c} app crash(es), "
                 f"{crit} critical event-log entries in the scan window.")


def _respond_dev(hw, sw, meta, msg, profile) -> TroubleshooterFinding | None:
    dev = sw.get("dev_environment") or {}
    tools = dev.get("installed_tools") or []
    if not tools:
        return _fact("dev_environment", "Developer Environment", "Development",
                     "No common developer tools (Git, Node, Python, Docker, VS Code, Cursor, WSL) detected.")
    details = []
    for name in tools:
        info = (dev.get("tools") or {}).get(name) or {}
        ver = info.get("version")
        details.append(f"{name}" + (f" ({ver})" if ver else ""))
    return _fact("dev_environment", "Developer Environment", "Development",
                 f"Installed: {', '.join(details)}.")


def _respond_ai(hw, sw, meta, msg, profile) -> TroubleshooterFinding | None:
    ai = sw.get("ai_environment") or {}
    stacks = ai.get("installed_stacks") or []
    if not stacks:
        return _fact("ai_environment", "AI / ML Environment", "AI",
                     "No local AI runtimes (Ollama, LM Studio, HuggingFace cache, CUDA) detected.")
    details = []
    for name in stacks:
        info = (ai.get("stacks") or {}).get(name) or {}
        det = info.get("detail")
        details.append(f"{name}" + (f" ({det})" if det else ""))
    return _fact("ai_environment", "AI / ML Environment", "AI",
                 f"Detected: {', '.join(details)}.")


def _respond_app_health(hw, sw, meta, msg, profile) -> TroubleshooterFinding | None:
    ah = sw.get("app_health") or {}
    if not ah:
        return None
    browsers = ah.get("browser_count") or 0
    issues = ah.get("issues") or []
    detail = f"{browsers} browser profile(s) scanned."
    ol = ah.get("outlook") or {}
    tm = ah.get("teams") or {}
    if ol.get("installed"):
        detail += f" Outlook: {'issues detected' if ol.get('issues') else 'OK'}."
    if tm.get("installed"):
        detail += f" Teams: {'issues detected' if tm.get('issues') else 'OK'}."
    if issues:
        detail += " Issues: " + "; ".join(issues[:4]) + "."
    return _fact("app_health", "Application Health", "Applications", detail)


def _respond_knowledge_graph(hw, sw, meta, msg, profile) -> TroubleshooterFinding | None:
    kg = sw.get("knowledge_graph") or {}
    if not kg:
        return None
    nodes = kg.get("node_count") or len(kg.get("nodes") or [])
    edges = kg.get("edge_count") or len(kg.get("edges") or [])
    correlations = kg.get("correlations") or []
    detail = f"Knowledge graph: {nodes} nodes, {edges} relationships."
    if correlations:
        detail += " " + correlations[0]
    return _fact("knowledge_graph", "Knowledge Graph", "Analysis", detail)


# Domain -> responder (used when topic regex did not match)
DOMAIN_RESPONDERS: dict[str, Responder] = {
    "usb": _respond_usb,
    "mouse": _respond_mouse,
    "keyboard": _respond_keyboard,
    "hardware": _respond_executive_health,
    "executive_health": _respond_executive_health,
    "compliance": _respond_compliance,
    "predictive": _respond_predictive,
    "process": _respond_processes,
    "service": _respond_services,
    "driver": _respond_drivers,
    "reliability": _respond_reliability,
    "crash": _respond_reliability,
    "dev_environment": _respond_dev,
    "ai_environment": _respond_ai,
    "application": _respond_app_health,
    "app_health": _respond_app_health,
}

# Message-keyword -> responder (broader than domain)
_KEYWORD_RESPONDERS: list[tuple[re.Pattern[str], Responder]] = [
    (re.compile(r"\b(usb|flash\s+drive|pendrive)\b", re.I), _respond_usb),
    (re.compile(r"\b(mouse|touchpad|trackpad|pointing)\b", re.I), _respond_mouse),
    (re.compile(r"\bkeyboard\b", re.I), _respond_keyboard),
    (re.compile(r"\b(dock|docking|thunderbolt)\b", re.I), _respond_docks),
    (re.compile(r"\b(health\s+score|machine\s+health|executive|scorecard)\b", re.I), _respond_executive_health),
    (re.compile(r"\bcompliance\b", re.I), _respond_compliance),
    (re.compile(r"\b(predict|failure\s+risk|likely\s+to\s+fail)\b", re.I), _respond_predictive),
    (re.compile(r"\b(process|processes|running\s+apps?)\b", re.I), _respond_processes),
    (re.compile(r"\bservices?\b", re.I), _respond_services),
    (re.compile(r"\bdrivers?\b", re.I), _respond_drivers),
    (re.compile(r"\b(crash|bsod|reliability|blue\s+screen)\b", re.I), _respond_reliability),
    (re.compile(r"\b(docker|node\.?js|python|git|wsl|developer|dev\s+environment)\b", re.I), _respond_dev),
    (re.compile(r"\b(ollama|lm\s+studio|cuda|ai\s+model|machine\s+learning)\b", re.I), _respond_ai),
    (re.compile(r"\b(browser|outlook|teams)\b", re.I), _respond_app_health),
    (re.compile(r"\bknowledge\s+graph\b", re.I), _respond_knowledge_graph),
]


def respond_from_scan(
    hw: dict,
    sw: dict,
    message: str,
    profile: IssueProfile,
    *,
    health_report: dict | None = None,
) -> TroubleshooterFinding | None:
    """Best-effort answer from scan buckets for the user's domain/question."""
    meta = {"health_report": health_report or {}}
    msg = message or ""

    domains: list[str] = []
    if profile.primary_domain:
        domains.append(profile.primary_domain)
    for d in profile.domains:
        if d not in domains:
            domains.append(d)

    for domain in domains:
        fn = DOMAIN_RESPONDERS.get(domain)
        if not fn:
            continue
        try:
            f = fn(hw, sw, meta, msg, profile)
            if f:
                return f
        except Exception:
            pass

    for pat, fn in _KEYWORD_RESPONDERS:
        if pat.search(msg):
            try:
                f = fn(hw, sw, meta, msg, profile)
                if f:
                    return f
            except Exception:
                pass
    return None
