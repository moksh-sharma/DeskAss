"""Machine scan history CRUD."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session as OrmSession

from app.api.deps import container
from app.core.container import Container
from app.db.database import get_db
from app.models.schemas import MachineScanHistorySummary, MachineScanReport

router = APIRouter(prefix="/api/machine-scans", tags=["machine-scans"])


@router.get("", response_model=list[MachineScanHistorySummary], summary="List saved machine scans")
async def list_machine_scans(
    c: Container = Depends(container),
    db: OrmSession = Depends(get_db),
) -> list[MachineScanHistorySummary]:
    return c.machine_scan_history.list_scans(db)


@router.get("/{scan_id}", response_model=MachineScanReport, summary="Get a saved machine scan")
async def get_machine_scan(
    scan_id: int,
    c: Container = Depends(container),
    db: OrmSession = Depends(get_db),
) -> MachineScanReport:
    return c.machine_scan_history.get_scan(db, scan_id)


@router.delete("/{scan_id}", summary="Delete a saved machine scan")
async def delete_machine_scan(
    scan_id: int,
    c: Container = Depends(container),
    db: OrmSession = Depends(get_db),
) -> dict[str, bool]:
    c.machine_scan_history.delete_scan(db, scan_id)
    return {"deleted": True}
