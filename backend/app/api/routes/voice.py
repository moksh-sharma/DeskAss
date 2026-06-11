"""Voice transcription endpoints (ElevenLabs / Deepgram)."""
from __future__ import annotations

import contextlib

from fastapi import APIRouter, Depends, File, UploadFile, WebSocket, WebSocketDisconnect

from app.api.deps import container
from app.core.container import Container, get_container
from app.core.exceptions import FeatureUnavailableError, ValidationError
from app.core.logging import get_logger
from app.models.schemas import TranscriptionResponse

router = APIRouter(prefix="/api/voice", tags=["voice"])
logger = get_logger(__name__)


@router.websocket("/stream")
async def stream_transcribe(
    websocket: WebSocket,
    language: str | None = None,
) -> None:
    await websocket.accept()
    c = get_container()
    if not c.speech.is_configured:
        await websocket.send_json(
            {"type": "error", "message": c.speech.not_configured_message()}
        )
        await websocket.close(code=1008, reason="Speech-to-text not configured")
        return

    resolved = c.speech.resolve_language(language)
    await websocket.send_json({"type": "ready", "language": resolved, "provider": c.speech.provider})

    try:
        await c.speech.stream_session(websocket, language=language)
    except WebSocketDisconnect:
        logger.debug("Voice stream client disconnected")
    except FeatureUnavailableError as exc:
        with contextlib.suppress(Exception):
            await websocket.send_json({"type": "error", "message": exc.message})
    except Exception as exc:
        logger.exception("Voice stream failed")
        with contextlib.suppress(Exception):
            await websocket.send_json({"type": "error", "message": str(exc)})


@router.post("/transcribe", response_model=TranscriptionResponse, summary="Transcribe an audio clip")
async def transcribe(
    file: UploadFile = File(...),
    c: Container = Depends(container),
) -> TranscriptionResponse:
    audio = await file.read()
    if not audio:
        raise ValidationError("Uploaded audio file is empty.")
    wav_bytes, wav_name, wav_type = c.audio.ensure_wav(
        audio,
        filename=file.filename or "recording.webm",
        content_type=file.content_type or "application/octet-stream",
    )
    text = await c.speech.transcribe(wav_bytes, filename=wav_name, content_type=wav_type)
    return TranscriptionResponse(text=text)
