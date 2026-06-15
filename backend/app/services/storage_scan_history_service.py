"""Persistence, history, change-tracking and growth inputs for storage scans."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from app.core.exceptions import ResourceNotFoundError
from app.core.logging import get_logger
from app.db.models import StorageScanRecord

logger = get_logger(__name__)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class StorageScanHistoryService:
    """CRUD + history helpers for Advanced Storage Intelligence scans."""

    # ---- history inputs for the next deep scan ----------------------- #
    def history_snapshots(self, db: OrmSession, *, limit: int = 30) -> list[dict[str, Any]]:
        """Oldest..newest light snapshots used for growth prediction."""
        rows = db.execute(
            select(StorageScanRecord)
            .order_by(StorageScanRecord.created_at.asc())
            .limit(limit)
        ).scalars().all()
        out: list[dict[str, Any]] = []
        for r in rows:
            if not r.snapshot_json:
                continue
            try:
                out.append(json.loads(r.snapshot_json))
            except json.JSONDecodeError:
                continue
        return out

    def latest_snapshot(self, db: OrmSession) -> dict[str, Any] | None:
        row = db.execute(
            select(StorageScanRecord).order_by(StorageScanRecord.created_at.desc()).limit(1)
        ).scalars().first()
        if not row or not row.snapshot_json:
            return None
        try:
            return json.loads(row.snapshot_json)
        except json.JSONDecodeError:
            return None

    def latest_report(self, db: OrmSession) -> dict[str, Any] | None:
        row = db.execute(
            select(StorageScanRecord).order_by(StorageScanRecord.created_at.desc()).limit(1)
        ).scalars().first()
        if not row:
            return None
        try:
            data = json.loads(row.report_json)
            data["scan_id"] = row.id
            return data
        except json.JSONDecodeError:
            return None

    # ---- save / load -------------------------------------------------- #
    def save_scan(self, db: OrmSession, report: dict[str, Any]) -> dict[str, Any]:
        health = report.get("health") or {}
        score = int(health.get("overall_score") or 0)
        status = str(health.get("overall_status") or "Unknown")
        recoverable = float((report.get("cleanup") or {}).get("total_potential_gb") or 0)
        primary = report.get("primary_drive") or {}
        snapshot = report.get("snapshot") or {}
        title = f"Storage · {status} {score}/100 · {round(recoverable, 1)} GB free-able"
        record = StorageScanRecord(
            title=title,
            health_score=score,
            health_status=status,
            recoverable_gb=recoverable,
            primary_free_gb=float(primary.get("free_gb") or 0),
            primary_used_pct=float(primary.get("used_pct") or 0),
            scan_duration_seconds=float(report.get("scan_duration_seconds") or 0),
            report_json=json.dumps(report, default=str),
            snapshot_json=json.dumps(snapshot, default=str),
            created_at=_utc_now(),
            updated_at=_utc_now(),
        )
        db.add(record)
        db.flush()
        report["scan_id"] = record.id
        record.report_json = json.dumps(report, default=str)
        db.flush()
        logger.info("Saved storage scan history id=%s (%s)", record.id, title)
        return self._to_summary(record)

    def list_scans(self, db: OrmSession, *, limit: int = 50) -> list[dict[str, Any]]:
        rows = db.execute(
            select(StorageScanRecord).order_by(StorageScanRecord.created_at.desc()).limit(limit)
        ).scalars().all()
        return [self._to_summary(r) for r in rows]

    def timeline(self, db: OrmSession, *, limit: int = 30) -> list[dict[str, Any]]:
        """Storage change timeline (oldest..newest) for the dashboard chart."""
        rows = db.execute(
            select(StorageScanRecord).order_by(StorageScanRecord.created_at.asc()).limit(limit)
        ).scalars().all()
        return [
            {
                "id": r.id,
                "scanned_at": r.created_at.isoformat() + "Z",
                "health_score": r.health_score,
                "primary_free_gb": r.primary_free_gb,
                "primary_used_pct": r.primary_used_pct,
                "recoverable_gb": r.recoverable_gb,
            }
            for r in rows
        ]

    def get_scan(self, db: OrmSession, scan_id: int) -> dict[str, Any]:
        record = db.get(StorageScanRecord, scan_id)
        if record is None:
            raise ResourceNotFoundError(f"Storage scan {scan_id} not found")
        try:
            data = json.loads(record.report_json)
        except json.JSONDecodeError as exc:
            raise ResourceNotFoundError(f"Storage scan {scan_id} data is corrupt") from exc
        data["scan_id"] = record.id
        return data

    def delete_scan(self, db: OrmSession, scan_id: int) -> None:
        record = db.get(StorageScanRecord, scan_id)
        if record is None:
            raise ResourceNotFoundError(f"Storage scan {scan_id} not found")
        db.delete(record)

    @staticmethod
    def _to_summary(record: StorageScanRecord) -> dict[str, Any]:
        return {
            "id": record.id,
            "title": record.title,
            "health_score": record.health_score,
            "health_status": record.health_status,
            "recoverable_gb": record.recoverable_gb,
            "primary_free_gb": record.primary_free_gb,
            "primary_used_pct": record.primary_used_pct,
            "scan_duration_seconds": record.scan_duration_seconds,
            "scanned_at": record.created_at.isoformat() + "Z",
        }
