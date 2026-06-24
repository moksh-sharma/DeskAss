"""System / service health endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app import __version__
from app.api.deps import container
from app.core.container import Container
from app.models.schemas import ServiceStatus, SystemStatus

router = APIRouter(tags=["health"])


@router.get("/", summary="Liveness probe")
async def root() -> dict[str, str]:
    return {"status": "running"}


@router.get("/api/status", response_model=SystemStatus, summary="Service health overview")
async def status(c: Container = Depends(container)) -> SystemStatus:
    speech_ok = await c.speech.health()
    ocr_ok = c.ocr.is_available()
    kb_count = c.rag.count()

    services = [
        ServiceStatus(name="diagnosis_engine", healthy=True,
                      detail="Deterministic rule-based engine (no AI model)"),
        ServiceStatus(
            name="speech_to_text",
            healthy=speech_ok,
            detail=c.speech.provider_label() if speech_ok else c.speech.not_configured_message(),
        ),
        ServiceStatus(name="ocr", healthy=ocr_ok,
                      detail=c.ocr.backend_name if ocr_ok else "No OCR engine available"),
        ServiceStatus(name="knowledge_base", healthy=kb_count > 0,
                      detail=f"{kb_count} documents indexed"),
    ]
    return SystemStatus(status="running", version=__version__, services=services)
