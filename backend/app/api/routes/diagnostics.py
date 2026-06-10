"""Diagnostics, event-log and full-scan endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session as OrmSession

from app.api.deps import container
from app.core.container import Container
from app.db.database import get_db
from app.models.schemas import (
    EventLogSummary,
    HealthReport,
    MachineAiSummary,
    MachineScanReport,
    MachineScanSummaryRequest,
    SystemDiagnostics,
)

router = APIRouter(prefix="/api/diagnostics", tags=["diagnostics"])


@router.get("", response_model=SystemDiagnostics, summary="Collect live system diagnostics")
async def get_diagnostics(
    top_n: int = Query(10, ge=1, le=50),
    c: Container = Depends(container),
) -> SystemDiagnostics:
    return c.diagnostics.collect(top_n=top_n)


@router.get("/event-logs", response_model=EventLogSummary, summary="Collect Windows event logs")
async def get_event_logs(
    hours_back: int = Query(72, ge=1, le=720),
    max_per_log: int = Query(60, ge=1, le=300),
    c: Container = Depends(container),
) -> EventLogSummary:
    return c.event_logs.collect(hours_back=hours_back, max_per_log=max_per_log)


@router.post("/scan", response_model=HealthReport, summary="Run a full diagnostic scan")
async def full_scan(c: Container = Depends(container)) -> HealthReport:
    diagnostics = c.diagnostics.collect(top_n=10)
    event_logs = c.event_logs.collect()
    findings = c.troubleshooter.analyze(diagnostics, event_logs)
    return c.health.build_report(diagnostics, event_logs, findings)


@router.post(
    "/full-scan",
    response_model=MachineScanReport,
    summary="Run the comprehensive machine scan (all categories + health score)",
)
async def comprehensive_scan(
    c: Container = Depends(container),
    db: OrmSession = Depends(get_db),
) -> MachineScanReport:
    report = await c.machine_scan.scan()
    # Run the Windows troubleshooter analysis on live diagnostics + event logs.
    diagnostics = c.diagnostics.collect(top_n=10)
    event_logs = c.event_logs.collect()
    findings = c.troubleshooter.analyze(diagnostics, event_logs)
    report["findings"] = [f.model_dump(mode="json") for f in findings]
    report["event_logs"] = event_logs.model_dump(mode="json")
    saved = c.machine_scan_history.save_scan(db, report)
    report["scan_id"] = saved.id
    return MachineScanReport(**report)


@router.post(
    "/full-scan/summary",
    response_model=MachineAiSummary,
    summary="Generate an AI summary from a completed machine scan",
)
async def machine_scan_summary(
    payload: MachineScanSummaryRequest,
    c: Container = Depends(container),
    db: OrmSession = Depends(get_db),
) -> MachineAiSummary:
    report = payload.model_dump()
    summary = await c.machine_scan.generate_summary(report)
    result = MachineAiSummary(**summary)
    if payload.scan_id is not None:
        c.machine_scan_history.update_ai_summary(db, payload.scan_id, result.model_dump(mode="json"))
    return result
