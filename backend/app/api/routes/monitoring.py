"""Continuous monitoring, historical analytics and incident reconstruction."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, Query

from app.api.deps import container
from app.core.container import Container
from app.core.logging import get_logger
from app.services.telemetry_analytics_service import parse_incident_time

router = APIRouter(prefix="/api/monitoring", tags=["monitoring"])
logger = get_logger(__name__)


@router.get("/status", summary="Live monitoring status + latest telemetry")
async def status(c: Container = Depends(container)) -> dict[str, Any]:
    return await asyncio.to_thread(c.telemetry.status)


@router.get("/trends", summary="Telemetry trends over a window")
async def trends(days: int = Query(7, ge=1, le=365), c: Container = Depends(container)) -> dict[str, Any]:
    return await asyncio.to_thread(c.telemetry.trends, days)


@router.get("/events", summary="Recent monitor events")
async def events(
    days: int = Query(30, ge=1, le=365),
    category: Optional[str] = Query(None),
    limit: int = Query(80, ge=1, le=500),
    c: Container = Depends(container),
) -> list[dict[str, Any]]:
    return await asyncio.to_thread(lambda: c.telemetry.events(limit=limit, category=category, days=days))


@router.get("/alerts", summary="Active alerts and anomalies")
async def alerts(hours: int = Query(48, ge=1, le=720), c: Container = Depends(container)) -> list[dict[str, Any]]:
    return await asyncio.to_thread(lambda: c.telemetry.alerts(hours=hours))


@router.get("/changes", summary="Change / device / driver / security timeline")
async def changes(days: int = Query(30, ge=1, le=365), c: Container = Depends(container)) -> list[dict[str, Any]]:
    return await asyncio.to_thread(lambda: c.telemetry.change_timeline(days=days))


@router.get("/boot-history", summary="Boot history and uptime")
async def boot_history(c: Container = Depends(container)) -> dict[str, Any]:
    return await asyncio.to_thread(c.telemetry.boot_history)


@router.get("/predictions", summary="Predictive analytics (disk full, regression, battery)")
async def predictions(c: Container = Depends(container)) -> dict[str, Any]:
    return await asyncio.to_thread(c.telemetry.predictions)


@router.get("/machine-memory", summary="Long-term machine understanding")
async def machine_memory(c: Container = Depends(container)) -> dict[str, Any]:
    return await asyncio.to_thread(c.telemetry.machine_memory)


@router.get("/digital-twin", summary="Complete digital representation of the machine")
async def digital_twin(c: Container = Depends(container)) -> dict[str, Any]:
    return await asyncio.to_thread(c.telemetry.digital_twin)


@router.get("/report", summary="Auto-generated daily/weekly/monthly report")
async def report(
    period: str = Query("daily", pattern="^(daily|weekly|monthly)$"),
    c: Container = Depends(container),
) -> dict[str, Any]:
    return await asyncio.to_thread(c.telemetry.report, period)


@router.get("/incident", summary="Reconstruct an incident around a point in time")
async def incident(
    when: Optional[str] = Query(None, description="ISO timestamp; omit to use `text`"),
    text: Optional[str] = Query(None, description="Natural language e.g. 'froze 20 minutes ago'"),
    window_minutes: int = Query(30, ge=5, le=720),
    include_event_logs: bool = Query(True),
    c: Container = Depends(container),
) -> dict[str, Any]:
    if when:
        try:
            anchor = datetime.fromisoformat(when.replace("Z", "+00:00")).astimezone(timezone.utc).replace(tzinfo=None)
        except ValueError:
            anchor, window_minutes = parse_incident_time(text or "")
    else:
        anchor, window_minutes = parse_incident_time(text or "")

    log_entries: list[dict] = []
    if include_event_logs:
        def _logs() -> list[dict]:
            summary = c.event_logs.collect(hours_back=72, max_per_log=80)
            return [e.model_dump(mode="json") for e in (summary.entries or [])]
        try:
            log_entries = await asyncio.to_thread(_logs)
        except Exception as exc:  # pragma: no cover
            logger.debug("incident event-log fetch failed: %s", exc)

    return await asyncio.to_thread(
        lambda: c.telemetry.incident(anchor, window_minutes, event_log_entries=log_entries)
    )
