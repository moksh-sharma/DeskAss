"""Plain-text formatting for diagnosis results (e.g. support tickets)."""
from __future__ import annotations

import re

from app.models.schemas import DiagnosisResult


def format_diagnosis_plain_text(d: DiagnosisResult) -> str:
    """Render a diagnosis the same way the chat card presents it."""
    lines: list[str] = []

    if d.issue_summary:
        lines.append(d.issue_summary)
        lines.append("")

    if d.root_cause:
        lines.append("Likely Root Cause")
        lines.append("-" * 40)
        lines.append(d.root_cause)
        lines.append("")

    if d.reasoning:
        lines.append("Engineering Reasoning")
        lines.append("-" * 40)
        lines.append(d.reasoning)
        lines.append("")

    if d.confidence_reasons:
        lines.append("Confidence Factors")
        lines.append("-" * 40)
        for reason in d.confidence_reasons:
            lines.append(f"  • {reason}")
        lines.append("")

    if d.evidence:
        lines.append("Observed Telemetry Facts")
        lines.append("-" * 40)
        for item in d.evidence:
            lines.append(f"  {item.label}: {item.value} [{item.severity.value}]")
        lines.append("")

    if d.recommended_fixes:
        lines.append("Recommended System Actions")
        lines.append("-" * 40)
        for fix in d.recommended_fixes:
            lines.append(f"  {fix.title}")
            lines.append(f"    {fix.description}")
            if fix.safe_action:
                lines.append(f"    Action: {fix.safe_action}")
        lines.append("")

    if d.visual_guide and d.visual_guide.steps:
        lines.append("Step-by-Step Resolution Guide")
        lines.append("-" * 40)
        lines.append(f"  Source: {d.visual_guide.title} ({d.visual_guide.source_url})")
        for step in d.visual_guide.steps:
            lines.append(f"  {step.step}. {step.text}")
            if step.caption:
                lines.append(f"     ({step.caption})")
        lines.append("")
    elif d.resolution_steps:
        actionable = [
            s for s in d.resolution_steps
            if s.strip() and not re.match(r"^\s*(this is informational|no action needed)\b", s, re.I)
        ]
        if actionable:
            lines.append("Step-by-Step Resolution Guide")
            lines.append("-" * 40)
            for i, step in enumerate(actionable, start=1):
                lines.append(f"  {i}. {step}")
            lines.append("")

    if d.prevention_tips:
        lines.append("Prevention & Best Practices")
        lines.append("-" * 40)
        for tip in d.prevention_tips:
            lines.append(f"  ✓ {tip}")
        lines.append("")

    if d.knowledge_references:
        lines.append("Grounded KB Documentation")
        lines.append("-" * 40)
        for ref in d.knowledge_references:
            lines.append(f"  • {ref.title} ({ref.category}) - {ref.snippet}")
        lines.append("")

    if d.severity or d.confidence:
        meta: list[str] = []
        if d.severity:
            meta.append(f"Severity: {d.severity.value}")
        if d.confidence and not d.is_conversational:
            meta.append(f"Confidence: {d.confidence}%")
        if d.model:
            meta.append(f"Model: {d.model}")
        if meta:
            lines.append(" | ".join(meta))

    text = "\n".join(lines).strip()
    if text:
        return text
    if d.raw_response:
        return d.raw_response.strip()
    return d.issue_summary or d.root_cause or "No assistant reply recorded."
