"""Persistence and retrieval for comprehensive machine scan history."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from app.core.exceptions import ResourceNotFoundError
from app.core.logging import get_logger
from app.db.models import MachineScanRecord
from app.models.schemas import MachineScanHistorySummary, MachineScanReport

logger = get_logger(__name__)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _parse_scanned_at(report: dict[str, Any]) -> datetime:
    """Use the scan's own timestamp so history matches the runtime view."""
    raw = report.get("generated_at")
    if not raw:
        return _utc_now()
    try:
        text = str(raw).strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is not None:
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt
    except (TypeError, ValueError):
        return _utc_now()


class MachineScanHistoryService:
    """CRUD for saved machine scans."""

    def save_scan(self, db: OrmSession, report: dict[str, Any]) -> MachineScanHistorySummary:
        health = report.get("health_report") or {}
        score = int(health.get("overall_score") or 0)
        status = str(health.get("overall_status") or "Unknown")
        title = f"Scan · {status} {score}/100"
        ai = report.get("ai_summary") or {}
        scanned_at = _parse_scanned_at(report)
        record = MachineScanRecord(
            title=title,
            health_score=score,
            health_status=status,
            scan_duration_seconds=float(report.get("scan_duration_seconds") or 0),
            has_ai_summary=bool(ai.get("summary")),
            report_json=json.dumps(report, default=str),
            created_at=scanned_at,
            updated_at=scanned_at,
        )
        db.add(record)
        db.flush()
        report["scan_id"] = record.id
        record.report_json = json.dumps(report, default=str)
        db.flush()
        logger.info("Saved machine scan history id=%s (%s)", record.id, title)
        return self._to_summary(record)

    def update_ai_summary(
        self,
        db: OrmSession,
        scan_id: int,
        ai_summary: dict[str, Any],
    ) -> MachineScanHistorySummary:
        record = db.get(MachineScanRecord, scan_id)
        if record is None:
            raise ResourceNotFoundError(f"Machine scan {scan_id} not found")
        try:
            report = json.loads(record.report_json)
        except json.JSONDecodeError:
            report = {}
        # Persist the summary exactly as returned to the UI (text, actions, model flags).
        report["ai_summary"] = ai_summary
        report["ai_summary_generated_at"] = _utc_now().isoformat() + "Z"
        record.report_json = json.dumps(report, default=str)
        record.has_ai_summary = bool(ai_summary.get("summary"))
        record.updated_at = _parse_scanned_at(report)
        db.flush()
        logger.info("Updated AI summary on machine scan id=%s", scan_id)
        return self._to_summary(record)

    def list_scans(self, db: OrmSession, *, limit: int = 50) -> list[MachineScanHistorySummary]:
        rows = db.execute(
            select(MachineScanRecord).order_by(MachineScanRecord.created_at.desc()).limit(limit)
        ).scalars().all()
        return [self._to_summary(r) for r in rows]

    def get_scan(self, db: OrmSession, scan_id: int) -> MachineScanReport:
        record = db.get(MachineScanRecord, scan_id)
        if record is None:
            raise ResourceNotFoundError(f"Machine scan {scan_id} not found")
        try:
            data = json.loads(record.report_json)
        except json.JSONDecodeError as exc:
            raise ResourceNotFoundError(f"Machine scan {scan_id} data is corrupt") from exc
        data["scan_id"] = record.id
        # Ensure the header timestamp always matches what was stored at scan time.
        if not data.get("generated_at") and record.created_at:
            data["generated_at"] = record.created_at.isoformat() + "Z"
        return MachineScanReport.model_validate(data)

    def delete_scan(self, db: OrmSession, scan_id: int) -> None:
        record = db.get(MachineScanRecord, scan_id)
        if record is None:
            raise ResourceNotFoundError(f"Machine scan {scan_id} not found")
        db.delete(record)

    @staticmethod
    def _to_summary(record: MachineScanRecord) -> MachineScanHistorySummary:
        scanned_at = record.created_at
        try:
            data = json.loads(record.report_json)
            scanned_at = _parse_scanned_at(data)
        except (json.JSONDecodeError, TypeError):
            pass
        return MachineScanHistorySummary(
            id=record.id,
            title=record.title,
            health_score=record.health_score,
            health_status=record.health_status,
            scan_duration_seconds=record.scan_duration_seconds,
            has_ai_summary=record.has_ai_summary,
            scanned_at=scanned_at,
            updated_at=record.updated_at,
        )
