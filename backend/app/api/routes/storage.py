"""Advanced Storage Intelligence Engine endpoints."""
from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session as OrmSession

from app.api.deps import container
from app.core.container import Container
from app.core.logging import get_logger
from app.db.database import get_db

router = APIRouter(prefix="/api/storage", tags=["storage"])
logger = get_logger(__name__)


@router.post("/quick", summary="Fast storage scan (drives + recoverable space)")
async def quick_storage_scan(c: Container = Depends(container)) -> dict[str, Any]:
    return await asyncio.to_thread(c.storage.quick_scan)


@router.post("/scan", summary="Run the deep storage intelligence scan (heavy, persisted)")
async def deep_storage_scan(
    tree_budget: float = Query(240.0, ge=20.0, le=900.0),
    c: Container = Depends(container),
    db: OrmSession = Depends(get_db),
) -> dict[str, Any]:
    history = c.storage_history.history_snapshots(db)
    previous = c.storage_history.latest_snapshot(db)
    logger.info("Running deep storage scan (tree_budget=%ss, history=%d)", tree_budget, len(history))
    report = await asyncio.to_thread(
        c.storage.deep_scan,
        tree_budget=tree_budget,
        history=history,
        previous_snapshot=previous,
    )
    report["timeline"] = c.storage_history.timeline(db)
    summary = c.storage_history.save_scan(db, report)
    report["scan_id"] = summary["id"]
    # Refresh timeline to include the scan we just saved.
    report["timeline"] = c.storage_history.timeline(db)
    return report


@router.get("", summary="List saved storage scans")
async def list_storage_scans(
    c: Container = Depends(container),
    db: OrmSession = Depends(get_db),
) -> list[dict[str, Any]]:
    return c.storage_history.list_scans(db)


@router.get("/latest", summary="Get the most recent storage scan")
async def latest_storage_scan(
    c: Container = Depends(container),
    db: OrmSession = Depends(get_db),
) -> dict[str, Any]:
    report = c.storage_history.latest_report(db)
    if report is None:
        return {}
    report["timeline"] = c.storage_history.timeline(db)
    return report


@router.get("/{scan_id}", summary="Get a saved storage scan")
async def get_storage_scan(
    scan_id: int,
    c: Container = Depends(container),
    db: OrmSession = Depends(get_db),
) -> dict[str, Any]:
    report = c.storage_history.get_scan(db, scan_id)
    report["timeline"] = c.storage_history.timeline(db)
    return report


@router.delete("/{scan_id}", summary="Delete a saved storage scan")
async def delete_storage_scan(
    scan_id: int,
    c: Container = Depends(container),
    db: OrmSession = Depends(get_db),
) -> dict[str, bool]:
    c.storage_history.delete_scan(db, scan_id)
    return {"deleted": True}
