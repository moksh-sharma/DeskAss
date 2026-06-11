"""Domain exceptions and FastAPI exception handlers."""
from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.core.logging import get_logger

logger = get_logger(__name__)


class AppError(Exception):
    """Base class for application errors with an HTTP status code."""

    status_code: int = 500
    error_code: str = "internal_error"

    def __init__(self, message: str, *, status_code: int | None = None,
                 error_code: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        if status_code is not None:
            self.status_code = status_code
        if error_code is not None:
            self.error_code = error_code


class ExternalServiceError(AppError):
    """Raised when an upstream dependency (Ollama, Deepgram) fails."""

    status_code = 502
    error_code = "external_service_error"


class ResourceNotFoundError(AppError):
    status_code = 404
    error_code = "not_found"


class ValidationError(AppError):
    status_code = 422
    error_code = "validation_error"


class FeatureUnavailableError(AppError):
    """Raised when an optional capability (OCR, WMI) is not installed."""

    status_code = 503
    error_code = "feature_unavailable"


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error_handler(_: Request, exc: AppError) -> JSONResponse:
        logger.warning("AppError [%s]: %s", exc.error_code, exc.message)
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": exc.error_code, "message": exc.message}},
        )

    @app.exception_handler(Exception)
    async def _unhandled_handler(_: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled exception: %s", exc)
        return JSONResponse(
            status_code=500,
            content={"error": {"code": "internal_error", "message": "An unexpected error occurred."}},
        )
