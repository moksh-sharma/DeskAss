"""System / service health endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app import __version__
from app.api.deps import container
from app.core.container import Container
from app.models.schemas import ServiceStatus, SystemStatus
from app.services.deepgram_service import DeepgramService

router = APIRouter(tags=["health"])


@router.get("/", summary="Liveness probe")
async def root() -> dict[str, str]:
    return {"status": "running"}


@router.get("/api/status", response_model=SystemStatus, summary="Service health overview")
async def status(c: Container = Depends(container)) -> SystemStatus:
    ollama_ok = await c.ollama.health()
    deepgram_ok = await c.deepgram.health()
    ocr_ok = c.ocr.is_available()
    kb_count = c.rag.count()

    services = [
        ServiceStatus(name="ollama", healthy=ollama_ok,
                      detail=f"{c.settings.ollama_base_url} ({c.settings.default_model})"),
        ServiceStatus(
            name="deepgram",
            healthy=deepgram_ok,
            detail=(
                f"Deepgram ({c.settings.deepgram_model}, {DeepgramService._language_label(c.settings.deepgram_language)})"
                if deepgram_ok
                else "Set DEEPGRAM_API_KEY in backend/.env"
            ),
        ),
        ServiceStatus(name="ocr", healthy=ocr_ok,
                      detail=c.ocr.backend_name if ocr_ok else "No OCR engine available"),
        ServiceStatus(name="knowledge_base", healthy=kb_count > 0,
                      detail=f"{kb_count} documents indexed"),
    ]
    return SystemStatus(status="running", version=__version__, services=services)


@router.get("/api/models", summary="List available Ollama models")
async def models(c: Container = Depends(container)) -> dict[str, object]:
    available = await c.ollama.list_models()
    return {"default": c.settings.default_model, "models": available}
