"""Local cache engine (Layer 6: instant-read summaries).

Maintains small JSON summary files refreshed in the background from continuous
telemetry, so the UI and the AI query engine can answer common questions in
milliseconds without scanning or even hitting the database on the hot path.

Files (under ``<data>/cache/``):
  * ``current_snapshot.json``  - latest CPU/RAM/disk/GPU + top processes
  * ``health_summary.json``    - per-subsystem health derived from telemetry
  * ``machine_summary.json``   - trends, predictions, recent changes, memory

The refresh is best-effort and never raises into the monitoring loop.
"""
from __future__ import annotations

import contextlib
import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core.logging import get_logger
from app.services.telemetry_analytics_service import TelemetryAnalyticsService

logger = get_logger(__name__)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat() + "Z"


def _score(value: float | None, warn: float, crit: float, *, higher_is_worse: bool = True) -> tuple[int, str]:
    """Map a metric to a 0-100 health score + status label."""
    if value is None:
        return 100, "unknown"
    v = value if higher_is_worse else (100 - value)
    if v >= crit:
        return max(0, int(100 - v)), "critical"
    if v >= warn:
        return int(100 - v * 0.6), "warning"
    return max(60, int(100 - v * 0.4)), "good"


class MachineCacheService:
    """Builds and persists instant-read machine summaries from telemetry."""

    def __init__(self, cache_dir: Path, telemetry: TelemetryAnalyticsService | None = None) -> None:
        self._dir = cache_dir
        self._telemetry = telemetry or TelemetryAnalyticsService()
        self._lock = threading.Lock()
        self._dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ #
    #  Paths
    # ------------------------------------------------------------------ #
    @property
    def current_snapshot_path(self) -> Path:
        return self._dir / "current_snapshot.json"

    @property
    def health_summary_path(self) -> Path:
        return self._dir / "health_summary.json"

    @property
    def machine_summary_path(self) -> Path:
        return self._dir / "machine_summary.json"

    # ------------------------------------------------------------------ #
    #  Write (background refresh)
    # ------------------------------------------------------------------ #
    def refresh(self) -> None:
        """Rebuild all summary files from current telemetry. Never raises."""
        with self._lock:
            try:
                snapshot = self._build_snapshot()
                self._write(self.current_snapshot_path, snapshot)
                self._write(self.health_summary_path, self._build_health(snapshot))
                self._write(self.machine_summary_path, self._build_machine_summary())
            except Exception as exc:  # pragma: no cover - cache must never break the loop
                logger.debug("Machine cache refresh failed: %s", exc)

    def _build_snapshot(self) -> dict[str, Any]:
        snap = self._telemetry.latest_resource_snapshot(max_age_seconds=600) or {}
        return {"generated_at": _utc_now_iso(), **snap}

    def _build_health(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        cpu_score, cpu_status = _score(snapshot.get("cpu_pct"), 75, 90)
        ram_score, ram_status = _score(snapshot.get("mem_used_pct"), 80, 92)
        disk_score, disk_status = _score(snapshot.get("disk_used_pct"), 85, 95)
        predictions: dict[str, Any] = {}
        with contextlib.suppress(Exception):
            predictions = self._telemetry.predictions()
        categories = {
            "cpu": {"score": cpu_score, "status": cpu_status, "value_pct": snapshot.get("cpu_pct")},
            "ram": {"score": ram_score, "status": ram_status, "value_pct": snapshot.get("mem_used_pct")},
            "disk": {"score": disk_score, "status": disk_status, "free_gb": snapshot.get("disk_free_gb")},
        }
        overall = min(c["score"] for c in categories.values()) if categories else 100
        return {
            "generated_at": _utc_now_iso(),
            "overall_score": overall,
            "categories": categories,
            "predictions": predictions,
        }

    def _build_machine_summary(self) -> dict[str, Any]:
        ctx = self._telemetry.diagnosis_context()
        return {"generated_at": _utc_now_iso(), **ctx}

    @staticmethod
    def _write(path: Path, data: dict[str, Any]) -> None:
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, default=str, indent=2), encoding="utf-8")
        tmp.replace(path)

    # ------------------------------------------------------------------ #
    #  Read (instant)
    # ------------------------------------------------------------------ #
    def read(self, path: Path) -> dict[str, Any] | None:
        try:
            if path.exists():
                return json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:  # pragma: no cover
            logger.debug("Machine cache read failed (%s): %s", path.name, exc)
        return None

    def current_snapshot(self) -> dict[str, Any] | None:
        return self.read(self.current_snapshot_path)

    def health_summary(self) -> dict[str, Any] | None:
        return self.read(self.health_summary_path)

    def machine_summary(self) -> dict[str, Any] | None:
        return self.read(self.machine_summary_path)
