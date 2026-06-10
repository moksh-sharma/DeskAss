"""Main chat / diagnosis endpoint that orchestrates the full pipeline."""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session as OrmSession

from app.api.deps import container
from app.core.container import Container
from app.core.logging import get_logger
from app.db.database import get_db
from app.models.schemas import (
    DiagnoseRequest,
    DiagnoseResponse,
    EventLogSummary,
    MessageRole,
    SystemDiagnostics,
)
from app.utils.message_intent import is_troubleshooting_message

router = APIRouter(prefix="/api/chat", tags=["chat"])
logger = get_logger(__name__)


@router.post("/diagnose", response_model=DiagnoseResponse, summary="Run an AI diagnosis")
async def diagnose(
    payload: DiagnoseRequest,
    c: Container = Depends(container),
    db: OrmSession = Depends(get_db),
) -> DiagnoseResponse:
    preview = payload.message[:120] + ("..." if len(payload.message) > 120 else "")
    logger.info("AI diagnose request: %s", preview)

    # 1. Resolve / create the session and persist the user message.
    session = c.sessions.ensure_session(db, payload.session_id)
    c.sessions.add_message(db, session.id, MessageRole.user, payload.message)

    # Greetings / small talk - skip diagnostics, RAG, and LLM diagnosis.
    if not payload.ocr_text and not is_troubleshooting_message(payload.message):
        logger.info("Conversational message - skipping diagnosis pipeline")
        diagnosis = c.diagnosis.conversational_response(payload.message)
        c.sessions.add_message(db, session.id, MessageRole.assistant, diagnosis.issue_summary)
        return DiagnoseResponse(session_id=session.id, diagnosis=diagnosis)

    # Issue-scoped live investigation (no knowledge base in the answer path).
    if c.settings.investigation_enabled:
        logger.info("Session %s - running full hardware/software scan + diagnosis...", session.id)
        diagnosis, report = await c.investigation.diagnose(
            payload.message, ocr_text=payload.ocr_text
        )
        logger.info(
            "Investigation complete - session=%s domains=%s findings=%d severity=%s",
            session.id, report.profile.domains, len(report.findings), diagnosis.severity.value,
        )
        c.sessions.add_message(
            db,
            session.id,
            MessageRole.assistant,
            diagnosis.issue_summary or diagnosis.root_cause or "Investigation complete.",
            metadata={
                "diagnosis": diagnosis.model_dump(mode="json"),
                "investigation": report.model_dump(mode="json"),
            },
        )
        return DiagnoseResponse(
            session_id=session.id,
            diagnosis=diagnosis,
            investigation=report,
        )

    logger.info("Session %s - collecting diagnostics and event logs...", session.id)

    # 2. Collect evidence in parallel (diagnostics + event logs are blocking I/O).
    diagnostics: SystemDiagnostics | None = None
    event_logs: EventLogSummary | None = None
    tasks = []
    if payload.include_diagnostics:
        tasks.append(asyncio.to_thread(c.diagnostics.collect, top_n=10))
    if payload.include_event_logs:
        tasks.append(asyncio.to_thread(c.event_logs.collect))
    if tasks:
        results = await asyncio.gather(*tasks)
        idx = 0
        if payload.include_diagnostics:
            diagnostics = results[idx]
            idx += 1
        if payload.include_event_logs:
            event_logs = results[idx]
    logger.info(
        "Evidence collected - diagnostics=%s, event_logs=%s",
        "yes" if diagnostics else "no",
        f"{event_logs.error_count} errors" if event_logs and event_logs.available else "skipped",
    )

    # 3. Run the diagnosis engine (RAG + LLM + heuristics).
    logger.info("Calling Ollama (%s) for diagnosis...", c.settings.default_model)
    # Always use the configured DEFAULT_MODEL (qwen2.5:latest) - no client override.
    diagnosis = await c.diagnosis.diagnose(
        payload.message,
        diagnostics=diagnostics,
        event_logs=event_logs,
        ocr_text=payload.ocr_text,
        model=c.settings.default_model,
    )
    logger.info(
        "AI diagnosis complete - session=%s severity=%s confidence=%s%% root_cause=%s",
        session.id,
        diagnosis.severity.value,
        diagnosis.confidence,
        (diagnosis.root_cause or "")[:80],
    )

    # 4. Persist the assistant response with full metadata.
    c.sessions.add_message(
        db,
        session.id,
        MessageRole.assistant,
        diagnosis.issue_summary or diagnosis.root_cause or "Diagnosis complete.",
        metadata={"diagnosis": diagnosis.model_dump(mode="json")},
    )

    return DiagnoseResponse(
        session_id=session.id,
        diagnosis=diagnosis,
        diagnostics=diagnostics,
        event_logs=event_logs,
    )
