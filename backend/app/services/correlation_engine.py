"""Correlation engine — cross-signal linking for deterministic diagnosis.

Combines knowledge-graph edges, scan escalation hints, and performance/crash
correlations into a single structured result.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.models.schemas import IssueProfile
from app.services.scan_orchestrator import ScanPlan, correlate_escalation


@dataclass
class CorrelationResult:
    correlations: list[str] = field(default_factory=list)
    nodes: int = 0
    edges: int = 0
    escalation: ScanPlan | None = None
    signals: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "correlations": self.correlations,
            "nodes": self.nodes,
            "edges": self.edges,
            "escalation_reason": self.escalation.reason if self.escalation else None,
            "signals": self.signals,
        }


def correlate(
    report: dict[str, Any],
    plan: ScanPlan,
    profile: IssueProfile,
    message: str = "",
) -> CorrelationResult:
    """Build correlation output from scan report and orchestration plan."""
    result = CorrelationResult()

    sw = report.get("software") or {}
    kg = sw.get("knowledge_graph") or {}
    result.correlations = list(kg.get("correlations") or [])[:12]
    result.nodes = int(kg.get("node_count") or len(kg.get("nodes") or []))
    result.edges = int(kg.get("edge_count") or len(kg.get("edges") or []))

    # Performance ↔ process ↔ crash links from knowledge graph
    for edge in (kg.get("edges") or [])[:20]:
        if isinstance(edge, dict):
            label = edge.get("label") or edge.get("type")
            src = edge.get("from") or edge.get("source")
            dst = edge.get("to") or edge.get("target")
            if label and src and dst:
                result.signals.append({"type": str(label), "from": src, "to": dst})

    result.escalation = correlate_escalation(plan, report, message)

    hw = report.get("hardware") or {}
    perf = hw.get("performance") or {}
    crashes = (sw.get("crash_analysis") or {}).get("recent_crashes") or []
    if crashes and (perf.get("cpu_usage_percent") or 0) > 80:
        result.correlations.insert(
            0,
            "High CPU coincides with recent application crashes — check top CPU process.",
        )

    apps = profile.apps or []
    if apps and crashes:
        app = apps[0].lower()
        for c in crashes[:5]:
            name = str(c.get("app") or c.get("application") or "").lower()
            if app in name:
                result.correlations.insert(
                    0,
                    f"Recent crash events involve {apps[0]} — correlate with updates/drivers.",
                )
                break

    return result
