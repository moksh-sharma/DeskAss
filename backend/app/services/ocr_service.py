"""Screenshot OCR using Tesseract, with error-code extraction."""
from __future__ import annotations

import re
from io import BytesIO

from app.core.config import Settings
from app.core.exceptions import FeatureUnavailableError
from app.core.logging import get_logger

logger = get_logger(__name__)

# Matches Windows-style hex error codes (0x...) and HRESULT-like patterns.
_ERROR_CODE_RE = re.compile(r"\b(0x[0-9A-Fa-f]{4,8})\b")
# Matches common error number formats e.g. "Error 1603", "code 0x80070005".
_NUMERIC_ERROR_RE = re.compile(r"\berror\s*[:#]?\s*(\d{3,5})\b", re.IGNORECASE)


class OcrService:
    """Extracts text and error codes from uploaded screenshots."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._available: bool | None = None

    def _ensure_available(self):  # type: ignore[no-untyped-def]
        try:
            import pytesseract
            from PIL import Image  # noqa: F401
        except ImportError as exc:
            raise FeatureUnavailableError(
                "OCR dependencies (pytesseract/Pillow) are not installed."
            ) from exc

        if self._settings.tesseract_cmd:
            pytesseract.pytesseract.tesseract_cmd = self._settings.tesseract_cmd
        return pytesseract

    def is_available(self) -> bool:
        if self._available is not None:
            return self._available
        try:
            pytesseract = self._ensure_available()
            pytesseract.get_tesseract_version()
            self._available = True
        except Exception as exc:
            logger.warning("Tesseract OCR unavailable: %s", exc)
            self._available = False
        return self._available

    def extract_text(self, image_bytes: bytes) -> tuple[str, list[str]]:
        """Return (full_text, detected_error_codes)."""
        pytesseract = self._ensure_available()
        from PIL import Image

        try:
            image = Image.open(BytesIO(image_bytes))
        except Exception as exc:
            raise FeatureUnavailableError(f"Could not read uploaded image: {exc}") from exc

        try:
            text = pytesseract.image_to_string(image)
        except Exception as exc:
            raise FeatureUnavailableError(
                f"Tesseract OCR failed. Ensure Tesseract is installed and TESSERACT_CMD is set. ({exc})"
            ) from exc

        text = text.strip()
        codes = self._extract_error_codes(text)
        return text, codes

    @staticmethod
    def _extract_error_codes(text: str) -> list[str]:
        codes: list[str] = []
        codes.extend(_ERROR_CODE_RE.findall(text))
        codes.extend(f"Error {m}" for m in _NUMERIC_ERROR_RE.findall(text))
        # De-duplicate, preserve order.
        seen: set[str] = set()
        unique: list[str] = []
        for c in codes:
            if c.lower() not in seen:
                seen.add(c.lower())
                unique.append(c)
        return unique
