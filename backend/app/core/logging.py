"""Centralised logging configuration."""
from __future__ import annotations

import contextlib
import logging
import sys
from pathlib import Path

from app.core.config import BASE_DIR, get_settings

_CONFIGURED = False


class _FlushingStreamHandler(logging.StreamHandler):
    def emit(self, record: logging.LogRecord) -> None:
        super().emit(record)
        self.flush()


class _FlushingFileHandler(logging.FileHandler):
    def emit(self, record: logging.LogRecord) -> None:
        super().emit(record)
        self.flush()


def _line_buffer_stdio() -> None:
    """Prefer line-buffered stdio when the interpreter supports reconfigure."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            with contextlib.suppress(Exception):
                reconfigure(line_buffering=True)


def configure_logging() -> None:
    """Configure root logging once for the whole application."""
    global _CONFIGURED
    if _CONFIGURED:
        return

    _line_buffer_stdio()

    settings = get_settings()
    log_dir = BASE_DIR / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    fmt = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    formatter = logging.Formatter(fmt)

    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()

    # stderr survives uvicorn --reload child processes on Windows better than stdout.
    stream = _FlushingStreamHandler(sys.stderr)
    stream.setFormatter(formatter)
    root.addHandler(stream)

    file_handler = _FlushingFileHandler(log_dir / "backend.log", encoding="utf-8")
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)

    # Reduce noise from third-party libraries.
    for noisy in ("httpx", "httpcore", "chromadb", "sentence_transformers", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    # Chroma telemetry logs ERROR on posthog API mismatch even when telemetry is off.
    logging.getLogger("chromadb.telemetry.product.posthog").setLevel(logging.CRITICAL)

    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    configure_logging()
    return logging.getLogger(name)
