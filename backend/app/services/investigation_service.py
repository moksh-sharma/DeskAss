"""Issue-scoped investigation engine (fully deterministic, no LLM).

Pipeline (no knowledge base, no AI model in the answer path):
    parse issue -> plan probe packs -> run live probes -> collect findings
    -> build an evidence-first DiagnosisResult.

Every answer is derived from live system facts and curated, rule-based findings.
"""
from __future__ import annotations

import asyncio
import platform
import re
from datetime import datetime
from typing import Optional

from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.schemas import (
    DiagnosisResult,
    Evidence,
    InvestigationReport,
    IssueProfile,
    ProbeResult,
    RecommendedFix,
    Severity,
    TroubleshooterFinding,
)
from app.services.issue_parser import enrich_with_inventory, parse_issue
from app.services.machine_scan_findings import build_investigation_from_scan
from app.services.machine_scan_service import MachineScanService
from app.services.correlation_engine import correlate
from app.services.scan_orchestrator import build_scan_plan, correlate_escalation
from app.services.question_intent import is_scan_only_intent
from app.services.system_inventory import SystemInventory
from app.services.visual_guide_service import VisualGuideService

logger = get_logger(__name__)

_RANK = {Severity.healthy: 0, Severity.info: 1, Severity.warning: 2, Severity.critical: 3}

_PLACEHOLDER_STEP_RE = re.compile(
    r"^\s*(this is informational|no action needed)\b",
    re.I,
)


def _actionable_resolution_steps(steps: list[str]) -> list[str]:
    """Drop placeholder lines that exist only to mark informational answers."""
    return [s for s in steps if s.strip() and not _PLACEHOLDER_STEP_RE.match(s)]


def _detail_lines_from_texts(*chunks: str | None) -> list[str]:
    """Split prose into unique sentences for line-by-line UI display."""
    seen: set[str] = set()
    lines: list[str] = []
    for chunk in chunks:
        text = (chunk or "").strip()
        if not text:
            continue
        for part in re.split(r"(?<=[.!?])\s+", text):
            p = part.strip()
            if not p:
                continue
            if p[-1] not in ".!?":
                p = f"{p}."
            key = p.lower()
            if key in seen:
                continue
            seen.add(key)
            lines.append(p)
    return lines


def _with_detail_lines(d: DiagnosisResult) -> DiagnosisResult:
    """Populate ``detail_lines`` and avoid repeating root_cause inside summary."""
    if d.detail_lines:
        return d
    summary = (d.issue_summary or "").strip()
    root = (d.root_cause or "").strip()
    extra = root if root and root.lower() not in summary.lower() else None
    lines = _detail_lines_from_texts(summary, extra)
    if not lines and summary:
        lines = [summary]
    issue_summary = lines[0] if len(lines) == 1 else summary
    return d.model_copy(update={"detail_lines": lines, "issue_summary": issue_summary})


_RANK_TO_SEV = {0: Severity.healthy, 1: Severity.info, 2: Severity.warning, 3: Severity.critical}


# --------------------------------------------------------------------------- #
#  Deterministic forensic / holistic analysis helpers
# --------------------------------------------------------------------------- #
def _num(value) -> Optional[float]:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _collect_signals(ev: dict) -> list[dict]:
    """Extract notable problems from the broad evidence pack, ranked worst-first.

    Each signal is ``{"label", "detail", "rank"}`` where rank 3 = critical,
    2 = warning. Every detail string cites concrete facts from the evidence.
    """
    sig: list[dict] = []
    ev = ev or {}

    res = ev.get("resource_usage") or {}
    cpu = _num(res.get("cpu_pct"))
    if cpu is not None and cpu >= 85:
        top = (res.get("top_cpu") or [{}])[0]
        who = top.get("app")
        sig.append({
            "label": "High CPU load",
            "detail": f"CPU is at {cpu:.0f}%"
                      + (f", led by {who} ({_num(top.get('cpu_pct')) or 0:.0f}%)" if who else "")
                      + ".",
            "rank": 3 if cpu >= 95 else 2,
        })
    ram = _num(res.get("ram_used_pct"))
    if ram is not None and ram >= 85:
        top = (res.get("top_memory") or [{}])[0]
        who = top.get("app")
        sig.append({
            "label": "High memory use",
            "detail": f"RAM is {ram:.0f}% used"
                      + (f", with {who} using the most ({_num(top.get('memory_mb')) or 0:.0f} MB)" if who else "")
                      + ".",
            "rank": 3 if ram >= 95 else 2,
        })
    page = _num(res.get("pagefile_used_pct"))
    if page is not None and page >= 80:
        sig.append({
            "label": "Pagefile pressure",
            "detail": f"The pagefile is {page:.0f}% used, a sign of memory exhaustion.",
            "rank": 2,
        })
    for p in (res.get("suspicious_processes") or [])[:3]:
        nm = p.get("name")
        if nm:
            sig.append({
                "label": f"Suspicious process {nm}",
                "detail": f"Process {nm} was flagged ({p.get('reason') or 'unusual'}).",
                "rank": 3,
            })

    for d in (ev.get("storage") or {}).get("drives") or []:
        used = _num(d.get("used_pct"))
        if used is not None and used >= 85:
            sig.append({
                "label": f"{d.get('drive')} almost full",
                "detail": f"Drive {d.get('drive')} is {used:.0f}% full "
                          f"({_num(d.get('free_gb')) or 0:.0f} GB free).",
                "rank": 3 if used >= 95 else 2,
            })

    os_ = ev.get("operating_system") or {}
    if os_.get("pending_reboot"):
        sig.append({
            "label": "Pending reboot",
            "detail": "A reboot is pending; some fixes and updates only take effect after restart.",
            "rank": 2,
        })
    upd = _num(os_.get("updates_pending"))
    if upd is not None and upd >= 1:
        sig.append({
            "label": "Windows updates pending",
            "detail": f"{int(upd)} Windows update(s) are pending.",
            "rank": 2,
        })

    sec = ev.get("security") or {}
    if sec.get("defender_realtime") is False:
        sig.append({
            "label": "Real-time protection off",
            "detail": "Microsoft Defender real-time protection is turned off.",
            "rank": 3,
        })
    if sec.get("firewall_all_enabled") is False:
        sig.append({
            "label": "Firewall partially off",
            "detail": "One or more Windows Firewall profiles are disabled.",
            "rank": 2,
        })
    age = _num(sec.get("signature_age_days"))
    if age is not None and age >= 7:
        sig.append({
            "label": "Stale antivirus signatures",
            "detail": f"Antivirus definitions are {age:.0f} days old.",
            "rank": 2,
        })

    crash = ev.get("crashes") or {}
    bsod = crash.get("bsod_events") or []
    if bsod:
        sig.append({
            "label": "Blue-screen crashes",
            "detail": f"{len(bsod)} blue-screen (BSOD) event(s) were recorded.",
            "rank": 3,
        })
    app_crashes = crash.get("application_crashes") or []
    if len(app_crashes) >= 3:
        sig.append({
            "label": "Frequent app crashes",
            "detail": f"{len(app_crashes)} application crash event(s) were recorded.",
            "rank": 2,
        })

    svc = ev.get("services") or {}
    failed = svc.get("failed_critical") or []
    if failed:
        sig.append({
            "label": "Failed critical services",
            "detail": f"Critical service(s) not running: {', '.join(str(x) for x in failed[:4])}.",
            "rank": 3,
        })

    dd = ev.get("devices_drivers") or {}
    probs = dd.get("problem_devices") or []
    if probs:
        names = ", ".join(p.get("name") for p in probs[:3] if p.get("name"))
        sig.append({
            "label": "Device problems",
            "detail": f"{len(probs)} device(s) report a driver/hardware problem"
                      + (f": {names}" if names else "") + ".",
            "rank": 2,
        })
    for disk in dd.get("disk_smart") or []:
        health = str(disk.get("smart_health") or "").lower()
        if health and health not in ("ok", "healthy", "good"):
            sig.append({
                "label": "Disk SMART warning",
                "detail": f"Disk {disk.get('name')} SMART health is '{disk.get('smart_health')}'.",
                "rank": 3,
            })

    start = ev.get("startup") or {}
    hi = _num(start.get("high_impact_count"))
    if hi is not None and hi >= 5:
        sig.append({
            "label": "Heavy startup load",
            "detail": f"{int(hi)} high-impact startup programs slow down boot.",
            "rank": 2,
        })

    # Predictive risk (SSD/battery/crash/resource/disk-full) from the synthesis layer.
    pred = (ev.get("predictive") or {}).get("predictions") or {}
    _risk_label = {
        "ssd_failure": "SSD failure risk", "battery_failure": "Battery failure risk",
        "crash_probability": "Crash risk", "resource_exhaustion": "Resource exhaustion risk",
        "disk_full": "Disk-full risk",
    }
    for key, p in pred.items():
        risk = str((p or {}).get("risk") or "").lower()
        if risk in ("high", "elevated", "critical", "medium"):
            sig.append({
                "label": _risk_label.get(key, key),
                "detail": f"{_risk_label.get(key, key)}: {risk.upper()} - {(p or {}).get('detail') or ''}".strip(),
                "rank": 3 if risk in ("high", "critical") else 2,
            })

    # Compliance gaps (security posture) from the compliance evaluator.
    comp = ev.get("compliance") or {}
    for c in (comp.get("failed_controls") or [])[:4]:
        sev = str(c.get("severity") or "").lower()
        sig.append({
            "label": f"Compliance gap: {c.get('name')}",
            "detail": f"{c.get('name')} - {c.get('detail')}",
            "rank": 3 if sev in ("high", "critical") else 2,
        })

    sig.sort(key=lambda s: s["rank"], reverse=True)
    return sig


def _prioritised_actions(ev: dict, signals: list[dict]) -> list[str]:
    """Build a prioritised, actionable list from health actions + signal mapping."""
    actions: list[str] = []
    rec = ((ev or {}).get("health") or {}).get("recommended_actions") or []
    for a in rec:
        a = str(a).strip()
        if a and a not in actions:
            actions.append(a)
    mapping = {
        "High CPU load": "Open Task Manager > Processes and close or restart the top CPU app.",
        "High memory use": "Close memory-heavy apps and browser tabs, then restart the top memory app.",
        "Pagefile pressure": "Close apps to free RAM, or increase the pagefile size.",
        "Pending reboot": "Restart Windows to apply pending updates and changes.",
        "Windows updates pending": "Install pending updates via Settings > Windows Update.",
        "Real-time protection off": "Turn on Microsoft Defender real-time protection in Windows Security.",
        "Firewall partially off": "Re-enable all firewall profiles in Windows Security > Firewall.",
        "Stale antivirus signatures": "Update antivirus definitions in Windows Security.",
        "Blue-screen crashes": "Update drivers and run 'sfc /scannow'; check minidumps for the failing driver.",
        "Frequent app crashes": "Update or reinstall the crashing app and update its drivers.",
        "Failed critical services": "Start the stopped services (services.msc) and set them to Automatic.",
        "Device problems": "Update or reinstall the affected device drivers in Device Manager.",
        "Disk SMART warning": "Back up your data now - the disk reports a SMART health warning.",
        "Heavy startup load": "Disable unneeded startup apps in Task Manager > Startup.",
    }
    for s in signals:
        for key, act in mapping.items():
            if s["label"].startswith(key) and act not in actions:
                actions.append(act)
    if any("almost full" in s["label"] for s in signals):
        act = "Free disk space: empty the Recycle Bin, clear temp files and run Disk Cleanup."
        if act not in actions:
            actions.append(act)
    return actions


def _mode_intro(mode: str) -> str:
    return {
        "forensic": "Across the full scan, the most significant finding is:",
        "predictive": "Based on current health and trends, the main risk is:",
        "reasoning": "Weighing all the evidence, the single biggest issue is:",
        "executive": "In summary, the main point is:",
    }.get(mode, "The most significant finding is:")


def _mode_summary(mode: str, lead: Optional[dict], signals: list[dict], ev: dict) -> str:
    health = (ev or {}).get("health") or {}
    score = health.get("score")
    status = health.get("status")
    head = ""
    if score is not None:
        head = f"Overall health {score}/100"
        if status:
            head += f" ({status})"
        head += ". "
    if not lead:
        return (head + "No significant problems detected.").strip()
    n = len(signals)
    label = lead["label"].lower()
    if mode == "predictive":
        return (head + f"Most likely to cause trouble next: {label}.").strip()
    if mode == "reasoning":
        extra = f" (plus {n - 1} more)" if n > 1 else ""
        return (head + f"Biggest issue: {label}{extra}.").strip()
    if mode == "executive":
        return (head + f"{n} issue(s) need attention; top priority is {label}.").strip()
    extra = f", with {n - 1} other item(s) noted" if n > 1 else ""
    return (head + f"Top finding: {label}{extra}.").strip()


def _evidence_recap(ev: dict) -> str:
    ev = ev or {}
    res = ev.get("resource_usage") or {}
    bits: list[str] = []
    cpu = _num(res.get("cpu_pct"))
    ram = _num(res.get("ram_used_pct"))
    if cpu is not None:
        bits.append(f"CPU {cpu:.0f}%")
    if ram is not None:
        bits.append(f"RAM {ram:.0f}%")
    drives = (ev.get("storage") or {}).get("drives") or []
    if drives:
        d = drives[0]
        used = _num(d.get("used_pct"))
        if used is not None:
            bits.append(f"{d.get('drive')} {used:.0f}% full")
    up = (ev.get("operating_system") or {}).get("uptime")
    if up:
        bits.append(f"uptime {up}")
    if not bits:
        return ""
    return "Current state: " + ", ".join(bits) + "."


def _healthy_reasons(ev: dict) -> list[str]:
    out: list[str] = []
    ev = ev or {}
    res = ev.get("resource_usage") or {}
    cpu = _num(res.get("cpu_pct"))
    ram = _num(res.get("ram_used_pct"))
    if cpu is not None:
        out.append(f"CPU at {cpu:.0f}%.")
    if ram is not None:
        out.append(f"RAM at {ram:.0f}%.")
    if (ev.get("security") or {}).get("protection_active"):
        out.append("Security protection is active.")
    return out or ["All scanned checks are within healthy ranges."]


def _prevention_tips(mode: str, signals: list[dict]) -> list[str]:
    tips = [
        "Keep Windows and device drivers up to date.",
        "Restart regularly and keep at least 15% of each drive free.",
    ]
    labels = {s["label"] for s in signals}
    if any(("protection" in l) or ("Firewall" in l) or ("signature" in l) for l in labels):
        tips.append("Keep Microsoft Defender and the firewall on with current definitions.")
    return tips[:3]


# A pure resource/usage question ("what's my CPU/RAM usage", "which app uses the
# most RAM") - answerable instantly from telemetry/a fast read, no heavy scan.
_RESOURCE_QUERY_RE = re.compile(
    r"\b(cpu|ram|memory|usage|resource|resources|disk\s+usage|gpu|"
    r"which\s+(?:app|application|process|program)|what\s+(?:app|application|process|program)|"
    r"using\s+the\s+most|most\s+(?:cpu|ram|memory)|task\s+manager|"
    r"how\s+much\s+(?:cpu|ram|memory))\b",
    re.I,
)
# Slowness/diagnosis phrasing benefits from event logs + incident replay, so it
# should NOT take the lightweight resource fast path.
_SLOWNESS_RE = re.compile(
    r"\b(slow|sluggish|lag|laggy|freeze|freezing|froze|frozen|hang|hanging|"
    r"not\s+responding|unresponsive|stutter|crash|bsod|overheat)\b",
    re.I,
)


def _is_resource_query(message: str, profile: IssueProfile) -> bool:
    """True for a pure CPU/RAM/disk usage question (no slowness diagnosis)."""
    if profile.analysis_mode:
        return False
    if set(profile.domains) - {"performance"}:
        return False
    if "performance" not in profile.domains:
        return False
    text = message or ""
    if _SLOWNESS_RE.search(text):
        return False
    return bool(_RESOURCE_QUERY_RE.search(text))


class InvestigationService:
    """Runs live, issue-scoped diagnostics and turns them into a result."""

    def __init__(
        self,
        inventory: Optional[SystemInventory] = None,
        machine_scan: Optional[MachineScanService] = None,
        visual_guides: Optional[VisualGuideService] = None,
        telemetry: Optional[object] = None,
    ) -> None:
        self._inventory = inventory or SystemInventory()
        self._machine_scan = machine_scan
        self._visual_guides = visual_guides
        self._telemetry = telemetry

    # ------------------------------------------------------------------ #
    #  Public API
    # ------------------------------------------------------------------ #
    async def investigate(self, message: str, ocr_text: str | None = None) -> InvestigationReport:
        profile = parse_issue(message, ocr_text)
        settings = get_settings()

        # Pure resource/usage questions take the fast path and don't need the
        # inventory (no app/process name matching), so skip that ~1s refresh.
        fast_resource = settings.investigation_fast_path and _is_resource_query(message, profile)

        snap = None
        if not fast_resource:
            # Enrich against the live machine inventory so ANY installed app /
            # running process the user names is recognised (not just a fixed list).
            snap = self._inventory.snapshot()
            profile = enrich_with_inventory(
                profile,
                f"{message or ''} {ocr_text or ''}",
                [a.name for a in snap.installed_apps],
                snap.process_names,
            )

        report = InvestigationReport(
            generated_at=datetime.utcnow(),
            issue=message,
            profile=profile,
        )
        if profile.needs_clarification:
            report.summary = profile.clarification_question or "Need more detail about the problem."
            report.overall_status = Severity.info
            return report

        # Fast path (query-first): pure resource/usage questions are answered from
        # cached telemetry or a quick psutil-only read - no heavy scoped scan, no
        # WMI / event-log queries. This is the "instant" path for the most common
        # questions ("which app uses the most RAM", "what's my CPU usage").
        if fast_resource:
            fast_report, source = await asyncio.to_thread(
                self._fast_resource_report, settings, message or ""
            )
            if fast_report is not None:
                logger.info("Fast resource path (%s) - skipping scoped scan", source)
                probes, findings, scan_facts = build_investigation_from_scan(
                    fast_report, profile, message or ""
                )
                findings.sort(key=lambda f: _RANK.get(f.severity, 0), reverse=True)
                report.probes = probes
                report.findings = findings
                report.scan_duration_seconds = 0.0
                report.scan_facts = scan_facts
                report.overall_status = self._overall_status(probes, findings)
                report.summary = self._summary(profile, findings, probes, fast_report)
                return report

        if not self._machine_scan:
            logger.warning("Machine scan service unavailable - investigation cannot run full scan.")
            report.summary = "Full system scan is unavailable on this host."
            report.overall_status = Severity.info
            return report

        # Intent-driven scan orchestration: run only the scanners required to
        # answer this question (see scan_orchestrator.py).
        scan_domains: list[str] | None = None
        scanner_keys: set[str] | None = None
        run_deep_storage: bool | None = None
        scan_plan = build_scan_plan(message or "", profile)
        profile.enterprise_intents = scan_plan.intents
        profile.entities = scan_plan.entities.to_dict()
        profile.scan_depth = scan_plan.depth

        if settings.investigation_scan_mode == "full":
            scan_domains = None
            scanner_keys = None
            run_deep_storage = settings.storage_deep_on_full_scan
        elif scan_plan.full_scan or profile.analysis_mode:
            scan_domains = None
            scanner_keys = None
            run_deep_storage = scan_plan.run_deep_storage
        else:
            scan_domains = scan_plan.issue_domains
            scanner_keys = scan_plan.scanners
            run_deep_storage = scan_plan.run_deep_storage

        logger.info(
            "Investigation scan mode=%s depth=%s intents=%s scanners=%s domains=%s drive=%s",
            settings.investigation_scan_mode,
            scan_plan.depth,
            scan_plan.intents,
            sorted(scanner_keys) if scanner_keys is not None else "ALL",
            scan_domains if scan_domains is not None else "ALL",
            profile.target_drive or "system",
        )
        # Reuse the inventory snapshot we already took for app/process matching,
        # and use shorter storage budgets for chat so storage answers come back
        # faster than the Full System Scan page (which keeps the longer budgets).
        scan_report = await self._machine_scan.scan(
            target_drive=profile.target_drive,
            domains=scan_domains,
            scanner_keys=scanner_keys,
            run_deep_storage=run_deep_storage,
            snapshot=snap,
            storage_tree_budget=settings.investigation_storage_tree_budget_seconds,
            storage_duplicate_budget=settings.investigation_storage_duplicate_budget_seconds,
            scan_depth=scan_plan.depth,
        )

        correlation = correlate(scan_report, scan_plan, profile, message or "")
        escalated = correlate_escalation(scan_plan, scan_report, message or "")
        if correlation.escalation and correlation.escalation.scanners:
            escalated = correlation.escalation
        if escalated and escalated.scanners and scan_plan.scanners:
            added = escalated.scanners - scan_plan.scanners
            if added:
                logger.info("Correlation escalation -> extra scanners: %s", sorted(added))
                extra_report = await self._machine_scan.scan(
                    target_drive=profile.target_drive,
                    domains=escalated.issue_domains,
                    scanner_keys=added,
                    run_deep_storage=escalated.run_deep_storage,
                    snapshot=snap,
                    storage_tree_budget=settings.investigation_storage_tree_budget_seconds,
                    storage_duplicate_budget=settings.investigation_storage_duplicate_budget_seconds,
                    scan_depth=scan_plan.depth,
                )
                scan_report = self._machine_scan.merge_reports(scan_report, extra_report)
        probes, findings, scan_facts = build_investigation_from_scan(
            scan_report, profile, message or ""
        )
        scan_facts["correlation"] = correlation.to_dict()

        findings.sort(key=lambda f: _RANK.get(f.severity, 0), reverse=True)
        health = scan_report.get("health_report") or {}
        report.probes = probes
        report.findings = findings
        report.scan_health_score = int(health.get("overall_score") or 0)
        report.scan_duration_seconds = float(scan_report.get("scan_duration_seconds") or 0)
        report.scan_facts = scan_facts
        report.overall_status = self._overall_status(probes, findings)
        report.summary = self._summary(profile, findings, probes, scan_report)
        return report

    def to_diagnosis(self, report: InvestigationReport) -> DiagnosisResult:
        """Convert an investigation report into the DiagnosisResult the UI renders."""
        profile = report.profile

        if profile.needs_clarification:
            return _with_detail_lines(DiagnosisResult(
                issue_summary=report.summary,
                is_conversational=True,
                severity=Severity.info,
                confidence=100,
            ))

        evidence = self._evidence_from_probes(report.probes)

        # Informational inventory answers (e.g. "how many printers on my network?")
        # should surface scan facts directly - not a generic troubleshooting template.
        if report.findings and all(f.id.startswith("info_") for f in report.findings):
            top = report.findings[0]
            detected = top.detected or top.title
            inventory = list(top.inventory_items or [])
            detail_lines = _detail_lines_from_texts(
                *(f.detected for f in report.findings[:4] if f.detected)
            )
            if not detail_lines:
                detail_lines = [detected] if detected else []
            steps: list[str] = []
            for f in report.findings[:3]:
                for s in f.resolution_steps:
                    if s not in steps:
                        steps.append(s)
            return _with_detail_lines(DiagnosisResult(
                issue_summary=detail_lines[0] if detail_lines else detected,
                severity=Severity.healthy if top.severity == Severity.info else top.severity,
                confidence=90,
                confidence_reasons=detail_lines[:3] or [detected],
                root_cause=detail_lines[0] if detail_lines else detected,
                reasoning="\n".join(detail_lines),
                evidence=evidence,
                recommended_fixes=[],
                resolution_steps=_actionable_resolution_steps(steps)[:6],
                prevention_tips=[],
                inventory_items=inventory,
                detail_lines=detail_lines,
            ))

        if not report.findings:
            if is_scan_only_intent(profile.query_intent):
                return _with_detail_lines(DiagnosisResult(
                    issue_summary=(
                        report.summary
                        or "Could not determine an answer from the scan data for this question."
                    ),
                    severity=Severity.info,
                    confidence=60,
                    confidence_reasons=["Scan data did not contain enough detail for this question."],
                    root_cause=report.summary or "Insufficient scan data.",
                    reasoning=report.summary or "Insufficient scan data.",
                    evidence=evidence,
                    recommended_fixes=[],
                    resolution_steps=[],
                    prevention_tips=[],
                ))
            # Nothing wrong detected in the scanned area (troubleshooting path).
            scanned = ", ".join(p.title for p in report.probes if p.available) or "the relevant components"
            return _with_detail_lines(DiagnosisResult(
                issue_summary=report.summary,
                severity=Severity.healthy,
                confidence=70,
                confidence_reasons=[c.value and f"{c.label}: {c.value}" for c in
                                    self._notable_checks(report.probes)][:4] or ["Live checks found no faults."],
                root_cause=f"No specific fault was detected in {scanned}.",
                reasoning=(
                    "The live scan of the components related to your issue did not find a clear problem. "
                    "If the issue persists, it may be intermittent or caused by an external factor "
                    "(the device itself, a peripheral, or the network beyond this PC)."
                ),
                evidence=evidence,
                resolution_steps=self._generic_next_steps(profile),
            ))

        top = report.findings[0]
        fixes = [
            RecommendedFix(
                title=f.title,
                description=f.likely_cause or f.detected,
                safe_action=(f.resolution_steps[0] if f.resolution_steps else None),
                requires_confirmation=True,
            )
            for f in report.findings[:4]
        ]
        # Merge resolution steps from the top findings, de-duplicated, capped.
        steps: list[str] = []
        for f in report.findings[:3]:
            for s in f.resolution_steps:
                if s not in steps:
                    steps.append(s)
        steps = steps[:8]

        confidence = self._confidence(report.findings)
        reasons = [f.detected for f in report.findings[:4] if f.detected]

        correlations = (report.scan_facts or {}).get("correlation", {}).get("correlations") or []
        from app.services.response_generator import render_from_findings
        templated = render_from_findings(
            report.findings,
            profile,
            summary=report.summary,
            evidence=evidence,
            correlations=correlations,
        )
        if templated:
            return _with_detail_lines(templated)

        return _with_detail_lines(DiagnosisResult(
            issue_summary=report.summary,
            severity=report.overall_status,
            confidence=confidence,
            confidence_reasons=reasons or ["Based on live system checks."],
            root_cause=top.likely_cause or top.detected,
            reasoning=self._reasoning(report.findings),
            evidence=evidence,
            recommended_fixes=fixes,
            resolution_steps=steps,
            prevention_tips=[],
        ))

    async def diagnose(self, message: str, ocr_text: str | None = None) -> tuple[DiagnosisResult, InvestigationReport]:
        """Run the full investigation and build a deterministic diagnosis.

        Every answer is derived from live system facts + curated rule-based
        findings - there is no AI model in the answer path.
        """
        report = await self.investigate(message, ocr_text)
        result = self.to_diagnosis(report)

        # Holistic / forensic / predictive / executive questions get a broad,
        # cross-cutting answer assembled deterministically from the evidence pack.
        scanned = any(p.available for p in report.probes)
        if report.profile.analysis_mode and not report.profile.needs_clarification and scanned:
            result = self._forensic_diagnose(result, report)

        return result, report

    # ------------------------------------------------------------------ #
    #  Helpers
    # ------------------------------------------------------------------ #
    @staticmethod
    def _notable_checks(probes: list[ProbeResult]):
        out = []
        for p in probes:
            for c in p.checks:
                if c.status in (Severity.warning, Severity.critical):
                    out.append(c)
        return out

    def _evidence_from_probes(self, probes: list[ProbeResult]) -> list[Evidence]:
        evidence: list[Evidence] = []
        # Surface problem checks first, then a few key healthy facts for context.
        for p in probes:
            for c in p.checks:
                if c.status in (Severity.warning, Severity.critical):
                    evidence.append(Evidence(label=c.label, value=c.value, severity=c.status))
        if len(evidence) < 6:
            for p in probes:
                for c in p.checks:
                    if c.status in (Severity.healthy, Severity.info):
                        evidence.append(Evidence(label=c.label, value=c.value, severity=c.status))
                        if len(evidence) >= 8:
                            break
                if len(evidence) >= 8:
                    break
        return evidence[:10]

    @staticmethod
    def _overall_status(probes: list[ProbeResult], findings: list[TroubleshooterFinding]) -> Severity:
        actionable = [
            f for f in findings
            if f.severity != Severity.info and not f.id.startswith("no_fault_")
        ]
        if not actionable:
            if any(p.available for p in probes):
                return Severity.healthy
            return Severity.info
        worst = Severity.healthy
        for f in actionable:
            if _RANK[f.severity] > _RANK[worst]:
                worst = f.severity
        return worst

    @staticmethod
    def _confidence(findings: list[TroubleshooterFinding]) -> int:
        if not findings:
            return 60
        base = 60
        crit = sum(1 for f in findings if f.severity == Severity.critical)
        warn = sum(1 for f in findings if f.severity == Severity.warning)
        base += crit * 15 + warn * 8
        return max(40, min(96, base))

    @staticmethod
    def _summary(
        profile: IssueProfile,
        findings: list[TroubleshooterFinding],
        probes: list[ProbeResult],
        scan_report: dict | None = None,
    ) -> str:
        # Keep chat summaries focused on the issue/finding - scan metadata (health
        # score, duration) is shown in the scan details panel, not repeated here.
        if not findings:
            focus = profile.primary_domain or "your issue"
            return (
                f"No clear fault detected for {focus}. "
                "See the steps below to isolate the problem."
            )
        if len(findings) == 1:
            f = findings[0]
            if f.id.startswith("info_"):
                if f.inventory_items:
                    return f.detected or f.title
                if f.detected:
                    return f.detected
            return f"{f.title}."
        titles = "; ".join(f.title for f in findings[:3])
        if len(findings) > 3:
            return f"{titles}; and {len(findings) - 3} more."
        return f"{titles}."

    @staticmethod
    def _reasoning(findings: list[TroubleshooterFinding]) -> str:
        parts = []
        for f in findings[:3]:
            parts.append(f"{f.detected} {f.likely_cause}".strip())
        return " ".join(parts)

    @staticmethod
    def _generic_next_steps(profile: IssueProfile) -> list[str]:
        if "webcam" in profile.domains:
            return [
                "Check the physical privacy shutter/switch and any Fn key that disables the camera.",
                "Settings > Privacy & security > Camera: turn on camera access and allow your meeting/browser app.",
                "Close other apps that may hold the camera (Teams, Zoom, OBS) and test in the built-in Camera app.",
                "Device Manager > Cameras: update or reinstall the camera driver if video is still black.",
            ]
        if "audio" in profile.domains:
            return [
                "Settings > Privacy & security > Microphone: turn on access and allow your app.",
                "Settings > System > Sound > Input: select the correct mic and watch the input meter while speaking.",
                "Right-click speaker icon > Sound settings - ensure the mic is not muted.",
                "Device Manager > Audio inputs and outputs: update the microphone driver.",
                "Test in Windows Voice Recorder; close Teams/Zoom if they may be holding the mic.",
            ]
        if "mouse" in profile.domains:
            return [
                "Press Fn + the touchpad key, or double-tap the top-left corner of the touchpad.",
                "Settings > Bluetooth & devices > Mouse: check pointer speed and device selection.",
                "Device Manager > Mice and other pointing devices: update or reinstall the driver.",
                "Try another USB port or replace batteries in a wireless mouse.",
                "Restart the PC and test the pointer on the desktop.",
            ]
        if "keyboard" in profile.domains:
            return [
                "Settings > Accessibility > Keyboard: turn off Filter Keys and Sticky Keys.",
                "Settings > Time & language: confirm the correct keyboard layout.",
                "Device Manager > Keyboards: update or reinstall the driver.",
                "For wireless keyboards: replace batteries or re-pair via Bluetooth.",
            ]
        return [
            "Re-test the device/feature once more to confirm the symptom is still happening.",
            "If it's a peripheral, try it on another PC (or another device on this PC) to isolate the fault.",
            "Restart the PC and try again - this clears transient driver/service states.",
            "If the problem returns, note exactly when it happens and run this scan again.",
        ]

    # ------------------------------------------------------------------ #
    #  Fast resource path (query-first: telemetry cache or quick live read)
    # ------------------------------------------------------------------ #
    def _fast_resource_report(self, settings, message: str = "") -> tuple[Optional[dict], str]:
        """Synthetic scan report for resource questions, no heavy scan.

        Top-app CPU/RAM questions always take a fresh live process read.
        Other resource questions prefer cached telemetry when fresh enough.
        Returns ``(report, source)`` or ``(None, "")``.
        """
        from app.services.machine_scan_info import is_top_cpu_question, is_top_ram_question

        if is_top_cpu_question(message) or is_top_ram_question(message):
            try:
                return self._report_from_psutil(), "live process scan"
            except Exception as exc:
                logger.info("Live process read failed (%s); trying telemetry", exc)

        if self._telemetry is not None:
            try:
                snap = self._telemetry.latest_resource_snapshot(
                    max_age_seconds=settings.investigation_telemetry_max_age_seconds
                )
            except Exception:  # pragma: no cover - telemetry optional
                snap = None
            if snap and (snap.get("top_cpu") or snap.get("top_mem")):
                return self._report_from_snapshot(snap), f"telemetry {snap.get('age_seconds')}s"

        try:
            return self._report_from_psutil(), "live psutil"
        except Exception as exc:
            logger.info("Fast resource read failed (%s); falling back to scan", exc)
            return None, ""

    @staticmethod
    def _report_from_snapshot(snap: dict) -> dict:
        def _proc(p: dict) -> dict:
            mem = p.get("mem_mb")
            return {
                "name": p.get("name"),
                "cpu_pct": p.get("cpu_pct"),
                "memory_mb": mem if mem is not None else p.get("memory_mb"),
            }

        drives = []
        used_pct = snap.get("disk_used_pct")
        free_gb = snap.get("disk_free_gb")
        if used_pct is not None:
            total_gb = None
            if free_gb is not None and used_pct < 100:
                total_gb = round(free_gb / (1 - used_pct / 100), 1)
            drives.append({"drive": "C:", "usage_pct": used_pct,
                           "free_gb": free_gb, "total_gb": total_gb})
        return {
            "hardware": {
                "cpu": {"processor_name": platform.processor() or None,
                        "current_usage_pct": snap.get("cpu_pct")},
                "ram": {"total_gb": snap.get("mem_total_gb"), "used_gb": snap.get("mem_used_gb"),
                        "utilization_pct": snap.get("mem_used_pct"),
                        "virtual_memory": {"used_pct": snap.get("pagefile_pct")}},
                "storage": {"logical_drives": drives},
            },
            "software": {"running_processes": {
                "top_cpu": [_proc(p) for p in (snap.get("top_cpu") or [])],
                "top_memory": [_proc(p) for p in (snap.get("top_mem") or [])],
                "total_processes": snap.get("process_count"),
                "suspicious": [],
            }},
            "scan_scope": "fast",
            "scan_duration_seconds": 0,
        }

    @staticmethod
    def _report_from_psutil() -> dict:
        import psutil

        from app.services.scanners import processes as processes_scanner

        gb = 1024 ** 3
        vm = psutil.virtual_memory()
        cpu_pct = psutil.cpu_percent(interval=0.2)
        drives = []
        seen: set[str] = set()
        for part in psutil.disk_partitions(all=False):
            try:
                usage = psutil.disk_usage(part.mountpoint)
            except (PermissionError, OSError):
                continue
            key = (part.device or "").rstrip("\\")
            if key in seen:
                continue
            seen.add(key)
            drives.append({"drive": part.device, "usage_pct": usage.percent,
                           "free_gb": round(usage.free / gb, 1),
                           "total_gb": round(usage.total / gb, 1)})
        proc = processes_scanner.scan()
        return {
            "hardware": {
                "cpu": {"processor_name": platform.processor() or None,
                        "current_usage_pct": round(cpu_pct, 1)},
                "ram": {"total_gb": round(vm.total / gb, 1), "used_gb": round(vm.used / gb, 1),
                        "utilization_pct": vm.percent, "virtual_memory": {}},
                "storage": {"logical_drives": drives},
            },
            "software": {"running_processes": proc if isinstance(proc, dict) else {}},
            "scan_scope": "fast",
            "scan_duration_seconds": 0,
        }

    def _forensic_diagnose(
        self, result: DiagnosisResult, report: InvestigationReport
    ) -> DiagnosisResult:
        """Deterministic holistic analysis for forensic / predictive / reasoning /
        executive questions.

        Reads the broad evidence pack assembled by ``build_forensic_context`` and
        builds a grounded, cross-cutting answer (root cause, reasoning, prioritised
        actions) purely from the collected facts - no AI model involved.
        """
        profile = report.profile
        mode = profile.analysis_mode or "forensic"
        facts = report.scan_facts or {}
        ev = facts.get("forensic_evidence") or facts

        signals = _collect_signals(ev)
        actions = _prioritised_actions(ev, signals)

        if signals:
            lead = signals[0]
            others = [s["label"] for s in signals[1:4]]
            tail = f" Other notable items: {', '.join(others)}." if others else ""
            result.issue_summary = _mode_summary(mode, lead, signals, ev)
            result.root_cause = f"{lead['detail']}"
            result.reasoning = (
                f"{_mode_intro(mode)} {lead['detail']}{tail} "
                f"{_evidence_recap(ev)}"
            ).strip()
            result.confidence_reasons = [s["detail"] for s in signals[:5]]
            result.confidence = max(55, min(95, 60 + 8 * len(signals)))
            sev = max((s["rank"] for s in signals), default=1)
            result.severity = _RANK_TO_SEV.get(sev, result.severity)
        else:
            result.issue_summary = _mode_summary(mode, None, [], ev)
            result.root_cause = (
                "No significant problems were detected across hardware, software, "
                "security, storage or stability checks."
            )
            result.reasoning = _evidence_recap(ev) or (
                "All scanned subsystems are within healthy ranges."
            )
            result.confidence_reasons = _healthy_reasons(ev)
            result.confidence = 80

        if actions:
            result.resolution_steps = actions[:6]
        result.prevention_tips = _prevention_tips(mode, signals)

        # Cross-entity correlations from the knowledge graph (process<->service<->
        # driver<->device<->error links) make "correlate X with Y" answers concrete.
        correlations = (ev.get("correlations") or [])[:5]
        if correlations:
            corr_text = " Correlations: " + " ".join(
                f"({i + 1}) {c}" for i, c in enumerate(correlations)
            )
            result.reasoning = (result.reasoning or "") + corr_text
            result.confidence_reasons = (result.confidence_reasons or []) + correlations[:3]

        # Executive scorecard: surface the per-dimension scores for executive/risk
        # questions so leaders get the numbers, not just a single finding.
        scores = ev.get("category_scores") or {}
        if mode == "executive" and scores:
            parts = []
            for dim in ("hardware", "software", "performance", "security",
                        "reliability", "storage", "network", "application", "compliance"):
                s = scores.get(dim) or {}
                if isinstance(s, dict) and s.get("score") is not None:
                    parts.append(f"{dim} {s['score']}/100")
            if parts:
                result.reasoning = (result.reasoning or "") + " Scorecard: " + ", ".join(parts) + "."

        result.model = ""
        logger.info("Deterministic forensic analysis (mode=%s, signals=%d, steps=%d).",
                    mode, len(signals), len(result.resolution_steps))
        return result
