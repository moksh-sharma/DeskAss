"""Serve extracted Microsoft Support visual guide assets."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

router = APIRouter(prefix="/api/visual-guides", tags=["visual-guides"])

_REPO_ROOT = Path(__file__).resolve().parents[4]
_GUIDES_DIR = _REPO_ROOT / "kb_visual_assets" / "guides"


@router.get("/{guide_id}/{filename}", summary="Get a visual guide step image")
async def get_guide_asset(guide_id: str, filename: str) -> FileResponse:
    if ".." in guide_id or ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="Invalid path")

    path = (_GUIDES_DIR / guide_id / filename).resolve()
    if not path.is_file() or _GUIDES_DIR.resolve() not in path.parents:
        raise HTTPException(status_code=404, detail="Asset not found")

    media = "image/png"
    if filename.lower().endswith(".jpg") or filename.lower().endswith(".jpeg"):
        media = "image/jpeg"
    elif filename.lower().endswith(".webp"):
        media = "image/webp"
    elif filename.lower().endswith(".svg"):
        media = "image/svg+xml"

    return FileResponse(path, media_type=media)
