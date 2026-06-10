"""Client for the external Vosk speech-to-text service."""
from __future__ import annotations

import httpx

from app.core.config import Settings
from app.core.exceptions import ExternalServiceError
from app.core.logging import get_logger

logger = get_logger(__name__)


class VoskService:
    """Proxies audio to the deployed Vosk transcription service."""

    def __init__(self, settings: Settings) -> None:
        self._base_url = settings.vosk_api_url.rstrip("/")
        self._timeout = settings.vosk_timeout_seconds

    async def health(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{self._base_url}/")
                if resp.status_code != 200:
                    return False
                try:
                    return resp.json().get("status") == "running"
                except ValueError:
                    return True
        except httpx.HTTPError as exc:
            logger.debug("Vosk health check failed: %s", exc)
            return False

    async def transcribe(self, audio_bytes: bytes, filename: str = "audio.wav",
                         content_type: str = "audio/wav") -> str:
        """Send audio to the Vosk /transcribe endpoint and return the text."""
        files = {"file": (filename, audio_bytes, content_type)}
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(f"{self._base_url}/transcribe", files=files)
                resp.raise_for_status()
                data = resp.json()
                return data.get("text", "")
        except httpx.TimeoutException as exc:
            raise ExternalServiceError("Vosk transcription timed out.") from exc
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text[:300] if exc.response is not None else str(exc)
            raise ExternalServiceError(f"Vosk returned an error: {detail}") from exc
        except httpx.HTTPError as exc:
            raise ExternalServiceError(
                f"Could not reach Vosk service at {self._base_url}: {exc}"
            ) from exc
