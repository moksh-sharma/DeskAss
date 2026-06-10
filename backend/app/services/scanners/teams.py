"""Microsoft Teams scanner: version, cache size/health."""
from __future__ import annotations

import os

from app.services.scanners.base import safe_scan

LOCALAPPDATA = os.environ.get("LOCALAPPDATA", "")
APPDATA = os.environ.get("APPDATA", "")

# Classic Teams + new Teams (MSIX) cache locations.
_CACHE_DIRS = [
    os.path.join(APPDATA, "Microsoft", "Teams"),
    os.path.join(LOCALAPPDATA, "Packages", "MSTeams_8wekyb3d8bbwe", "LocalCache"),
]


def _dir_size(path: str) -> int:
    total = 0
    try:
        for root, _dirs, files in os.walk(path):
            for f in files:
                try:
                    total += os.path.getsize(os.path.join(root, f))
                except OSError:
                    continue
    except Exception:
        return total
    return total


def _version(inventory) -> str | None:
    if inventory is None:
        return None
    for ia in getattr(inventory, "installed_apps", []) or []:
        if "teams" in (getattr(ia, "name", "") or "").lower():
            v = getattr(ia, "version", None)
            if v:
                return v
    return None


@safe_scan("teams_diagnostics")
def scan(inventory=None) -> dict:
    cache_bytes = 0
    found_dir = None
    for d in _CACHE_DIRS:
        if os.path.isdir(d):
            cache_bytes += _dir_size(d)
            found_dir = found_dir or d
    cache_mb = round(cache_bytes / (1024 ** 2), 1) if cache_bytes else 0
    installed = found_dir is not None or bool(_version(inventory))
    return {
        "installed": installed,
        "version": _version(inventory),
        "cache_dir": found_dir,
        "cache_size_mb": cache_mb,
        # Large caches (>1 GB) often cause sign-in/loading problems.
        "cache_bloated": cache_mb >= 1024,
    }
