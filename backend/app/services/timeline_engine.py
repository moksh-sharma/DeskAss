"""Timeline engine — merge events, changes, and telemetry into ordered timelines."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

Window = Literal["24h", "7d", "30d", "90d"]

_WINDOW_HOURS = {"24h": 24, "7d": 168, "30d": 720, "90d": 2160}


@dataclass
class TimelineEvent:
    ts: str
    source: str
    category: str
    summary: str
    severity: str = "info"
    detail: str = ""


@dataclass
class TimelineResult:
    anchor: str | None
    window: str
    events: list[TimelineEvent] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "anchor": self.anchor,
            "window": self.window,
            "events": [
                {
                    "ts": e.ts,
                    "source": e.source,
                    "category": e.category,
                    "summary": e.summary,
                    "severity": e.severity,
                    "detail": e.detail,
                }
                for e in self.events
            ],
        }


def _parse_window(window: str | Window) -> int:
    return _WINDOW_HOURS.get(window, 24)


def _window_to_days(window: str | Window) -> int:
    hours = _parse_window(window)
    return max(1, hours // 24)


def build_timeline(
    anchor: datetime | None = None,
    window: str | Window = "24h",
    *,
    include_changes: bool = True,
    include_incident: bool = True,
    message: str = "",
) -> TimelineResult:
    """Assemble a unified timeline from SQLite telemetry and monitor events."""
    from app.services.telemetry_analytics_service import (
        TelemetryAnalyticsService,
        parse_incident_time,
    )

    if anchor is None and message:
        anchor, window = parse_incident_time(message)

    hours = _parse_window(window)
    days = _window_to_days(window)
    telem = TelemetryAnalyticsService()
    result = TimelineResult(
        anchor=anchor.isoformat() if anchor else None,
        window=window,
    )

    if include_changes:
        for row in telem.change_timeline(days=days)[:40]:
            result.events.append(TimelineEvent(
                ts=str(row.get("ts") or row.get("time") or ""),
                source="change_detection",
                category=str(row.get("category") or row.get("type") or "change"),
                summary=str(row.get("summary") or row.get("description") or row.get("label") or ""),
                severity=str(row.get("severity") or "info"),
                detail=str(row.get("detail") or ""),
            ))

    if include_incident and anchor is not None:
        inc = telem.incident(anchor, window)
        for row in (inc.get("timeline") or [])[:30]:
            result.events.append(TimelineEvent(
                ts=str(row.get("ts") or ""),
                source="telemetry",
                category=str(row.get("type") or "metric"),
                summary=str(row.get("label") or row.get("summary") or ""),
                severity=str(row.get("severity") or "info"),
                detail=str(row.get("detail") or row.get("value") or ""),
            ))

    result.events.sort(key=lambda e: e.ts, reverse=True)
    return result
