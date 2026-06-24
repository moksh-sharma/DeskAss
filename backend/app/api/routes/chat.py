"""Main chat / diagnosis endpoint that orchestrates the full pipeline."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import container
from app.core.container import Container
from app.core.logging import get_logger
from app.db.database import session_scope
from app.models.schemas import (
    DiagnoseRequest,
    DiagnoseResponse,
    MessageRole,
    RaiseTicketRequest,
    RaiseTicketResponse,
)
from app.utils.message_intent import is_troubleshooting_message

router = APIRouter(prefix="/api/chat", tags=["chat"])
logger = get_logger(__name__)


@router.post("/diagnose", response_model=DiagnoseResponse, summary="Run an AI diagnosis")
async def diagnose(
    payload: DiagnoseRequest,
    c: Container = Depends(container),
) -> DiagnoseResponse:
    preview = payload.message[:120] + ("..." if len(payload.message) > 120 else "")
    logger.info("AI diagnose request: %s", preview)

    # Persist the user message, then release the DB before any long-running work.
    # Holding a session open during a full scan blocks the monitoring sampler (SQLite lock).
    with session_scope() as db:
        session = c.sessions.ensure_session(db, payload.session_id)
        c.sessions.add_message(db, session.id, MessageRole.user, payload.message)
        session_id = session.id

    # Greetings / small talk - skip diagnostics, RAG, and LLM diagnosis.
    if not payload.ocr_text and not is_troubleshooting_message(payload.message):
        logger.info("Conversational message - skipping diagnosis pipeline")
        diagnosis = c.diagnosis.conversational_response(payload.message)
        with session_scope() as db:
            c.sessions.add_message(db, session_id, MessageRole.assistant, diagnosis.issue_summary)
        return DiagnoseResponse(session_id=session_id, diagnosis=diagnosis)

    # Issue-scoped live investigation - fully deterministic (no AI model).
    logger.info("Session %s - running issue-scoped scan + diagnosis...", session_id)
    diagnosis, report = await c.investigation.diagnose(
        payload.message, ocr_text=payload.ocr_text
    )
    logger.info(
        "Investigation complete - session=%s domains=%s findings=%d severity=%s",
        session_id, report.profile.domains, len(report.findings), diagnosis.severity.value,
    )
    with session_scope() as db:
        c.sessions.add_message(
            db,
            session_id,
            MessageRole.assistant,
            diagnosis.issue_summary or diagnosis.root_cause or "Investigation complete.",
            metadata={
                "diagnosis": diagnosis.model_dump(mode="json"),
                "investigation": report.model_dump(mode="json"),
            },
        )
    return DiagnoseResponse(
        session_id=session_id,
        diagnosis=diagnosis,
        investigation=report,
    )


@router.post("/raise-ticket", response_model=RaiseTicketResponse, summary="Email a support ticket")
async def raise_ticket(
    payload: RaiseTicketRequest,
    c: Container = Depends(container),
) -> RaiseTicketResponse:
    logger.info(
        "Raise ticket request: session=%s issue_len=%d",
        payload.session_id,
        len(payload.user_issue),
    )
    c.tickets.send_ticket_email(
        user_issue=payload.user_issue,
        diagnosis=payload.diagnosis,
        assistant_reply=payload.assistant_reply,
        session_id=payload.session_id,
    )
    return RaiseTicketResponse()
