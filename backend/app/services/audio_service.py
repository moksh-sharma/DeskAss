"""Normalise uploaded audio to 16 kHz mono PCM WAV for speech recognition."""
from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from app.core.logging import get_logger

logger = get_logger(__name__)

_WAV_MAGIC = b"RIFF"

# Speech-focused ffmpeg filter chain:
# - highpass removes rumble / fan noise
# - lowpass keeps speech band
# - soxr resampler (when available) for clean 16 kHz conversion
# - dynaudnorm evens out volume across the clip
_SPEECH_FILTER = (
    "highpass=f=80,"
    "lowpass=f=8000,"
    "aresample=resampler=soxr:osr=16000:dither_method=triangular,"
    "dynaudnorm=f=150:g=15:p=0.95"
)


class AudioService:
    """Prepare browser-captured audio for reliable transcription."""

    def ensure_wav(self, audio_bytes: bytes, filename: str, content_type: str) -> tuple[bytes, str, str]:
        """Return (bytes, filename, content_type) as normalised 16 kHz mono WAV."""
        ext = _guess_extension(filename, content_type, audio_bytes)
        converted = self._ffmpeg_convert(audio_bytes, ext)
        if converted is not None:
            return converted, "audio.wav", "audio/wav"

        if audio_bytes[:4] == _WAV_MAGIC:
            logger.info("ffmpeg unavailable - sending client WAV as-is.")
            return audio_bytes, "audio.wav", "audio/wav"

        logger.warning(
            "Could not convert %s (%s) to WAV - ffmpeg not available.",
            filename,
            content_type,
        )
        return audio_bytes, filename, content_type

    @staticmethod
    def _ffmpeg_convert(audio_bytes: bytes, input_ext: str) -> bytes | None:
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            return None

        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / f"input{input_ext}"
            dst = Path(tmp) / "output.wav"
            src.write_bytes(audio_bytes)

            # Try soxr resampler first; fall back to default if unsupported.
            for af in (_SPEECH_FILTER, _SPEECH_FILTER.replace("resampler=soxr:", "")):
                try:
                    subprocess.run(
                        [
                            ffmpeg,
                            "-y",
                            "-hide_banner",
                            "-loglevel",
                            "error",
                            "-i",
                            str(src),
                            "-af",
                            af,
                            "-ac",
                            "1",
                            "-ar",
                            "16000",
                            "-sample_fmt",
                            "s16",
                            "-f",
                            "wav",
                            str(dst),
                        ],
                        check=True,
                        capture_output=True,
                        timeout=60,
                    )
                    if dst.exists() and dst.stat().st_size > 44:
                        return dst.read_bytes()
                except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
                    logger.debug("ffmpeg attempt failed (%s): %s", af[:40], exc)
                    if dst.exists():
                        dst.unlink(missing_ok=True)
            logger.warning("All ffmpeg conversion attempts failed for %s", input_ext)
            return None


def _guess_extension(filename: str, content_type: str, data: bytes) -> str:
    if data[:4] == _WAV_MAGIC:
        return ".wav"
    name = (filename or "").lower()
    if name.endswith(".webm") or "webm" in content_type:
        return ".webm"
    if name.endswith(".ogg") or "ogg" in content_type:
        return ".ogg"
    if name.endswith(".mp4") or "mp4" in content_type:
        return ".mp4"
    if name.endswith(".wav"):
        return ".wav"
    return ".webm"
