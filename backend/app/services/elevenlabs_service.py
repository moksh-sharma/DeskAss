"""ElevenLabs Scribe speech-to-text for uploaded clips and live streaming."""
from __future__ import annotations

import asyncio
import base64
import contextlib
import json
from urllib.parse import urlencode

import httpx
import websockets
from fastapi import WebSocket
from starlette.websockets import WebSocketDisconnect

from app.core.config import Settings
from app.core.exceptions import ExternalServiceError, FeatureUnavailableError
from app.core.logging import get_logger

logger = get_logger(__name__)

_ALLOWED_LANGUAGES = frozenset({"multi", "en", "hi", "en-in", "hi-in"})
_ELEVENLABS_API = "https://api.elevenlabs.io"
_ELEVENLABS_WS = "wss://api.elevenlabs.io/v1/speech-to-text/realtime"
_SCRIBE_V2_REALTIME = "scribe_v2_realtime"


class ElevenLabsService:
    """Transcribes audio via ElevenLabs Scribe batch and realtime WebSocket APIs."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._api_key = (settings.elevenlabs_api_key or "").strip()
        self._batch_model = settings.elevenlabs_stt_model
        realtime = (settings.elevenlabs_stt_realtime_model or "").strip()
        self._realtime_model = realtime or _SCRIBE_V2_REALTIME
        commit = (settings.elevenlabs_realtime_commit_strategy or "vad").strip().lower()
        self._commit_strategy = commit if commit in {"vad", "manual"} else "vad"
        self._language = settings.elevenlabs_language
        self._timeout = settings.elevenlabs_timeout_seconds

    @property
    def is_configured(self) -> bool:
        return bool(self._api_key)

    def _require_key(self) -> str:
        if not self._api_key:
            raise FeatureUnavailableError(
                "ElevenLabs is not configured. Set ELEVENLABS_API_KEY in backend/.env.",
                error_code="feature_unavailable",
            )
        return self._api_key

    async def health(self) -> bool:
        if not self.is_configured:
            return False
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(
                    f"{_ELEVENLABS_API}/v1/user",
                    headers={"xi-api-key": self._api_key},
                )
                return resp.status_code == 200
        except Exception:
            logger.debug("ElevenLabs health check failed", exc_info=True)
            return False

    def resolve_language(self, override: str | None = None) -> str:
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

    def _language_code_param(self, language: str | None = None) -> str | None:
        """Return ElevenLabs language_code, or None for auto-detect."""
        lang = self.resolve_language(language)
        if lang == "multi":
            return None
        return lang

    @staticmethod
    def _extract_transcript(payload: object) -> str:
        if isinstance(payload, dict):
            for key in ("text", "transcript"):
                value = payload.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
        text = getattr(payload, "text", None) or getattr(payload, "transcript", None)
        if isinstance(text, str) and text.strip():
            return text.strip()
        return ""

    async def transcribe(
        self,
        audio_bytes: bytes,
        filename: str = "audio.wav",
        content_type: str = "audio/wav",
    ) -> str:
        api_key = self._require_key()
        logger.info(
            "ElevenLabs transcribe: %d bytes (%s, %s)",
            len(audio_bytes),
            filename,
            content_type,
        )

        data: dict[str, str] = {"model_id": self._batch_model}
        lang_code = self._language_code_param()
        if lang_code:
            data["language_code"] = lang_code

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(
                    f"{_ELEVENLABS_API}/v1/speech-to-text",
                    headers={"xi-api-key": api_key},
                    data=data,
                    files={"file": (filename, audio_bytes, content_type)},
                )
                resp.raise_for_status()
                payload = resp.json()
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text[:300] if exc.response is not None else str(exc)
            logger.exception("ElevenLabs transcription HTTP error")
            raise ExternalServiceError(f"ElevenLabs transcription failed: {detail}") from exc
        except Exception as exc:
            logger.exception("ElevenLabs transcription failed")
            raise ExternalServiceError(f"ElevenLabs transcription failed: {exc}") from exc

        text = self._extract_transcript(payload)
        if not text:
            raise ExternalServiceError("ElevenLabs returned an empty transcription.")
        return text

    async def stream_session(self, websocket: WebSocket, language: str | None = None) -> None:
        """Bridge browser PCM chunks to ElevenLabs realtime Scribe."""
        api_key = self._require_key()
        lang = self.resolve_language(language)

        params: dict[str, str] = {
            "model_id": self._realtime_model,
            "audio_format": "pcm_16000",
            "commit_strategy": self._commit_strategy,
            "include_language_detection": "true" if lang == "multi" else "false",
        }
        lang_code = self._language_code_param(language)
        if lang_code:
            params["language_code"] = lang_code

        url = f"{_ELEVENLABS_WS}?{urlencode(params)}"
        logger.info(
            "ElevenLabs live stream: model=%s commit=%s language=%s",
            self._realtime_model,
            self._commit_strategy,
            lang,
        )
        committed: list[str] = []
        interim = ""
        client_open = True

        async def safe_send(payload: dict[str, object]) -> None:
            nonlocal client_open
            if not client_open:
                return
            try:
                await websocket.send_json(payload)
            except WebSocketDisconnect:
                client_open = False

        async def send_transcript(*, is_final: bool, detected_language: str | None = None) -> None:
            parts = committed + ([interim] if interim else [])
            full = " ".join(parts).strip()
            payload: dict[str, object] = {"type": "transcript", "text": full, "is_final": is_final}
            if detected_language:
                payload["language"] = detected_language
            await safe_send(payload)

        async def handle_elevenlabs_message(raw: str) -> None:
            nonlocal interim
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                return

            message_type = data.get("message_type", "")
            if message_type == "session_started":
                return
            if message_type == "partial_transcript":
                interim = str(data.get("text", "")).strip()
                if interim:
                    await send_transcript(is_final=False)
                return
            if message_type in {"committed_transcript", "committed_transcript_with_timestamps"}:
                text = str(data.get("text", "")).strip()
                if text:
                    committed.append(text)
                interim = ""
                detected = data.get("language_code")
                await send_transcript(
                    is_final=True,
                    detected_language=str(detected) if detected else None,
                )
                return
            if message_type in {
                "error",
                "auth_error",
                "quota_exceeded",
                "commit_throttled",
                "unaccepted_terms",
                "rate_limited",
                "input_error",
                "transcriber_error",
            }:
                error = data.get("error") or message_type
                await safe_send({"type": "error", "message": str(error)})

        try:
            async with websockets.connect(
                url,
                extra_headers={"xi-api-key": api_key},
                open_timeout=20,
                ping_interval=15,
                ping_timeout=15,
            ) as el_ws:
                reader = asyncio.create_task(self._read_elevenlabs(el_ws, handle_elevenlabs_message))
                try:
                    while True:
                        message = await websocket.receive()
                        if message["type"] == "websocket.disconnect":
                            client_open = False
                            break
                        chunk = message.get("bytes")
                        if chunk:
                            await el_ws.send(
                                json.dumps(
                                    {
                                        "message_type": "input_audio_chunk",
                                        "audio_base_64": base64.b64encode(chunk).decode("ascii"),
                                        "commit": False,
                                        "sample_rate": 16000,
                                    }
                                )
                            )
                            continue
                        if message.get("text") == "stop":
                            await el_ws.send(
                                json.dumps(
                                    {
                                        "message_type": "input_audio_chunk",
                                        "audio_base_64": "",
                                        "commit": True,
                                        "sample_rate": 16000,
                                    }
                                )
                            )
                            # Allow ElevenLabs to return the final committed transcript.
                            await asyncio.sleep(1.0)
                            break
                finally:
                    client_open = False
                    reader.cancel()
                    with contextlib.suppress(asyncio.CancelledError, WebSocketDisconnect):
                        await reader
        except WebSocketDisconnect:
            logger.debug("ElevenLabs stream: client disconnected")
        except Exception as exc:
            logger.exception("ElevenLabs live stream failed")
            with contextlib.suppress(Exception):
                await websocket.send_json(
                    {"type": "error", "message": f"Live transcription failed: {exc}"}
                )
            raise

    @staticmethod
    async def _read_elevenlabs(el_ws, handler) -> None:
        async for message in el_ws:
            if isinstance(message, bytes):
                message = message.decode("utf-8", errors="ignore")
            await handler(str(message))
