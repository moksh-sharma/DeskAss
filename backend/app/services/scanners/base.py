"""Shared helpers for the comprehensive machine-scanning engine.

Each scanner is an independent, defensive module that returns a plain ``dict``
for its section of the report. Helpers here wrap PowerShell/CIM access and never
raise - a failing query degrades gracefully to ``None``/empty values so one bad
probe can never break a full scan.
"""
from __future__ import annotations

import functools
import time
from typing import Any, Callable

from app.core.logging import get_logger

# Reuse the battle-tested PowerShell helpers from the probe layer.
from app.services.probes.base import (  # noqa: F401
    IS_WINDOWS,
    as_list,
    get_service,
    ps_json,
    run_powershell,
)

logger = get_logger(__name__)

GB = 1024 ** 3
MB = 1024 ** 2


# --------------------------------------------------------------------------- #
#  Formatting helpers
# --------------------------------------------------------------------------- #
def to_int(value: Any) -> int | None:
    try:
        if value is None or value == "":
            return None
        return int(float(value))
    except (TypeError, ValueError):
        return None


def to_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def bytes_to_gb(value: Any, digits: int = 1) -> float | None:
    n = to_float(value)
    return round(n / GB, digits) if n is not None else None


def bytes_to_mb(value: Any, digits: int = 0) -> float | None:
    n = to_float(value)
    return round(n / MB, digits) if n is not None else None


def pct(used: float | None, total: float | None, digits: int = 1) -> float | None:
    if not total:
        return None
    if used is None:
        return None
    return round((used / total) * 100, digits)


def first(value: Any) -> dict | None:
    """Return the first record from a CIM/JSON result (dict or list)."""
    items = as_list(value)
    return items[0] if items else None


# --------------------------------------------------------------------------- #
#  CIM / WMI access
# --------------------------------------------------------------------------- #
def cim(
    class_name: str,
    properties: str | None = None,
    *,
    namespace: str | None = None,
    where: str | None = None,
    timeout: float = 20.0,
) -> list[dict]:
    """Query a CIM class and return a list of records (possibly empty).

    ``properties`` is a comma-separated Select-Object list; omit for all props.
    """
    if not IS_WINDOWS:
        return []
    ns = f"-Namespace {namespace} " if namespace else ""
    flt = f'-Filter "{where}" ' if where else ""
    select = f"Select-Object {properties}" if properties else "Select-Object *"
    script = (
        f"Get-CimInstance {ns}-ClassName {class_name} {flt}-ErrorAction SilentlyContinue | "
        f"{select} | ConvertTo-Json -Compress -Depth 4"
    )
    return as_list(ps_json(script, timeout=timeout))


def cim_one(
    class_name: str,
    properties: str | None = None,
    *,
    namespace: str | None = None,
    where: str | None = None,
    timeout: float = 20.0,
) -> dict | None:
    return first(cim(class_name, properties, namespace=namespace, where=where, timeout=timeout))


# --------------------------------------------------------------------------- #
#  Defensive scanner wrapper
# --------------------------------------------------------------------------- #
def safe_scan(name: str) -> Callable:
    """Decorator: run a scanner, log timing, and never propagate exceptions.

    On failure the section returns ``{"error": "..."}`` so the rest of the scan
    continues and the report still has the key.
    """

    def decorator(fn: Callable[..., dict]) -> Callable[..., dict]:
        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> dict:
            start = time.perf_counter()
            try:
                result = fn(*args, **kwargs)
                elapsed = (time.perf_counter() - start) * 1000
                logger.info("Scanner '%s' completed in %.0f ms", name, elapsed)
                return result or {}
            except Exception as exc:  # pragma: no cover - host dependent
                logger.warning("Scanner '%s' failed: %s", name, exc, exc_info=True)
                return {"error": str(exc), "available": False}

        return wrapper

    return decorator
