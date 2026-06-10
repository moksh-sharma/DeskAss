"""FastAPI dependency providers backed by the DI container."""
from __future__ import annotations

from app.core.container import Container, get_container


def container() -> Container:
    return get_container()
