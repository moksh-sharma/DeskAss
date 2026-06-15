"""Speech-to-text facade - routes to ElevenLabs or Deepgram based on settings."""
from __future__ import annotations

from fastapi import WebSocket

from app.core.config import Settings
from app.services.deepgram_service import DeepgramService
from app.services.elevenlabs_service import ElevenLabsService


class SpeechService:
    """Unified STT interface used by API routes."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._elevenlabs = ElevenLabsService(settings)
        self._deepgram = DeepgramService(settings)

    @property
    def provider(self) -> str:
        if self._settings.stt_provider.strip().lower() == "deepgram":
            return "deepgram"
        if self._elevenlabs.is_configured:
            return "elevenlabs"
        if self._deepgram.is_configured:
            return "deepgram"
        return "elevenlabs"

    @property
    def is_configured(self) -> bool:
        return self._elevenlabs.is_configured or self._deepgram.is_configured

    def _active(self):
        return self._deepgram if self.provider == "deepgram" else self._elevenlabs

    async def health(self) -> bool:
        return await self._active().health()

    def resolve_language(self, override: str | None = None) -> str:
        return self._active().resolve_language(override)

    async def transcribe(
        self,
        audio_bytes: bytes,
        filename: str = "audio.wav",
        content_type: str = "audio/wav",
    ) -> str:
        return await self._active().transcribe(audio_bytes, filename=filename, content_type=content_type)

    async def stream_session(self, websocket: WebSocket, language: str | None = None) -> None:
        await self._active().stream_session(websocket, language=language)

    def provider_label(self) -> str:
        active = self._active()
        if self.provider == "elevenlabs":
            lang = ElevenLabsService._language_label(self._settings.elevenlabs_language)
            model = (self._settings.elevenlabs_stt_realtime_model or "scribe_v2_realtime").strip()
            label = "Scribe v2 Realtime" if model == "scribe_v2_realtime" else model
            return f"ElevenLabs ({label}, {lang})"
        lang = DeepgramService._language_label(self._settings.deepgram_language)
        return f"Deepgram ({self._settings.deepgram_model}, {lang})"

    def not_configured_message(self) -> str:
        if self.provider == "deepgram":
            return "Deepgram is not configured. Set DEEPGRAM_API_KEY in backend/.env."
        return "ElevenLabs is not configured. Set ELEVENLABS_API_KEY in backend/.env."
