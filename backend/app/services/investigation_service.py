"""Issue-scoped investigation engine.

Pipeline (no knowledge base in the answer path):
    parse issue -> plan probe packs -> run live probes -> collect findings
    -> build an evidence-first DiagnosisResult.

Optionally, an LLM can rewrite the deterministic report into friendlier prose,
but it is constrained to the collected facts only (cite-only mode).
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Optional

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
from app.services.ollama_service import OllamaService
from app.services.system_inventory import SystemInventory

logger = get_logger(__name__)

_RANK = {Severity.healthy: 0, Severity.info: 1, Severity.warning: 2, Severity.critical: 3}


def _clean_str(value: object) -> str:
    """Normalise an LLM string field, rejecting empty/null-ish output."""
    if not isinstance(value, str):
        return ""
    s = value.strip()
    return "" if s.lower() in ("", "none", "null", "n/a", "unknown") else s


def _clean_list(value: object) -> list[str]:
    """Normalise an LLM array-of-strings field, dropping empties."""
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        s = item.strip() if isinstance(item, str) else str(item).strip()
        if s and s.lower() not in ("none", "null", "n/a"):
            out.append(s)
    return out

_DIAGNOSIS_SYSTEM = (
    "You are a senior Windows IT support engineer. You are given (1) the user's reported problem "
    "and (2) FACTS collected live from THIS PC, plus deterministic FINDINGS about that specific issue.\n"
    "STRICT RULES:\n"
    "- Diagnose ONLY the user's stated problem (e.g. microphone, webcam, Wi-Fi). "
    "Do NOT cite or blame unrelated system issues (CPU usage, firewall, BitLocker, unrelated "
    "stopped services such as NLA/DNS, disk space, etc.) unless they are explicitly in the "
    "findings for this issue.\n"
    "- Use ONLY the facts/findings provided. NEVER invent processes, services, event IDs, drivers, "
    "devices, versions, or numbers that are not present in the evidence.\n"
    "- If no fault was found in the relevant subsystem, say so honestly and give troubleshooting "
    "steps specific to the user's symptom (permissions, default device, mute, app settings).\n"
    "- Resolution steps must be concrete and ordered, with exact Windows UI paths or commands.\n"
    "- Do NOT change the severity you are given; it is computed from hard evidence.\n"
    "- Return ONLY the requested JSON object, nothing else."
)


class InvestigationService:
    """Runs live, issue-scoped diagnostics and turns them into a result."""

    def __init__(
        self,
        ollama: Optional[OllamaService] = None,
        use_llm: bool = False,
        inventory: Optional[SystemInventory] = None,
        machine_scan: Optional[MachineScanService] = None,
    ) -> None:
        self._ollama = ollama
        self._use_llm = use_llm
        self._inventory = inventory or SystemInventory()
        self._machine_scan = machine_scan

    # ------------------------------------------------------------------ #
    #  Public API
    # ------------------------------------------------------------------ #
    async def investigate(self, message: str, ocr_text: str | None = None) -> InvestigationReport:
        profile = parse_issue(message, ocr_text)

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

        if not self._machine_scan:
            logger.warning("Machine scan service unavailable - investigation cannot run full scan.")
            report.summary = "Full system scan is unavailable on this host."
            report.overall_status = Severity.info
            return report

        logger.info(
            "Investigation running comprehensive machine scan (all hardware + software) for domains=%s",
            profile.domains,
        )
        scan_report = await self._machine_scan.scan()
        probes, findings, scan_facts = build_investigation_from_scan(
            scan_report, profile, message or ""
        )

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
            return DiagnosisResult(
                issue_summary=report.summary,
                is_conversational=True,
                severity=Severity.info,
                confidence=100,
            )

        evidence = self._evidence_from_probes(report.probes)

        if not report.findings:
            # Nothing wrong detected in the scanned area.
            scanned = ", ".join(p.title for p in report.probes if p.available) or "the relevant components"
            return DiagnosisResult(
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
            )

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

        return DiagnosisResult(
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
        )

    async def diagnose(self, message: str, ocr_text: str | None = None) -> tuple[DiagnosisResult, InvestigationReport]:
        """Run the full investigation, then enrich it with grounded LLM generation.

        The deterministic result is always computed first and used as a guaranteed
        fallback, so a slow/offline LLM never breaks diagnosis.
        """
        report = await self.investigate(message, ocr_text)
        result = self.to_diagnosis(report)

        # Only enrich real investigations (skip clarification prompts) and only
        # when a probe actually ran, so we never hallucinate over nothing.
        scanned = any(p.available for p in report.probes)
        if self._use_llm and self._ollama and not report.profile.needs_clarification and scanned:
            try:
                if await self._ollama.health():
                    result = await self._llm_diagnose(result, report)
                else:
                    logger.info("Ollama offline - using deterministic diagnosis.")
            except Exception as exc:  # pragma: no cover - never let the LLM break diagnosis
                logger.warning("LLM diagnosis failed, using deterministic result: %s", exc)
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
        health = (scan_report or {}).get("health_report") or {}
        score = health.get("overall_score")
        status = health.get("overall_status")
        duration = (scan_report or {}).get("scan_duration_seconds")
        scan_blurb = "all hardware and software on this PC"
        if score is not None and status:
            scan_blurb += f" (health {score}/100 {status}"
            if duration:
                scan_blurb += f", {duration}s scan"
            scan_blurb += ")"
        if not findings:
            focus = profile.primary_domain or "your issue"
            return (
                f"I ran a full scan of {scan_blurb} and found no clear fault for {focus}. "
                "See the steps below to isolate the problem."
            )
        if len(findings) == 1:
            return f"Full scan of {scan_blurb} found: {findings[0].title}."
        titles = "; ".join(f.title for f in findings[:3])
        return f"Full scan of {scan_blurb} found {len(findings)} issue(s): {titles}."

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
                "Right-click speaker icon > Sound settings — ensure the mic is not muted.",
                "Device Manager > Audio inputs and outputs: update the microphone driver.",
                "Test in Windows Voice Recorder; close Teams/Zoom if they may be holding the mic.",
            ]
        return [
            "Re-test the device/feature once more to confirm the symptom is still happening.",
            "If it's a peripheral, try it on another PC (or another device on this PC) to isolate the fault.",
            "Restart the PC and try again - this clears transient driver/service states.",
            "If the problem returns, note exactly when it happens and run this scan again.",
        ]

    async def _llm_diagnose(self, result: DiagnosisResult, report: InvestigationReport) -> DiagnosisResult:
        """Generate a grounded, detailed diagnosis from the live evidence.

        The LLM enriches the prose (summary, root cause, reasoning), the
        confidence narrative, and the step-by-step / prevention guidance, but is
        constrained to the collected facts. Deterministic severity, evidence and
        recommended fixes remain the source of truth.
        """
        profile = report.profile
        payload: dict = {
            "user_problem": report.issue,
            "parsed": {
                "domains": profile.domains,
                "apps": profile.apps,
                "symptoms": profile.symptoms,
            },
            "severity": report.overall_status.value,
            "facts": [
                {
                    "probe": p.title,
                    "checks": [
                        {"label": c.label, "value": c.value, "status": c.status.value,
                         **({"detail": c.detail} if c.detail else {})}
                        for c in p.checks
                    ],
                }
                for p in report.probes if p.available
            ],
            "findings": [
                {
                    "title": f.title,
                    "severity": f.severity.value,
                    "detected": f.detected,
                    "likely_cause": f.likely_cause,
                    "steps": f.resolution_steps,
                }
                for f in report.findings
            ],
        }
        if report.scan_facts:
            payload["issue_relevant_scan"] = report.scan_facts
        has_findings = bool(report.findings)
        actionable_findings = [
            f for f in report.findings
            if f.severity != Severity.info and not f.id.startswith("no_fault_")
        ]
        guidance = (
            f"The user reported: \"{report.issue}\"\n"
            "Diagnose ONLY this specific problem. Do not mention unrelated system issues.\n\n"
            + json.dumps(payload, indent=2)
            + "\n\nReturn ONLY a JSON object with these keys:\n"
            '  "issue_summary": one precise sentence restating the user\'s specific problem,\n'
            '  "root_cause": the single most likely cause for THIS issue only, from the evidence'
            + (" and findings" if actionable_findings else "")
            + ",\n"
            '  "reasoning": 2-4 sentences that cite the exact facts (values, statuses, '
            "service/device names) supporting the root cause,\n"
            '  "confidence": integer 0-100 reflecting how strongly the evidence supports it,\n'
            '  "confidence_reasons": array of 2-4 short strings, each citing one concrete fact,\n'
            '  "resolution_steps": array of 4-8 concrete ordered steps with exact Windows paths/commands,\n'
            '  "prevention_tips": array of 2-4 short, specific tips to stop recurrence.\n'
        )
        if not actionable_findings:
            guidance += (
                "\nNo hardware/driver fault was detected for this specific issue. State that clearly in "
                "root_cause and give practical next steps for the user's symptom (privacy settings, "
                "default device selection, mute/volume, app permissions, restart the app). "
                "Do NOT blame unrelated services or system-wide health issues."
            )

        raw = await self._ollama.generate(
            guidance,
            system=_DIAGNOSIS_SYSTEM,
            json_mode=True,
            temperature=0.15,
            options={"num_ctx": 8192, "num_predict": 1100},
        )
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            logger.info("LLM returned non-JSON; keeping deterministic diagnosis.")
            return result
        if not isinstance(data, dict):
            return result

        # Merge — prose and guidance from the LLM, hard facts from the probes.
        result.issue_summary = _clean_str(data.get("issue_summary")) or result.issue_summary
        result.root_cause = _clean_str(data.get("root_cause")) or result.root_cause
        result.reasoning = _clean_str(data.get("reasoning")) or result.reasoning

        reasons = _clean_list(data.get("confidence_reasons"))
        if reasons:
            result.confidence_reasons = reasons[:4]
        steps = _clean_list(data.get("resolution_steps"))
        if steps:
            result.resolution_steps = steps[:8]
        tips = _clean_list(data.get("prevention_tips"))
        if tips:
            result.prevention_tips = tips[:4]

        conf = data.get("confidence")
        if isinstance(conf, (int, float)):
            # Blend LLM confidence with the deterministic floor so it stays evidence-bound.
            result.confidence = max(40, min(96, int(conf)))

        result.model = self._ollama.default_model
        logger.info("LLM-enriched diagnosis (model=%s, steps=%d).",
                    result.model, len(result.resolution_steps))
        return result
