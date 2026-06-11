"""Deepgram speech-to-text for uploaded voice clips and live streaming."""
from __future__ import annotations

import asyncio
import contextlib

from deepgram import AsyncDeepgramClient
from deepgram.core.events import EventType
from deepgram.extensions.types.sockets import ListenV1ControlMessage
from fastapi import WebSocket

from app.core.config import Settings
from app.core.exceptions import ExternalServiceError, FeatureUnavailableError
from app.core.logging import get_logger

logger = get_logger(__name__)

# Client overrides and env default (multi = Hindi + English code-switching on nova-3).
_ALLOWED_LANGUAGES = frozenset({"multi", "en", "hi", "en-in", "hi-in"})


class DeepgramService:
    """Transcribes audio via Deepgram pre-recorded and live WebSocket APIs."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._api_key = (settings.deepgram_api_key or "").strip()
        self._model = settings.deepgram_model
        self._language = settings.deepgram_language
        self._timeout = settings.deepgram_timeout_seconds
        self._client: AsyncDeepgramClient | None = None
        if self._api_key:
            self._client = AsyncDeepgramClient(api_key=self._api_key)

    @property
    def is_configured(self) -> bool:
        return bool(self._api_key)

    def _require_client(self) -> AsyncDeepgramClient:
        if not self._client:
            raise FeatureUnavailableError(
                "Deepgram is not configured. Set DEEPGRAM_API_KEY in backend/.env.",
                error_code="feature_unavailable",
            )
        return self._client

    async def health(self) -> bool:
        return self.is_configured

    def resolve_language(self, override: str | None = None) -> str:
        """Pick STT language: client override, else env default (multi for Hindi+English)."""
        if override:
            normalized = override.strip().lower().replace("_", "-")
            if normalized in _ALLOWED_LANGUAGES:
                return "en" if normalized == "en-in" else "hi" if normalized == "hi-in" else normalized
        return self._language

    @staticmethod
    def _language_label(code: str) -> str:
        labels = {
            "multi": "Hindi + English (auto)",
            "en": "English",
            "hi": "Hindi",
        }
        return labels.get(code, code)

    def listen_options(self, language: str | None = None) -> dict[str, str]:
        lang = self.resolve_language(language)
        return {
            "model": self._model,
            "language": lang,
            "punctuate": "true",
            "smart_format": "true",
        }

    @staticmethod
    def _extract_transcript(response: object) -> str:
        try:
            channels = response.results.channels  # type: ignore[attr-defined]
            if channels:
                alts = channels[0].alternatives
                if alts:
                    text = alts[0].transcript or ""
                    if text.strip():
                        return text.strip()
        except AttributeError:
            pass
        return ""

    async def transcribe(
        self,
        audio_bytes: bytes,
        filename: str = "audio.wav",
        content_type: str = "audio/wav",
    ) -> str:
        client = self._require_client()

        logger.info(
            "Deepgram transcribe: %d bytes (%s, %s)",
            len(audio_bytes),
            filename,
            content_type,
        )

        try:
            opts = self.listen_options()
            response = await client.listen.v1.media.transcribe_file(
                request=audio_bytes,
                model=opts["model"],
                language=opts["language"],
                smart_format=True,
                punctuate=True,
                request_options={
                    "timeout_in_seconds": int(self._timeout),
                    "max_retries": 2,
                },
            )
        except Exception as exc:
            logger.exception("Deepgram transcription failed")
            raise ExternalServiceError(f"Deepgram transcription failed: {exc}") from exc

        text = self._extract_transcript(response)
        if not text:
            raise ExternalServiceError("Deepgram returned an empty transcription.")
        return text

    async def stream_session(self, websocket: WebSocket, language: str | None = None) -> None:
        """Bridge browser PCM chunks to Deepgram live STT with interim results."""
        client = self._require_client()
        opts = self.listen_options(language)
        committed: list[str] = []
        interim = ""

        async def send_transcript(*, is_final: bool, detected_language: str | None = None) -> None:
            parts = committed + ([interim] if interim else [])
            full = " ".join(parts).strip()
            payload: dict[str, object] = {"type": "transcript", "text": full, "is_final": is_final}
            if detected_language:
                payload["language"] = detected_language
            await websocket.send_json(payload)

        try:
            async with client.listen.v1.connect(
                model=opts["model"],
                language=opts["language"],
                encoding="linear16",
                sample_rate="16000",
                channels="1",
                interim_results="true",
                punctuate=opts["punctuate"],
                smart_format=opts["smart_format"],
            ) as connection:

                async def on_message(result: object) -> None:
                    nonlocal interim
                    if getattr(result, "type", None) != "Results":
                        return
                    channel = getattr(result, "channel", None)
                    if channel is None or not channel.alternatives:
                        return
                    alt = channel.alternatives[0]
                    transcript = (alt.transcript or "").strip()
                    if not transcript:
                        return
                    detected = None
                    langs = getattr(alt, "languages", None)
                    if langs:
                        detected = langs[0]
                    if getattr(result, "is_final", False):
                        committed.append(transcript)
                        interim = ""
                    else:
                        interim = transcript
                    await send_transcript(
                        is_final=bool(getattr(result, "is_final", False)),
                        detected_language=detected,
                    )

                connection.on(EventType.MESSAGE, on_message)
                listen_task = asyncio.create_task(connection.start_listening())

                try:
                    while True:
                        message = await websocket.receive()
                        if message["type"] == "websocket.disconnect":
                            break
                        chunk = message.get("bytes")
                        if chunk:
                            await connection.send_media(chunk)
                            continue
                        text = message.get("text")
                        if text == "stop":
                            await connection.send_control(
                                ListenV1ControlMessage(type="Finalize")
                            )
                            await asyncio.sleep(0.4)
                            break
                finally:
                    listen_task.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await listen_task
        except Exception as exc:
            logger.exception("Deepgram live stream failed")
            with contextlib.suppress(Exception):
                await websocket.send_json(
                    {"type": "error", "message": f"Live transcription failed: {exc}"}
                )
            raise

