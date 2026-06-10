"""Session history CRUD and export endpoints."""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends
from fastapi.responses import Response, StreamingResponse
from sqlalchemy.orm import Session as OrmSession

from app.api.deps import container
from app.core.container import Container
from app.db.database import get_db
from app.models.schemas import SessionCreate, SessionDetail, SessionSummary

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


@router.get("", response_model=list[SessionSummary], summary="List sessions")
async def list_sessions(
    c: Container = Depends(container),
    db: OrmSession = Depends(get_db),
) -> list[SessionSummary]:
    return c.sessions.list_sessions(db)


@router.post("", response_model=SessionSummary, summary="Create a new session")
async def create_session(
    payload: SessionCreate,
    c: Container = Depends(container),
    db: OrmSession = Depends(get_db),
) -> SessionSummary:
    return c.sessions.create_session(db, payload.title)


@router.get("/{session_id}", response_model=SessionDetail, summary="Get a session with messages")
async def get_session(
    session_id: int,
    c: Container = Depends(container),
    db: OrmSession = Depends(get_db),
) -> SessionDetail:
    return c.sessions.get_session(db, session_id)


@router.delete("/{session_id}", summary="Delete a session")
async def delete_session(
    session_id: int,
    c: Container = Depends(container),
    db: OrmSession = Depends(get_db),
) -> dict[str, bool]:
    c.sessions.delete_session(db, session_id)
    return {"deleted": True}


@router.get("/{session_id}/export/json", summary="Export a session as JSON")
async def export_json(
    session_id: int,
    c: Container = Depends(container),
    db: OrmSession = Depends(get_db),
) -> Response:
    data = c.sessions.export_json(db, session_id)
    payload = json.dumps(data, indent=2, default=str)
    return Response(
        content=payload,
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="session_{session_id}.json"'},
    )


@router.get("/{session_id}/export/pdf", summary="Export a session as PDF")
async def export_pdf(
    session_id: int,
    c: Container = Depends(container),
    db: OrmSession = Depends(get_db),
) -> StreamingResponse:
    from io import BytesIO

    pdf_bytes = c.sessions.export_pdf(db, session_id)
    return StreamingResponse(
        BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="session_{session_id}.pdf"'},
    )
