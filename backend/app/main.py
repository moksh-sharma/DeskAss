"""FastAPI application factory and entrypoint for Cache AI Assistant."""
from __future__ import annotations

import asyncio
import contextlib
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api.router import api_router
from app.core.config import get_settings
from app.core.container import get_container, init_container
from app.core.exceptions import register_exception_handlers
from app.core.logging import configure_logging, get_logger
from app.db.database import init_db

configure_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):  # type: ignore[no-untyped-def]
    settings = get_settings()
    configure_logging()
    logger.info("Starting %s v%s (%s)", settings.app_name, __version__, settings.app_env)
    # Ensure storage directories exist.
    settings.upload_path.mkdir(parents=True, exist_ok=True)
    init_db()
    init_container()
    # Start the continuous monitoring engine (background telemetry sampler).
    get_container().monitoring.start()
    # Warm the instant-read summary cache in the background (non-blocking).
    asyncio.create_task(asyncio.to_thread(get_container().machine_cache.refresh))
    logger.info(
        "Startup complete (deterministic engine, no AI model). STT=%s",
        get_container().speech.provider_label()
        if get_container().speech.is_configured
        else "not configured",
    )
    yield
    logger.info("Shutting down.")
    with contextlib.suppress(Exception):
        await get_container().monitoring.stop()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        description="Enterprise AI Desktop Troubleshooting Assistant - backend API.",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_origin_regex=r"^(app|file)://.*$",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    register_exception_handlers(app)
    app.include_router(api_router)
    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    settings = get_settings()
    uvicorn.run("app.main:app", host=settings.api_host, port=settings.api_port, reload=True)
