"""Screenshot OCR endpoint."""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, UploadFile

from app.api.deps import container
from app.core.container import Container
from app.core.exceptions import ValidationError
from app.models.schemas import OcrResponse

router = APIRouter(prefix="/api/screenshot", tags=["screenshot"])


@router.post("/ocr", response_model=OcrResponse, summary="Extract text from a screenshot")
async def ocr(
    file: UploadFile = File(...),
    c: Container = Depends(container),
) -> OcrResponse:
    image = await file.read()
    if not image:
        raise ValidationError("Uploaded image is empty.")
    text, codes = c.ocr.extract_text(image)
    return OcrResponse(text=text, detected_error_codes=codes)
