"""Aggregates all API routers."""
from __future__ import annotations

from fastapi import APIRouter

from app.api.routes import (
    chat,
    diagnostics,
    health,
    knowledge,
    machine_scans,
    screenshot,
    sessions,
    visual_guides,
    voice,
)

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(diagnostics.router)
api_router.include_router(chat.router)
api_router.include_router(voice.router)
api_router.include_router(screenshot.router)
api_router.include_router(knowledge.router)
api_router.include_router(sessions.router)
api_router.include_router(machine_scans.router)
api_router.include_router(visual_guides.router)
