"""Windows health scanner: system-image integrity (DISM), component store,
Windows Recovery (WinRE) status and corruption detection.

These checks read the OS servicing state. The deep DISM/SFC repairs themselves
are destructive/slow and require elevation, so this scanner reports the current
*state* and a recommendation rather than running repairs.
"""
from __future__ import annotations

import ctypes

from app.services.scanners.base import run_powershell, safe_scan


def _is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def _image_health() -> dict:
    """DISM /Online /Cleanup-Image /CheckHealth - fast, reads stored health flag."""
    ok, out = run_powershell(
        "DISM /Online /Cleanup-Image /CheckHealth", timeout=90.0
    )
    text = (out or "").lower()
    if not ok and "elevat" in text or "administrator" in text:
        return {"state": "unknown", "requires_admin": True}
    if "no component store corruption" in text:
        return {"state": "healthy", "corruption_detected": False}
    if "repairable" in text:
        return {"state": "repairable", "corruption_detected": True}
    if "not repairable" in text or "nonrepairable" in text:
        return {"state": "not_repairable", "corruption_detected": True}
    if not ok:
        return {"state": "unknown", "error": (out or "")[:200]}
    return {"state": "unknown"}


def _component_store() -> dict:
    """Component-store size + whether a cleanup is recommended (DISM analyze)."""
    ok, out = run_powershell(
        "DISM /Online /Cleanup-Image /AnalyzeComponentStore", timeout=120.0
    )
    if not ok:
        text = (out or "").lower()
        if "elevat" in text or "administrator" in text:
            return {"requires_admin": True}
        return {"error": (out or "")[:200]}
    info: dict = {}
    for line in (out or "").splitlines():
        low = line.lower()
        if "actual size of component store" in low:
            info["actual_size"] = line.split(":", 1)[-1].strip()
        elif "shared with windows" in low:
            info["shared_with_windows"] = line.split(":", 1)[-1].strip()
        elif "component store cleanup recommended" in low:
            info["cleanup_recommended"] = "yes" in low
    return info


def _winre() -> dict:
    """Windows Recovery Environment status via reagentc /info."""
    ok, out = run_powershell("reagentc /info", timeout=20.0)
    if not ok:
        text = (out or "").lower()
        if "elevat" in text or "administrator" in text or "access" in text:
            return {"requires_admin": True}
        return {"error": (out or "")[:200]}
    text = (out or "").lower()
    enabled = None
    if "enabled" in text and "windows re status" in text:
        enabled = "windows re status" in text and "enabled" in text.split("windows re status", 1)[-1][:40]
    return {"recovery_enabled": enabled if enabled is not None else ("enabled" in text)}


@safe_scan("windows_health")
def scan() -> dict:
    admin = _is_admin()
    image = _image_health()
    store = _component_store() if admin else {"requires_admin": True}
    recovery = _winre()

    corruption = image.get("corruption_detected")
    needs_repair = image.get("state") in ("repairable", "not_repairable")

    notes: list[str] = []
    if needs_repair:
        notes.append(
            "System image reports corruption - run 'DISM /Online /Cleanup-Image "
            "/RestoreHealth' then 'sfc /scannow' (as Administrator)."
        )
    if store.get("cleanup_recommended"):
        notes.append("Component store cleanup recommended (DISM /Online /Cleanup-Image /StartComponentCleanup).")
    if recovery.get("recovery_enabled") is False:
        notes.append("Windows Recovery Environment (WinRE) is disabled.")

    return {
        "is_admin": admin,
        "image_health": image,
        "component_store": store,
        "recovery": recovery,
        "corruption_detected": bool(corruption),
        "sfc_recommendation": (
            "Run 'sfc /scannow' as Administrator to verify protected system files."
            if needs_repair or not admin else
            "No corruption detected; an SFC scan is optional."
        ),
        "notes": notes,
        "available": True,
    }
