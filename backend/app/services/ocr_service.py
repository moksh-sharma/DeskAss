"""Screenshot OCR - Windows built-in OCR (primary) with optional Tesseract fallback."""
from __future__ import annotations

import asyncio
import re
import sys
from io import BytesIO

from app.core.config import Settings
from app.core.exceptions import FeatureUnavailableError
from app.core.logging import get_logger

logger = get_logger(__name__)

_ERROR_CODE_RE = re.compile(r"\b(0x[0-9A-Fa-f]{4,8})\b")
_NUMERIC_ERROR_RE = re.compile(r"\berror\s*[:#]?\s*(\d{3,5})\b", re.IGNORECASE)


class OcrService:
    """Extracts text and error codes from uploaded screenshots."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._available: bool | None = None
        self._backend: str | None = None

    def _probe_tesseract(self) -> bool:
        try:
            import pytesseract

            if self._settings.tesseract_cmd:
                pytesseract.pytesseract.tesseract_cmd = self._settings.tesseract_cmd
            pytesseract.get_tesseract_version()
            return True
        except Exception as exc:
            logger.debug("Tesseract unavailable: %s", exc)
            return False

    def _probe_windows(self) -> bool:
        if sys.platform != "win32":
            return False
        try:
            from winsdk.windows.media.ocr import OcrEngine

            engine = OcrEngine.try_create_from_user_profile_languages()
            if engine is not None:
                return True
            langs = list(OcrEngine.get_available_recognizer_languages())
            return len(langs) > 0
        except Exception as exc:
            logger.debug("Windows OCR unavailable: %s", exc)
            return False

    def is_available(self) -> bool:
        if self._available is not None:
            return self._available

        if self._probe_windows():
            self._backend = "windows"
            self._available = True
        elif self._probe_tesseract():
            self._backend = "tesseract"
            self._available = True
        else:
            logger.warning(
                "OCR unavailable - install a Windows OCR language pack or Tesseract."
            )
            self._backend = None
            self._available = False
        return self._available

    @property
    def backend_name(self) -> str:
        if self._backend is None:
            self.is_available()
        if self._backend == "windows":
            return "Windows OCR"
        if self._backend == "tesseract":
            return "Tesseract"
        return "unavailable"

    async def extract_text(self, image_bytes: bytes) -> tuple[str, list[str]]:
        """Return (full_text, detected_error_codes)."""
        if not self.is_available():
            raise FeatureUnavailableError(
                "OCR is not available. On Windows, install an OCR language pack "
                "(Settings → Time & language → Language). "
                "Alternatively install Tesseract and set TESSERACT_CMD in backend/.env."
            )

        image_bytes = self._preprocess_image(image_bytes)
        text = ""

        if self._backend == "windows":
            try:
                text = await self._windows_ocr(image_bytes)
            except Exception as exc:
                logger.warning("Windows OCR failed (%s), trying Tesseract fallback", exc)
                if self._probe_tesseract():
                    self._backend = "tesseract"
                    text = self._tesseract_ocr(image_bytes)
                else:
                    raise FeatureUnavailableError(f"OCR failed: {exc}") from exc
        else:
            text = self._tesseract_ocr(image_bytes)

        text = text.strip()
        return text, self._extract_error_codes(text)

    @staticmethod
    def _preprocess_image(image_bytes: bytes) -> bytes:
        """Upscale small screenshots and normalise format for better OCR."""
        from PIL import Image, ImageOps

        image = Image.open(BytesIO(image_bytes))
        image = ImageOps.exif_transpose(image)
        if image.mode not in ("RGB", "L"):
            image = image.convert("RGB")

        # Error dialogs are often small crops - upscale for clearer text.
        if max(image.size) < 900:
            scale = 2
            image = image.resize(
                (image.width * scale, image.height * scale),
                Image.Resampling.LANCZOS,
            )

        out = BytesIO()
        image.save(out, format="PNG")
        return out.getvalue()

    async def _windows_ocr(self, image_bytes: bytes) -> str:
        from winsdk.windows.graphics.imaging import BitmapDecoder
        from winsdk.windows.media.ocr import OcrEngine
        from winsdk.windows.storage.streams import DataWriter, InMemoryRandomAccessStream

        engine = OcrEngine.try_create_from_user_profile_languages()
        if engine is None:
            langs = list(OcrEngine.get_available_recognizer_languages())
            if not langs:
                raise FeatureUnavailableError(
                    "No Windows OCR language packs found. "
                    "Add English (or Hindi) OCR in Windows Settings → Language."
                )
            engine = OcrEngine.try_create_from_language(langs[0])

        stream = InMemoryRandomAccessStream()
        writer = DataWriter(stream)
        writer.write_bytes(image_bytes)
        await writer.store_async()
        await writer.flush_async()
        stream.seek(0)

        decoder = await BitmapDecoder.create_async(stream)
        bitmap = await decoder.get_software_bitmap_async()
        result = await engine.recognize_async(bitmap)
        return result.text or ""

    def _tesseract_ocr(self, image_bytes: bytes) -> str:
        import pytesseract
        from PIL import Image

        if self._settings.tesseract_cmd:
            pytesseract.pytesseract.tesseract_cmd = self._settings.tesseract_cmd

        try:
            image = Image.open(BytesIO(image_bytes))
            return pytesseract.image_to_string(image)
        except Exception as exc:
            raise FeatureUnavailableError(
                f"Tesseract OCR failed. Ensure Tesseract is installed and TESSERACT_CMD is set. ({exc})"
            ) from exc

    @staticmethod
    def _extract_error_codes(text: str) -> list[str]:
        codes: list[str] = []
        codes.extend(_ERROR_CODE_RE.findall(text))
        codes.extend(f"Error {m}" for m in _NUMERIC_ERROR_RE.findall(text))
        seen: set[str] = set()
        unique: list[str] = []
        for c in codes:
            key = c.lower()
            if key not in seen:
                seen.add(key)
                unique.append(c)
        return unique
