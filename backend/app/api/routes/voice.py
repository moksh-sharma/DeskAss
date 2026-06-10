"""Voice transcription endpoint (proxies to the Vosk service)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, UploadFile

from app.api.deps import container
from app.core.container import Container
from app.core.exceptions import ValidationError
from app.models.schemas import TranscriptionResponse

router = APIRouter(prefix="/api/voice", tags=["voice"])


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
    text = await c.vosk.transcribe(wav_bytes, filename=wav_name, content_type=wav_type)
    return TranscriptionResponse(text=text)
