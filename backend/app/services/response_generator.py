"""Template-based response generator — deterministic, no LLM text generation."""
from __future__ import annotations

from typing import Any

from app.models.schemas import (
    DiagnosisResult,
    Evidence,
    IssueProfile,
    RecommendedFix,
    Severity,
    TroubleshooterFinding,
)


def _severity_rank(s: Severity) -> int:
    return {
        Severity.healthy: 0,
        Severity.info: 1,
        Severity.warning: 2,
        Severity.critical: 3,
    }.get(s, 1)


def _evidence_line(e: Evidence) -> str:
    if e.label and e.value:
        return f"{e.label}: {e.value}"
    return e.value or e.label or ""


def render_performance_diagnosis(
    findings: list[TroubleshooterFinding],
    evidence: list[Evidence],
    profile: IssueProfile,
    *,
    correlations: list[str] | None = None,
) -> DiagnosisResult:
    """Template for 'Why is my PC slow?' style answers."""
    ranked = sorted(findings, key=lambda f: _severity_rank(f.severity), reverse=True)
    top = ranked[0] if ranked else None
    title = top.title if top else "Performance Review"
    detected = top.detected if top else "No critical performance fault detected."
    cause = top.likely_cause if top else "System metrics are within normal range."

    evidence_lines = [_evidence_line(e) for e in evidence[:8]]
    evidence_lines = [line for line in evidence_lines if line]
    if correlations:
        evidence_lines.extend(correlations[:4])

    steps: list[str] = []
    for f in ranked[:3]:
        for s in f.resolution_steps:
            if s not in steps:
                steps.append(s)

    fixes = [
        RecommendedFix(
            title=f.title,
            description=f.likely_cause or f.detected,
            safe_action=f.resolution_steps[0] if f.resolution_steps else None,
            requires_confirmation=True,
        )
        for f in ranked[:4]
    ]

    confidence = 100 if top and top.severity in (Severity.critical, Severity.warning) else 85
    detail_lines = [detected] + [f.detected for f in ranked[1:3] if f.detected and f.detected != detected]

    return DiagnosisResult(
        issue_summary=f"Diagnosis: {title}",
        severity=top.severity if top else Severity.info,
        confidence=confidence,
        confidence_reasons=evidence_lines[:6] or [detected],
        root_cause=cause,
        reasoning="\n".join(detail_lines) if detail_lines else detected,
        evidence=evidence,
        recommended_fixes=fixes,
        resolution_steps=steps[:8],
        prevention_tips=[],
        detail_lines=detail_lines,
    )


def render_printer_discovery(
    printers: list[dict[str, Any]],
    *,
    summary: str = "",
) -> DiagnosisResult:
    """Template for network printer discovery answers."""
    lines: list[str] = []
    for p in printers[:20]:
        name = p.get("name") or "Printer"
        ip = p.get("network_address") or p.get("ip_address") or ""
        status = p.get("health") or p.get("status") or "Unknown"
        bit = f"{name}"
        if ip:
            bit += f" — IP: {ip}"
        bit += f" — Status: {status}"
        lines.append(bit)

    if not lines:
        lines.append(summary or "No network printers were discovered on your LAN.")

    return DiagnosisResult(
        issue_summary="Discovered Printers",
        severity=Severity.info,
        confidence=95,
        confidence_reasons=lines[:6],
        root_cause=lines[0],
        reasoning="\n".join(lines),
        detail_lines=lines,
        recommended_fixes=[],
        resolution_steps=[
            "Settings > Bluetooth & devices > Printers & scanners > Add device.",
            "Add manually by IP if auto-detect misses a printer.",
        ],
        prevention_tips=[],
    )


def render_from_findings(
    findings: list[TroubleshooterFinding],
    profile: IssueProfile,
    *,
    summary: str = "",
    evidence: list[Evidence] | None = None,
    correlations: list[str] | None = None,
) -> DiagnosisResult | None:
    """Pick the best template for the primary enterprise intent."""
    intents = profile.enterprise_intents or []
    primary = intents[0] if intents else ""

    if primary in ("performance_analysis", "application_troubleshooting", "root_cause_analysis"):
        if findings:
            return render_performance_diagnosis(
                findings, evidence or [], profile, correlations=correlations,
            )

    if primary in ("network_discovery", "printer_discovery", "printer_management"):
        # Printer list is usually in informational findings; keep default path.
        pass

    return None
