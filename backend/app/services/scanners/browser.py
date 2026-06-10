"""Browser scanner: detect installed browsers, versions and extensions."""
from __future__ import annotations

import json
import os

from app.services.scanners.base import safe_scan

LOCALAPPDATA = os.environ.get("LOCALAPPDATA", "")
APPDATA = os.environ.get("APPDATA", "")

# Chromium-family browsers: (display, user-data dir).
_CHROMIUM = {
    "Google Chrome": os.path.join(LOCALAPPDATA, "Google", "Chrome", "User Data"),
    "Microsoft Edge": os.path.join(LOCALAPPDATA, "Microsoft", "Edge", "User Data"),
    "Brave": os.path.join(LOCALAPPDATA, "BraveSoftware", "Brave-Browser", "User Data"),
}


def _chromium_extensions(user_data_dir: str) -> list[dict]:
    exts: list[dict] = []
    default = os.path.join(user_data_dir, "Default", "Extensions")
    try:
        if not os.path.isdir(default):
            return exts
        for ext_id in os.listdir(default):
            ext_path = os.path.join(default, ext_id)
            if not os.path.isdir(ext_path):
                continue
            versions = [d for d in os.listdir(ext_path) if os.path.isdir(os.path.join(ext_path, d))]
            if not versions:
                continue
            manifest_path = os.path.join(ext_path, versions[0], "manifest.json")
            name = ext_id
            try:
                with open(manifest_path, "r", encoding="utf-8") as f:
                    manifest = json.load(f)
                name = manifest.get("name", ext_id)
                if isinstance(name, str) and name.startswith("__MSG_"):
                    name = ext_id  # localized name, skip resolution
            except Exception:
                pass
            exts.append({"id": ext_id, "name": name, "version": versions[0]})
    except Exception:
        pass
    return exts


def _chromium_version(user_data_dir: str) -> str | None:
    # Version is in the parent install dir; read 'Last Version' if present.
    try:
        last = os.path.join(user_data_dir, "Last Version")
        if os.path.isfile(last):
            with open(last, "r", encoding="utf-8") as f:
                return f.read().strip()
    except Exception:
        pass
    return None


@safe_scan("browser_diagnostics")
def scan(inventory=None) -> dict:
    # Version from installed-app inventory if available.
    versions: dict[str, str] = {}
    if inventory is not None:
        for ia in getattr(inventory, "installed_apps", []) or []:
            n = (getattr(ia, "name", "") or "").lower()
            v = getattr(ia, "version", None)
            if not v:
                continue
            if "chrome" in n:
                versions["Google Chrome"] = v
            elif "edge" in n and "webview" not in n:
                versions["Microsoft Edge"] = v
            elif "brave" in n:
                versions["Brave"] = v
            elif "firefox" in n:
                versions["Mozilla Firefox"] = v

    browsers = []
    for name, user_data in _CHROMIUM.items():
        installed = os.path.isdir(user_data)
        if not installed and name not in versions:
            continue
        exts = _chromium_extensions(user_data) if installed else []
        browsers.append({
            "name": name,
            "installed": installed or name in versions,
            "version": versions.get(name) or _chromium_version(user_data),
            "engine": "Chromium",
            "extension_count": len(exts),
            "extensions": exts[:40],
        })

    # Firefox (presence via inventory; profile-based extension parsing is more complex).
    if "Mozilla Firefox" in versions or os.path.isdir(os.path.join(APPDATA, "Mozilla", "Firefox")):
        browsers.append({
            "name": "Mozilla Firefox",
            "installed": True,
            "version": versions.get("Mozilla Firefox"),
            "engine": "Gecko",
            "extension_count": None,
            "extensions": [],
        })

    return {
        "browsers": browsers,
        "browser_count": len(browsers),
        "total_extensions": sum(b.get("extension_count") or 0 for b in browsers),
    }
