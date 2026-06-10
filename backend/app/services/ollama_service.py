"""Async client for a local/remote Ollama LLM server."""
from __future__ import annotations

import time
from typing import Any, Optional

import httpx

from app.core.config import Settings
from app.core.exceptions import ExternalServiceError
from app.core.logging import get_logger

logger = get_logger(__name__)


class OllamaService:
    """Thin async wrapper over the Ollama HTTP API."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._base_url = settings.ollama_base_url.rstrip("/")
        self._timeout = settings.ollama_timeout_seconds

    @property
    def default_model(self) -> str:
        return self._settings.default_model

    async def health(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{self._base_url}/api/tags")
                return resp.status_code == 200
        except httpx.HTTPError as exc:
            logger.debug("Ollama health check failed: %s", exc)
            return False

    async def warmup(self) -> None:
        """Load the default model into memory so the first diagnosis is faster."""
        try:
            logger.info("Warming up Ollama model '%s'…", self.default_model)
            async with httpx.AsyncClient(timeout=120.0) as client:
                await client.post(
                    f"{self._base_url}/api/generate",
                    json={
                        "model": self.default_model,
                        "prompt": "ok",
                        "stream": False,
                        "keep_alive": "15m",
                    },
                )
            logger.info("Ollama model '%s' is loaded and ready.", self.default_model)
        except httpx.HTTPError as exc:
            logger.warning("Ollama warmup failed (diagnosis may be slow on first request): %s", exc)

    async def list_models(self) -> list[str]:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(f"{self._base_url}/api/tags")
                resp.raise_for_status()
                data = resp.json()
                return [m["name"] for m in data.get("models", [])]
        except httpx.HTTPError as exc:
            logger.warning("Failed to list Ollama models: %s", exc)
            return []

    async def generate(
        self,
        prompt: str,
        *,
        system: Optional[str] = None,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        json_mode: bool = False,
        options: Optional[dict[str, Any]] = None,
    ) -> str:
        """Generate a completion from a single prompt (non-streaming)."""
        merged_options: dict[str, Any] = {
            "temperature": temperature if temperature is not None else self._settings.ollama_temperature,
        }
        if options:
            merged_options.update(options)
        used_model = model or self.default_model
        payload: dict[str, Any] = {
            "model": used_model,
            "prompt": prompt,
            "stream": False,
            "keep_alive": "15m",
            "options": merged_options,
        }
        if system:
            payload["system"] = system
        if json_mode:
            payload["format"] = "json"

        try:
            t0 = time.monotonic()
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(f"{self._base_url}/api/generate", json=payload)
                resp.raise_for_status()
                data = resp.json()
                elapsed = time.monotonic() - t0
                logger.info(
                    "Ollama generate complete model=%s in %.1fs (%d eval tokens)",
                    used_model,
                    elapsed,
                    data.get("eval_count", 0),
                )
                return data.get("response", "")
        except httpx.TimeoutException as exc:
            models = await self.list_models()
            if used_model not in models and not any(m.startswith(used_model.split(":")[0]) for m in models):
                hint = f"Model '{used_model}' is not on the Ollama server. Run: ollama pull {used_model}"
            else:
                hint = (
                    f"The model '{used_model}' is available but inference exceeded {self._timeout:.0f}s. "
                    "The Ollama host may be under load or the model was loading into memory - try again. "
                    "Increase OLLAMA_TIMEOUT_SECONDS in backend/.env if this persists."
                )
            raise ExternalServiceError(f"Ollama request timed out after {self._timeout}s. {hint}") from exc
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text[:300] if exc.response is not None else str(exc)
            raise ExternalServiceError(f"Ollama returned an error: {detail}") from exc
        except httpx.HTTPError as exc:
            raise ExternalServiceError(
                f"Could not reach Ollama at {self._base_url}: {exc}"
            ) from exc

    async def chat(
        self,
        messages: list[dict[str, str]],
        *,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
    ) -> str:
        """Multi-turn chat completion (non-streaming)."""
        payload: dict[str, Any] = {
            "model": model or self.default_model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": temperature if temperature is not None else self._settings.ollama_temperature},
        }
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(f"{self._base_url}/api/chat", json=payload)
                resp.raise_for_status()
                data = resp.json()
                return data.get("message", {}).get("content", "")
        except httpx.HTTPError as exc:
            raise ExternalServiceError(f"Ollama chat failed: {exc}") from exc
