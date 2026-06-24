"""Application health scanner — browser, Outlook, Teams diagnostics."""
from __future__ import annotations

from app.services.scanners import browser, outlook, teams
from app.services.scanners.base import safe_scan


@safe_scan("app_health")
def scan(inventory=None) -> dict:
    browsers = browser.scan(inventory) or {}
    ol = outlook.scan(inventory) or {}
    tm = teams.scan(inventory) or {}
    issues: list[str] = []
    for label, block in (("Outlook", ol), ("Teams", tm)):
        for prob in (block.get("issues") or block.get("problems") or []):
            issues.append(f"{label}: {prob}")
    return {
        "browsers": browsers,
        "outlook": ol,
        "teams": tm,
        "browser_count": len(browsers.get("browsers") or []),
        "issues": issues[:12],
        "available": True,
    }
