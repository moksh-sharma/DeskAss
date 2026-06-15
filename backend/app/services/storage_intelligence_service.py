"""Advanced Storage Intelligence Engine.

A WinDirStat / WizTree / TreeSize-class analyzer that understands exactly where
storage is consumed and what can be recovered safely.

Two entry points:

* :meth:`StorageIntelligenceService.quick_scan` - fast (seconds). Drive usage +
  known cleanup locations + recoverable space + cleanup recommendations +
  storage-health score. Used inline by the AI diagnosis ("why is my disk full?",
  "what can I delete?", "how much can I recover?").

* :meth:`StorageIntelligenceService.deep_scan` - heavy (on-demand, persisted).
  Full folder/file tree (top folders + top files), file-type distribution,
  per-application footprint, developer/AI-ML/cloud/Windows/recovery/log/VM
  analysis, duplicate detection (SHA-256), growth/prediction and change
  tracking. Powers the Storage dashboard.

Everything is defensive (a failing probe degrades to empty) and time-bounded so
a single huge directory can never hang the scan.
"""
from __future__ import annotations

import hashlib
import heapq
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Optional

import psutil

from app.core.logging import get_logger
from app.services.probes.base import IS_WINDOWS, as_list, ps_json, run_powershell

logger = get_logger(__name__)

GB = 1024 ** 3
MB = 1024 ** 2
KB = 1024


# --------------------------------------------------------------------------- #
#  Extension → category
# --------------------------------------------------------------------------- #
_EXT_CATEGORY: dict[str, str] = {}


def _reg(category: str, *exts: str) -> None:
    for e in exts:
        _EXT_CATEGORY[e] = category


_reg("Video", ".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm", ".m4v",
     ".mpg", ".mpeg", ".ts", ".m2ts", ".3gp")
_reg("Image", ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".tif", ".webp",
     ".heic", ".raw", ".psd", ".ai", ".svg", ".cr2", ".nef", ".dng")
_reg("Audio", ".mp3", ".wav", ".flac", ".aac", ".m4a", ".ogg", ".wma", ".aiff")
_reg("Archive", ".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz", ".cab", ".tgz")
_reg("Disk Image", ".iso", ".img", ".vhd", ".vhdx", ".vmdk", ".vdi", ".wim", ".esd")
_reg("Installer", ".exe", ".msi", ".msix", ".appx", ".dmg", ".pkg")
_reg("Document", ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".txt",
     ".csv", ".rtf", ".odt", ".epub", ".one")
_reg("Database", ".db", ".sqlite", ".sqlite3", ".mdf", ".bak", ".dmp")
_reg("Code / Dev", ".py", ".js", ".ts", ".tsx", ".jsx", ".java", ".c", ".cpp", ".cs",
     ".go", ".rs", ".rb", ".php", ".json", ".xml", ".html", ".css")
_reg("Log", ".log", ".etl", ".evtx")
_reg("Backup", ".bak", ".old", ".tmp")

_ARCHIVE_EXTS = {".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz", ".tgz", ".cab"}
_ISO_EXTS = {".iso", ".img", ".wim", ".esd"}
_INSTALLER_EXTS = {".exe", ".msi", ".msix", ".appx"}
_VIDEO_EXTS = {".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm", ".m4v", ".mpg", ".mpeg"}
_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".tif", ".webp", ".heic", ".raw", ".psd"}
_AUDIO_EXTS = {".mp3", ".wav", ".flac", ".aac", ".m4a", ".ogg", ".wma"}

# Directories never worth descending into (slow, noisy, or reparse loops).
_SKIP_DIR_NAMES = {
    "$recycle.bin", "system volume information", "$sysreset", "$windows.~bt",
    "$windows.~ws", "config.msi", "recovery",
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _round_gb(num_bytes: float | int | None, digits: int = 2) -> float | None:
    if num_bytes is None:
        return None
    return round(num_bytes / GB, digits)


def _round_mb(num_bytes: float | int | None, digits: int = 1) -> float | None:
    if num_bytes is None:
        return None
    return round(num_bytes / MB, digits)


def _expand(path: str) -> str:
    return os.path.expandvars(path)


def _exists(path: str) -> bool:
    try:
        return bool(path) and os.path.exists(path)
    except OSError:
        return False


# --------------------------------------------------------------------------- #
#  Bounded directory sizing
# --------------------------------------------------------------------------- #
def _dir_size(path: str, deadline: float | None = None) -> tuple[int, int]:
    """Return (total_bytes, file_count) for *path*, never raising.

    Honors a monotonic *deadline*; if exceeded, returns what was summed so far.
    Skips reparse points (junctions / OneDrive cloud placeholders) to avoid loops
    and surprise network/cloud fetches.
    """
    total = 0
    files = 0
    if not path or not os.path.isdir(path):
        return 0, 0
    stack = [path]
    while stack:
        if deadline is not None and time.monotonic() > deadline:
            break
        current = stack.pop()
        try:
            with os.scandir(current) as it:
                for entry in it:
                    try:
                        if entry.is_symlink():
                            continue
                        if entry.is_dir(follow_symlinks=False):
                            stack.append(entry.path)
                        else:
                            st = entry.stat(follow_symlinks=False)
                            total += st.st_size
                            files += 1
                    except (OSError, ValueError):
                        continue
        except (OSError, ValueError):
            continue
    return total, files


def _file_size(path: str) -> int:
    try:
        return os.path.getsize(path) if os.path.isfile(path) else 0
    except OSError:
        return 0


# --------------------------------------------------------------------------- #
#  Service
# --------------------------------------------------------------------------- #
class StorageIntelligenceService:
    """Storage discovery, footprint, duplicate and cleanup analysis."""

    # ---- common location resolution ---------------------------------- #
    @staticmethod
    def _user_dir(*parts: str) -> str:
        return os.path.join(os.path.expanduser("~"), *parts)

    # ================================================================== #
    #  DRIVES
    # ================================================================== #
    def _drives(self) -> list[dict]:
        drives: list[dict] = []
        for part in psutil.disk_partitions(all=False):
            if IS_WINDOWS and "cdrom" in (part.opts or ""):
                continue
            try:
                usage = psutil.disk_usage(part.mountpoint)
            except (PermissionError, OSError):
                continue
            drives.append({
                "drive": part.device.rstrip("\\"),
                "mountpoint": part.mountpoint,
                "file_system": part.fstype,
                "total_gb": _round_gb(usage.total),
                "used_gb": _round_gb(usage.used),
                "free_gb": _round_gb(usage.free),
                "used_pct": usage.percent,
            })
        return drives

    @staticmethod
    def _primary_drive(drives: list[dict]) -> dict | None:
        system = os.environ.get("SystemDrive", "C:").rstrip("\\").upper()
        for d in drives:
            if d["drive"].upper() == system:
                return d
        return drives[0] if drives else None

    # ================================================================== #
    #  CLEANUP LOCATIONS  (fast, known paths)
    # ================================================================== #
    def _cleanup_locations(self, deadline: float) -> list[dict]:
        win = os.environ.get("SystemRoot", r"C:\Windows")
        local = os.environ.get("LOCALAPPDATA", self._user_dir("AppData", "Local"))
        roaming = os.environ.get("APPDATA", self._user_dir("AppData", "Roaming"))
        system_drive = os.environ.get("SystemDrive", "C:")

        specs: list[tuple[str, str, str, bool]] = [
            # (key, label, path, safe)
            ("user_temp", "User temporary files", _expand("%TEMP%"), True),
            ("windows_temp", "Windows temp", os.path.join(win, "Temp"), True),
            ("windows_update", "Windows Update cache",
             os.path.join(win, "SoftwareDistribution", "Download"), True),
            ("delivery_optimization", "Delivery Optimization cache",
             os.path.join(win, "SoftwareDistribution", "DeliveryOptimization"), True),
            ("prefetch", "Prefetch", os.path.join(win, "Prefetch"), True),
            ("minidumps", "Crash minidumps", os.path.join(win, "Minidump"), True),
            ("crash_dumps", "App crash dumps",
             os.path.join(local, "CrashDumps"), True),
            ("thumbnail_cache", "Thumbnail / icon cache",
             os.path.join(local, "Microsoft", "Windows", "Explorer"), True),
            ("inetcache", "Windows internet cache",
             os.path.join(local, "Microsoft", "Windows", "INetCache"), True),
            ("chrome_cache", "Chrome cache",
             os.path.join(local, "Google", "Chrome", "User Data", "Default", "Cache"), True),
            ("edge_cache", "Edge cache",
             os.path.join(local, "Microsoft", "Edge", "User Data", "Default", "Cache"), True),
            ("firefox_cache", "Firefox cache",
             os.path.join(local, "Mozilla", "Firefox", "Profiles"), True),
            ("nuget_cache", "NuGet package cache",
             os.path.join(self._user_dir(".nuget", "packages")), False),
            ("pip_cache", "pip cache", os.path.join(local, "pip", "Cache"), True),
        ]
        results: list[dict] = []
        for key, label, path, safe in specs:
            if not _exists(path):
                continue
            size, count = _dir_size(path, deadline=deadline)
            if size <= 0:
                continue
            results.append({
                "key": key,
                "label": label,
                "path": path,
                "size_gb": _round_gb(size),
                "size_mb": _round_mb(size),
                "file_count": count,
                "safe_to_delete": safe,
            })

        # Recycle Bin (all drives) via Shell.Application size.
        rb = self._recycle_bin_size()
        if rb > 0:
            results.append({
                "key": "recycle_bin", "label": "Recycle Bin", "path": "Recycle Bin",
                "size_gb": _round_gb(rb), "size_mb": _round_mb(rb),
                "file_count": None, "safe_to_delete": True,
            })

        # MEMORY.DMP (full memory dump) - often several GB.
        memdmp = os.path.join(win, "MEMORY.DMP")
        if _exists(memdmp):
            size = _file_size(memdmp)
            if size > 0:
                results.append({
                    "key": "memory_dump", "label": "Full memory dump (MEMORY.DMP)",
                    "path": memdmp, "size_gb": _round_gb(size), "size_mb": _round_mb(size),
                    "file_count": 1, "safe_to_delete": True,
                })
        _ = system_drive, roaming
        results.sort(key=lambda r: r.get("size_gb") or 0, reverse=True)
        return results

    @staticmethod
    def _recycle_bin_size() -> int:
        if not IS_WINDOWS:
            return 0
        data = ps_json(
            "$ErrorActionPreference='SilentlyContinue';"
            "$s=(New-Object -ComObject Shell.Application).NameSpace(0xA);"
            "$sum=0; foreach($i in $s.Items()){ $sum += $i.Size }; $sum | ConvertTo-Json",
            timeout=20.0,
        )
        try:
            return int(data) if data is not None else 0
        except (TypeError, ValueError):
            return 0

    # ================================================================== #
    #  APPLICATION FOOTPRINT
    # ================================================================== #
    def _installed_apps(self) -> list[dict]:
        if not IS_WINDOWS:
            return []
        rows = as_list(ps_json(
            "$paths=@('HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\*',"
            "'HKLM:\\SOFTWARE\\WOW6432Node\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\*',"
            "'HKCU:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\*');"
            "Get-ItemProperty $paths -ErrorAction SilentlyContinue | "
            "Where-Object { $_.DisplayName } | "
            "Select-Object DisplayName,Publisher,DisplayVersion,InstallLocation,EstimatedSize | "
            "ConvertTo-Json -Compress",
            timeout=30.0,
        ))
        seen: set[str] = set()
        apps: list[dict] = []
        for r in rows:
            name = (r.get("DisplayName") or "").strip()
            if not name or name in seen:
                continue
            seen.add(name)
            apps.append({
                "name": name,
                "publisher": (r.get("Publisher") or "").strip() or None,
                "version": (r.get("DisplayVersion") or "").strip() or None,
                "install_location": (r.get("InstallLocation") or "").strip() or None,
                "estimated_size_gb": _round_gb((r.get("EstimatedSize") or 0) * KB)
                if r.get("EstimatedSize") else None,
            })
        return apps

    def _app_footprint(self, apps: list[dict], deadline: float) -> dict:
        """Per-application storage: install + caches/user-data for known heavy apps."""
        local = os.environ.get("LOCALAPPDATA", self._user_dir("AppData", "Local"))
        roaming = os.environ.get("APPDATA", self._user_dir("AppData", "Roaming"))

        # Extra storage buckets for well-known apps (cache, profile, etc.).
        extra_specs: dict[str, list[tuple[str, str]]] = {
            "Google Chrome": [
                ("Cache", os.path.join(local, "Google", "Chrome", "User Data", "Default", "Cache")),
                ("Profile data", os.path.join(local, "Google", "Chrome", "User Data")),
            ],
            "Microsoft Edge": [
                ("Cache", os.path.join(local, "Microsoft", "Edge", "User Data", "Default", "Cache")),
                ("Profile data", os.path.join(local, "Microsoft", "Edge", "User Data")),
            ],
            "Mozilla Firefox": [
                ("Profile data", os.path.join(roaming, "Mozilla", "Firefox")),
            ],
            "Slack": [("Data", os.path.join(roaming, "Slack"))],
            "Discord": [("Data", os.path.join(roaming, "discord")),
                        ("Cache", os.path.join(local, "Discord"))],
            "Spotify": [("Data", os.path.join(local, "Spotify"))],
            "Microsoft Teams": [("Data", os.path.join(roaming, "Microsoft", "Teams"))],
            "Zoom": [("Data", os.path.join(roaming, "Zoom"))],
        }

        results: list[dict] = []
        # Index installed apps by lowercase name for matching.
        for app in apps:
            name = app["name"]
            install = app.get("install_location")
            install_size = None
            if install and _exists(install) and time.monotonic() < deadline:
                size, _ = _dir_size(install, deadline=min(deadline, time.monotonic() + 8))
                install_size = size
            buckets: list[dict] = []
            total = install_size or 0
            for key, specs in extra_specs.items():
                if key.lower() in name.lower():
                    for label, path in specs:
                        if _exists(path) and time.monotonic() < deadline:
                            sz, _ = _dir_size(path, deadline=min(deadline, time.monotonic() + 8))
                            if sz > 0:
                                buckets.append({"label": label, "size_gb": _round_gb(sz)})
                                total += sz
                    break
            est = (total if total else None)
            results.append({
                "name": name,
                "publisher": app.get("publisher"),
                "version": app.get("version"),
                "install_location": install,
                "install_size_gb": _round_gb(install_size) if install_size else app.get("estimated_size_gb"),
                "buckets": buckets,
                "total_gb": _round_gb(est) if est else app.get("estimated_size_gb"),
            })

        # Docker (special: images/containers/volumes via the daemon).
        docker = self._docker_footprint()
        results.sort(key=lambda a: a.get("total_gb") or 0, reverse=True)
        return {
            "applications": results[:200],
            "total_apps": len(results),
            "docker": docker,
            "top": results[:15],
        }

    def _docker_footprint(self) -> dict | None:
        ok, out = run_powershell(
            "docker system df --format '{{.Type}}|{{.Size}}|{{.Reclaimable}}' 2>$null", timeout=15.0
        )
        if not ok or not out.strip():
            return None
        rows = []
        for line in out.splitlines():
            parts = line.split("|")
            if len(parts) >= 2:
                rows.append({"type": parts[0], "size": parts[1],
                             "reclaimable": parts[2] if len(parts) > 2 else None})
        return {"breakdown": rows} if rows else None

    # ================================================================== #
    #  DEVELOPER STORAGE
    # ================================================================== #
    def _developer_storage(self, deadline: float) -> dict:
        home = os.path.expanduser("~")
        local = os.environ.get("LOCALAPPDATA", self._user_dir("AppData", "Local"))
        report: dict[str, Any] = {}

        def size_of(path: str, budget: float = 10.0) -> dict | None:
            if not _exists(path):
                return None
            sz, cnt = _dir_size(path, deadline=min(deadline, time.monotonic() + budget))
            return {"path": path, "size_gb": _round_gb(sz), "file_count": cnt} if sz else None

        # Python
        report["python"] = {
            "pip_cache": size_of(os.path.join(local, "pip", "Cache")),
            "conda_pkgs": size_of(os.path.join(home, "anaconda3", "pkgs"))
            or size_of(os.path.join(home, "miniconda3", "pkgs")),
            "conda_envs": size_of(os.path.join(home, "anaconda3", "envs"))
            or size_of(os.path.join(home, "miniconda3", "envs")),
        }
        # Java
        report["java"] = {
            "maven_cache": size_of(os.path.join(home, ".m2", "repository")),
            "gradle_cache": size_of(os.path.join(home, ".gradle")),
        }
        # JS / Node
        report["node"] = {
            "npm_cache": size_of(os.path.join(local, "npm-cache"))
            or size_of(os.path.join(home, "AppData", "Roaming", "npm-cache")),
            "yarn_cache": size_of(os.path.join(local, "Yarn", "Cache")),
            "pnpm_store": size_of(os.path.join(local, "pnpm")),
        }
        # .NET
        report["dotnet"] = {
            "nuget_cache": size_of(os.path.join(home, ".nuget", "packages")),
        }
        # Editors
        report["vs_code"] = {
            "extensions": size_of(os.path.join(home, ".vscode", "extensions")),
            "cache": size_of(os.path.join(local, "Code", "Cache"))
            or size_of(os.path.join(home, "AppData", "Roaming", "Code", "Cache")),
        }
        report["cursor"] = {
            "extensions": size_of(os.path.join(home, ".cursor", "extensions")),
            "cache": size_of(os.path.join(local, "Cursor", "Cache"))
            or size_of(os.path.join(home, "AppData", "Roaming", "Cursor", "Cache")),
        }
        # Android
        report["android"] = {
            "sdk": size_of(os.path.join(local, "Android", "Sdk")),
            "gradle": size_of(os.path.join(home, ".gradle")),
            "avd": size_of(os.path.join(home, ".android", "avd")),
        }
        return report

    def _node_modules_scan(self, roots: list[str], deadline: float) -> dict:
        """Find node_modules folders under common project roots (bounded)."""
        found: list[dict] = []
        total = 0
        for root in roots:
            if not _exists(root) or time.monotonic() > deadline:
                continue
            for dirpath, dirnames, _files in os.walk(root):
                if time.monotonic() > deadline:
                    break
                if "node_modules" in dirnames:
                    nm = os.path.join(dirpath, "node_modules")
                    sz, _ = _dir_size(nm, deadline=min(deadline, time.monotonic() + 5))
                    if sz > 0:
                        found.append({"path": nm, "size_gb": _round_gb(sz)})
                        total += sz
                    # Don't descend into the node_modules we just measured.
                    dirnames[:] = [d for d in dirnames if d != "node_modules"]
                # Avoid descending into very deep trees.
                dirnames[:] = [d for d in dirnames if not d.startswith(".")][:50]
        found.sort(key=lambda f: f.get("size_gb") or 0, reverse=True)
        return {
            "projects": found[:100],
            "project_count": len(found),
            "total_gb": _round_gb(total),
        }

    def _git_repos(self, roots: list[str], deadline: float) -> dict:
        repos: list[dict] = []
        total = 0
        for root in roots:
            if not _exists(root) or time.monotonic() > deadline:
                continue
            for dirpath, dirnames, _files in os.walk(root):
                if time.monotonic() > deadline:
                    break
                if ".git" in dirnames:
                    sz, _ = _dir_size(dirpath, deadline=min(deadline, time.monotonic() + 5))
                    if sz > 0:
                        repos.append({"path": dirpath, "size_gb": _round_gb(sz)})
                        total += sz
                    dirnames[:] = []  # don't descend into a repo
                dirnames[:] = [d for d in dirnames if not d.startswith(".")][:50]
        repos.sort(key=lambda r: r.get("size_gb") or 0, reverse=True)
        return {"repositories": repos[:100], "repo_count": len(repos), "total_gb": _round_gb(total)}

    # ================================================================== #
    #  AI / ML MODELS
    # ================================================================== #
    def _ai_models(self, deadline: float) -> dict:
        home = os.path.expanduser("~")
        local = os.environ.get("LOCALAPPDATA", self._user_dir("AppData", "Local"))
        out: dict[str, Any] = {}
        total = 0

        def folder(path: str) -> dict | None:
            nonlocal total
            if not _exists(path):
                return None
            sz, cnt = _dir_size(path, deadline=min(deadline, time.monotonic() + 10))
            if sz <= 0:
                return None
            total += sz
            return {"path": path, "size_gb": _round_gb(sz), "file_count": cnt}

        # Ollama - parse the manifests/blobs for individual model sizes.
        out["ollama"] = self._ollama_models(deadline)
        if out["ollama"] and out["ollama"].get("total_gb"):
            total += int((out["ollama"]["total_gb"]) * GB)
        out["lm_studio"] = folder(os.path.join(home, ".cache", "lm-studio", "models")) \
            or folder(os.path.join(home, ".lmstudio", "models"))
        out["huggingface"] = folder(os.path.join(home, ".cache", "huggingface")) \
            or folder(os.path.join(local, "huggingface"))
        out["torch"] = folder(os.path.join(home, ".cache", "torch"))
        out["total_gb"] = _round_gb(total)
        return out

    def _ollama_models(self, deadline: float) -> dict | None:
        home = os.path.expanduser("~")
        base = os.environ.get("OLLAMA_MODELS") or os.path.join(home, ".ollama", "models")
        if not _exists(base):
            return None
        models: list[dict] = []
        manifest_root = os.path.join(base, "manifests")
        size, _ = _dir_size(base, deadline=min(deadline, time.monotonic() + 10))
        # Best-effort per-model names from manifests directory tree.
        if _exists(manifest_root):
            for dirpath, _dirs, files in os.walk(manifest_root):
                for f in files:
                    rel = os.path.relpath(os.path.join(dirpath, f), manifest_root)
                    parts = rel.replace("\\", "/").split("/")
                    if len(parts) >= 2:
                        models.append({"name": f"{parts[-2]}:{parts[-1]}"})
        return {
            "path": base,
            "total_gb": _round_gb(size),
            "models": models[:50],
            "model_count": len(models),
        }

    # ================================================================== #
    #  DOWNLOADS / ARCHIVES / MEDIA  (from the tree-walk results)
    # ================================================================== #
    def _downloads_analysis(self, deadline: float) -> dict:
        downloads = self._user_dir("Downloads")
        if not _exists(downloads):
            return {"available": False}
        now = time.time()
        categories: dict[str, dict] = {}
        large: list[tuple[int, str, float]] = []
        old_total = 0
        total = 0
        for dirpath, dirnames, files in os.walk(downloads):
            if time.monotonic() > deadline:
                break
            dirnames[:] = [d for d in dirnames if d.lower() not in _SKIP_DIR_NAMES]
            for f in files:
                p = os.path.join(dirpath, f)
                size = _file_size(p)
                if size <= 0:
                    continue
                total += size
                ext = os.path.splitext(f)[1].lower()
                cat = self._download_category(ext)
                c = categories.setdefault(cat, {"size": 0, "count": 0})
                c["size"] += size
                c["count"] += 1
                try:
                    age_days = (now - os.path.getmtime(p)) / 86400
                except OSError:
                    age_days = 0
                if age_days > 90:
                    old_total += size
                if size >= 50 * MB:
                    large.append((size, p, round(age_days)))
        large.sort(reverse=True)
        return {
            "available": True,
            "path": downloads,
            "total_gb": _round_gb(total),
            "categories": {
                k: {"size_gb": _round_gb(v["size"]), "count": v["count"]}
                for k, v in sorted(categories.items(), key=lambda kv: kv[1]["size"], reverse=True)
            },
            "large_downloads": [
                {"path": p, "size_gb": _round_gb(s), "age_days": age} for s, p, age in large[:30]
            ],
            "old_downloads_gb": _round_gb(old_total),
        }

    @staticmethod
    def _download_category(ext: str) -> str:
        if ext in _INSTALLER_EXTS:
            return "Installers"
        if ext in _ISO_EXTS:
            return "ISOs / Disk Images"
        if ext in _ARCHIVE_EXTS:
            return "Archives"
        if ext in _VIDEO_EXTS:
            return "Videos"
        if ext in _IMAGE_EXTS:
            return "Images"
        if ext in _AUDIO_EXTS:
            return "Audio"
        return _EXT_CATEGORY.get(ext, "Other")

    # ================================================================== #
    #  CLOUD STORAGE
    # ================================================================== #
    def _cloud_storage(self, deadline: float) -> list[dict]:
        home = os.path.expanduser("~")
        user_profile = os.environ.get("USERPROFILE", home)
        candidates = [
            ("OneDrive", os.environ.get("OneDrive") or os.path.join(user_profile, "OneDrive")),
            ("OneDrive (Commercial)", os.environ.get("OneDriveCommercial", "")),
            ("Google Drive", os.path.join(user_profile, "Google Drive")),
            ("Dropbox", os.path.join(user_profile, "Dropbox")),
            ("iCloud Drive", os.path.join(user_profile, "iCloudDrive")),
            ("Box", os.path.join(user_profile, "Box")),
        ]
        out: list[dict] = []
        seen: set[str] = set()
        for name, path in candidates:
            if not path or path in seen or not _exists(path):
                continue
            seen.add(path)
            sz, cnt = _dir_size(path, deadline=min(deadline, time.monotonic() + 12))
            out.append({
                "provider": name, "path": path,
                "local_size_gb": _round_gb(sz), "file_count": cnt,
            })
        return out

    # ================================================================== #
    #  WINDOWS STORAGE
    # ================================================================== #
    def _windows_storage(self, deadline: float) -> dict:
        win = os.environ.get("SystemRoot", r"C:\Windows")

        def folder(path: str, budget: float = 15.0) -> float | None:
            if not _exists(path):
                return None
            sz, _ = _dir_size(path, deadline=min(deadline, time.monotonic() + budget))
            return _round_gb(sz)

        winsxs = self._winsxs_analyze()
        return {
            "winsxs": winsxs,
            "windows_update_cache_gb": folder(os.path.join(win, "SoftwareDistribution", "Download")),
            "temp_gb": folder(os.path.join(win, "Temp")),
            "prefetch_gb": folder(os.path.join(win, "Prefetch")),
            "logs_gb": folder(os.path.join(win, "Logs")),
            "installer_cache_gb": folder(os.path.join(win, "Installer"), budget=10.0),
            "memory_dump_gb": _round_gb(_file_size(os.path.join(win, "MEMORY.DMP"))) or None,
        }

    def _winsxs_analyze(self) -> dict:
        """Component store size via DISM (authoritative, accounts for hard-links)."""
        if not IS_WINDOWS:
            return {"available": False}
        ok, out = run_powershell(
            "Dism.exe /Online /Cleanup-Image /AnalyzeComponentStore 2>$null", timeout=90.0
        )
        if not ok or not out:
            return {"available": False}
        info: dict[str, Any] = {"available": True}
        for line in out.splitlines():
            low = line.lower()
            if "actual size of component store" in low:
                info["actual_size"] = line.split(":")[-1].strip()
            elif "reclaimable packages" in low:
                info["reclaimable"] = line.split(":")[-1].strip()
            elif "component store cleanup recommended" in low:
                info["cleanup_recommended"] = "yes" in low
        return info

    # ================================================================== #
    #  RECOVERY / RESTORE
    # ================================================================== #
    def _recovery_analysis(self) -> dict:
        if not IS_WINDOWS:
            return {"available": False}
        # Shadow-copy storage (System Restore + VSS) via vssadmin.
        ok, out = run_powershell(
            "vssadmin list shadowstorage 2>$null", timeout=20.0
        )
        used = allocated = None
        if ok and out:
            for line in out.splitlines():
                low = line.lower().strip()
                if low.startswith("used shadow copy storage space"):
                    used = line.split(":", 1)[-1].strip()
                elif low.startswith("allocated shadow copy storage space"):
                    allocated = line.split(":", 1)[-1].strip()
        points = ps_json(
            "Get-ComputerRestorePoint -ErrorAction SilentlyContinue | "
            "Select-Object Description,@{N='When';E={$_.ConvertToDateTime($_.CreationTime)}} | "
            "ConvertTo-Json -Compress", timeout=20.0
        )
        restore_points = as_list(points)
        return {
            "available": True,
            "shadow_copy_used": used,
            "shadow_copy_allocated": allocated,
            "restore_point_count": len(restore_points),
            "restore_points": [
                {"description": r.get("Description"), "when": str(r.get("When"))}
                for r in restore_points[:10]
            ],
        }

    # ================================================================== #
    #  LOGS / VM / ENTERPRISE
    # ================================================================== #
    def _vm_storage(self, deadline: float) -> dict:
        home = os.path.expanduser("~")
        user_profile = os.environ.get("USERPROFILE", home)
        public = os.environ.get("PUBLIC", r"C:\Users\Public")

        def folder(path: str) -> dict | None:
            if not _exists(path):
                return None
            sz, _ = _dir_size(path, deadline=min(deadline, time.monotonic() + 12))
            return {"path": path, "size_gb": _round_gb(sz)} if sz else None

        wsl = self._wsl_distros()
        return {
            "virtualbox": folder(os.path.join(user_profile, "VirtualBox VMs")),
            "vmware": folder(os.path.join(user_profile, "Documents", "Virtual Machines")),
            "hyperv": folder(os.path.join(public, "Documents", "Hyper-V")),
            "wsl": wsl,
        }

    def _wsl_distros(self) -> dict | None:
        home = os.path.expanduser("~")
        base = os.path.join(os.environ.get("LOCALAPPDATA", self._user_dir("AppData", "Local")), "Packages")
        distros: list[dict] = []
        if _exists(base):
            try:
                for entry in os.scandir(base):
                    if entry.is_dir() and any(
                        k in entry.name.lower()
                        for k in ("ubuntu", "debian", "kali", "suse", "fedora", "wsl")
                    ):
                        vhdx = self._find_vhdx(entry.path)
                        if vhdx:
                            distros.append({
                                "name": entry.name.split("_")[0],
                                "path": vhdx,
                                "size_gb": _round_gb(_file_size(vhdx)),
                            })
            except OSError:
                pass
        _ = home
        return {"distros": distros, "count": len(distros)} if distros else None

    @staticmethod
    def _find_vhdx(root: str) -> str | None:
        try:
            for dirpath, _dirs, files in os.walk(root):
                for f in files:
                    if f.lower().endswith(".vhdx"):
                        return os.path.join(dirpath, f)
        except OSError:
            return None
        return None

    # ================================================================== #
    #  TREE WALK  (top folders/files, file-type dist, duplicate candidates)
    # ================================================================== #
    def _walk_tree(self, roots: list[str], deadline: float) -> dict:
        folder_min = 20 * MB        # only track folders >= 20 MB
        file_min = 20 * MB          # only track files >= 20 MB
        dup_min = 5 * MB            # duplicate candidates >= 5 MB

        big_folders: list[tuple[int, str, int, int]] = []   # (size, path, files, subdirs)
        big_files: list[tuple[int, str]] = []
        type_dist: dict[str, dict] = {}
        dup_candidates: dict[int, list[str]] = {}
        total_files = 0
        total_size = 0
        truncated = False

        def recurse(path: str) -> int:
            nonlocal total_files, total_size, truncated
            if time.monotonic() > deadline:
                truncated = True
                return 0
            size_here = 0
            file_count = 0
            subdir_count = 0
            try:
                with os.scandir(path) as it:
                    entries = list(it)
            except (OSError, ValueError):
                return 0
            for entry in entries:
                try:
                    if entry.is_symlink():
                        continue
                    if entry.is_dir(follow_symlinks=False):
                        if entry.name.lower() in _SKIP_DIR_NAMES:
                            continue
                        subdir_count += 1
                        size_here += recurse(entry.path)
                    else:
                        st = entry.stat(follow_symlinks=False)
                        sz = st.st_size
                        size_here += sz
                        file_count += 1
                        total_files += 1
                        total_size += sz
                        ext = os.path.splitext(entry.name)[1].lower()
                        cat = _EXT_CATEGORY.get(ext, "Other")
                        td = type_dist.setdefault(cat, {"size": 0, "count": 0})
                        td["size"] += sz
                        td["count"] += 1
                        if sz >= file_min:
                            big_files.append((sz, entry.path))
                        if sz >= dup_min:
                            dup_candidates.setdefault(sz, []).append(entry.path)
                except (OSError, ValueError):
                    continue
            if size_here >= folder_min:
                big_folders.append((size_here, path, file_count, subdir_count))
            return size_here

        for root in roots:
            if not _exists(root) or time.monotonic() > deadline:
                continue
            recurse(root)

        top_folders = heapq.nlargest(1000, big_folders, key=lambda t: t[0])
        top_files = heapq.nlargest(1000, big_files, key=lambda t: t[0])
        drive_total = total_size or 1
        return {
            "total_files_scanned": total_files,
            "total_size_gb": _round_gb(total_size),
            "truncated": truncated,
            "top_folders": [
                {"path": p, "size_gb": _round_gb(s), "file_count": fc, "subfolder_count": sd,
                 "pct_of_scanned": round(s / drive_total * 100, 2)}
                for s, p, fc, sd in top_folders
            ],
            "top_files": [
                {"path": p, "size_gb": _round_gb(s), "size_mb": _round_mb(s)}
                for s, p in top_files
            ],
            "file_type_distribution": [
                {"category": k, "size_gb": _round_gb(v["size"]), "count": v["count"],
                 "pct": round(v["size"] / drive_total * 100, 1)}
                for k, v in sorted(type_dist.items(), key=lambda kv: kv[1]["size"], reverse=True)
            ],
            "_dup_candidates": dup_candidates,
        }

    # ================================================================== #
    #  DUPLICATE DETECTION  (SHA-256, bounded)
    # ================================================================== #
    def _detect_duplicates(self, candidates: dict[int, list[str]], deadline: float,
                           max_groups: int = 400) -> dict:
        groups: list[dict] = []
        recoverable = 0
        # Only same-size groups with >1 file can be duplicates.
        size_groups = [(s, paths) for s, paths in candidates.items() if len(paths) > 1]
        size_groups.sort(reverse=True)  # biggest first
        examined = 0
        for size, paths in size_groups:
            if time.monotonic() > deadline or examined >= max_groups:
                break
            by_hash: dict[str, list[str]] = {}
            for p in paths:
                if time.monotonic() > deadline:
                    break
                h = self._hash_file(p)
                if h:
                    by_hash.setdefault(h, []).append(p)
            examined += 1
            for h, dup_paths in by_hash.items():
                if len(dup_paths) > 1:
                    wasted = size * (len(dup_paths) - 1)
                    recoverable += wasted
                    groups.append({
                        "size_gb": _round_gb(size),
                        "size_mb": _round_mb(size),
                        "copies": len(dup_paths),
                        "original": dup_paths[0],
                        "duplicates": dup_paths[1:],
                        "recoverable_gb": _round_gb(wasted),
                    })
        groups.sort(key=lambda g: g.get("recoverable_gb") or 0, reverse=True)
        return {
            "duplicate_groups": groups[:200],
            "group_count": len(groups),
            "recoverable_gb": _round_gb(recoverable),
        }

    @staticmethod
    def _hash_file(path: str, chunk: int = 1024 * 1024, cap: int = 512 * MB) -> str | None:
        try:
            h = hashlib.sha256()
            read = 0
            with open(path, "rb", buffering=0) as f:
                while read < cap:
                    block = f.read(chunk)
                    if not block:
                        break
                    h.update(block)
                    read += len(block)
            return h.hexdigest()
        except OSError:
            return None

    # ================================================================== #
    #  CLEANUP RECOMMENDATIONS + HEALTH SCORE
    # ================================================================== #
    @staticmethod
    def _cleanup_recommendations(cleanup_locations: list[dict], downloads: dict,
                                 duplicates: dict, docker: dict | None) -> dict:
        quick_wins: list[dict] = []
        safe: list[dict] = []
        advanced: list[dict] = []
        total = 0.0

        for loc in cleanup_locations:
            gb = loc.get("size_gb") or 0
            if gb < 0.05:
                continue
            entry = {"label": loc["label"], "recover_gb": gb, "path": loc.get("path")}
            total += gb
            if loc["key"] in ("user_temp", "windows_temp", "recycle_bin", "thumbnail_cache",
                              "crash_dumps", "minidumps", "inetcache"):
                quick_wins.append(entry)
            elif loc["key"] in ("windows_update", "delivery_optimization", "prefetch",
                                "memory_dump", "chrome_cache", "edge_cache", "firefox_cache",
                                "pip_cache"):
                safe.append(entry)
            else:
                advanced.append(entry)

        old_dl = (downloads or {}).get("old_downloads_gb") or 0
        if old_dl >= 0.5:
            advanced.append({"label": "Downloads older than 90 days",
                             "recover_gb": old_dl, "path": (downloads or {}).get("path")})
            total += old_dl

        dup_gb = (duplicates or {}).get("recoverable_gb") or 0
        if dup_gb >= 0.1:
            advanced.append({"label": "Duplicate files", "recover_gb": dup_gb, "path": None})
            total += dup_gb

        if docker and docker.get("breakdown"):
            advanced.append({"label": "Docker reclaimable (run 'docker system prune')",
                             "recover_gb": None, "path": None})

        for bucket in (quick_wins, safe, advanced):
            bucket.sort(key=lambda e: e.get("recover_gb") or 0, reverse=True)
        return {
            "quick_wins": quick_wins,
            "safe_cleanup": safe,
            "advanced_cleanup": advanced,
            "total_potential_gb": round(total, 2),
        }

    @staticmethod
    def _health_score(primary: dict | None, recoverable_gb: float, growth: dict | None) -> dict:
        usage_score = 100
        drive_score = 100
        cleanup_score = 100
        growth_score = 100
        notes: list[str] = []

        if primary:
            used = primary.get("used_pct") or 0
            free = primary.get("free_gb") or 0
            if used >= 95:
                usage_score = 20; notes.append(f"{primary['drive']} is {used}% full ({free} GB free).")
            elif used >= 90:
                usage_score = 40; notes.append(f"{primary['drive']} is {used}% full.")
            elif used >= 80:
                usage_score = 65; notes.append(f"{primary['drive']} is {used}% full.")
            if free is not None and free < 10:
                drive_score = 40; notes.append(f"Only {free} GB free on {primary['drive']}.")

        total_gb = (primary or {}).get("total_gb") or 0
        if total_gb and recoverable_gb:
            ratio = recoverable_gb / total_gb
            if ratio >= 0.15:
                cleanup_score = 50
                notes.append(f"~{round(recoverable_gb, 1)} GB is recoverable via cleanup.")
            elif ratio >= 0.07:
                cleanup_score = 70

        if growth and growth.get("days_until_full") is not None:
            days = growth["days_until_full"]
            if days is not None and days < 14:
                growth_score = 30; notes.append(f"At the current rate the drive fills in ~{days} days.")
            elif days is not None and days < 45:
                growth_score = 60

        scores = [usage_score, drive_score, cleanup_score, growth_score]
        overall = int(round(min(sum(scores) / len(scores), min(scores) + 15)))
        overall = max(0, min(100, overall))
        status = "Healthy" if overall >= 80 else "Warning" if overall >= 50 else "Critical"
        return {
            "overall_score": overall,
            "overall_status": status,
            "categories": {
                "storage_usage": usage_score,
                "drive_health": drive_score,
                "cleanup_opportunity": cleanup_score,
                "growth_trend": growth_score,
            },
            "notes": notes,
        }

    # ================================================================== #
    #  GROWTH + PREDICTION (needs history) + CHANGE TRACKING
    # ================================================================== #
    @staticmethod
    def growth_and_prediction(primary: dict | None, history: list[dict]) -> dict:
        """history = prior reports' light snapshots, oldest..newest (excludes current)."""
        result: dict[str, Any] = {"days_until_full": None, "growth_gb_per_day": None,
                                  "samples": len(history)}
        if not primary:
            return result
        free_now = primary.get("free_gb")
        if free_now is None or not history:
            return result
        # Find the oldest sample with a comparable free figure.
        prev = None
        for snap in history:
            if snap.get("primary_free_gb") is not None and snap.get("scanned_at"):
                prev = snap
                break
        if not prev:
            return result
        try:
            t_prev = datetime.fromisoformat(str(prev["scanned_at"]).replace("Z", "+00:00"))
            days = max(0.01, (_now() - t_prev).total_seconds() / 86400)
        except (ValueError, TypeError):
            return result
        used_delta = (prev["primary_free_gb"] - free_now)  # positive => filling up
        rate = used_delta / days
        result["growth_gb_per_day"] = round(rate, 3)
        if rate > 0.01 and free_now is not None:
            result["days_until_full"] = int(free_now / rate)
        return result

    @staticmethod
    def change_tracking(current_apps: list[str], current_top_files: list[str],
                        prev: dict | None) -> dict:
        if not prev:
            return {"available": False}
        prev_apps = set(prev.get("apps") or [])
        cur_apps = set(current_apps)
        prev_files = set(prev.get("top_files") or [])
        cur_files = set(current_top_files)
        return {
            "available": True,
            "new_applications": sorted(cur_apps - prev_apps)[:50],
            "removed_applications": sorted(prev_apps - cur_apps)[:50],
            "new_large_files": sorted(cur_files - prev_files)[:50],
            "removed_large_files": sorted(prev_files - cur_files)[:50],
        }

    # ================================================================== #
    #  PUBLIC: QUICK SCAN  (fast, for AI diagnosis)
    # ================================================================== #
    def quick_scan(self, time_budget: float = 12.0) -> dict[str, Any]:
        start = time.monotonic()
        deadline = start + time_budget
        drives = self._drives()
        primary = self._primary_drive(drives)
        cleanup_locations = self._cleanup_locations(deadline)
        recs = self._cleanup_recommendations(cleanup_locations, {}, {}, self._docker_footprint())
        health = self._health_score(primary, recs["total_potential_gb"], None)
        return {
            "generated_at": _now().isoformat(),
            "mode": "quick",
            "drives": drives,
            "primary_drive": primary,
            "cleanup_locations": cleanup_locations,
            "cleanup": recs,
            "health": health,
            "scan_duration_seconds": round(time.monotonic() - start, 1),
        }

    # ================================================================== #
    #  PUBLIC: DEEP SCAN  (heavy, on-demand, persisted)
    # ================================================================== #
    def deep_scan(
        self,
        *,
        tree_budget: float = 240.0,
        duplicate_budget: float = 60.0,
        target_drive: str | None = None,
        history: Optional[list[dict]] = None,
        previous_snapshot: Optional[dict] = None,
        progress: Optional[Callable[[str], None]] = None,
    ) -> dict[str, Any]:
        start = time.monotonic()
        history = history or []

        def step(msg: str) -> None:
            logger.info("Storage deep-scan: %s", msg)
            if progress:
                try:
                    progress(msg)
                except Exception:  # pragma: no cover
                    pass

        drives = self._drives()
        primary = self._primary_drive(drives)
        if target_drive:
            td = target_drive.upper()
            if not td.endswith(":"):
                td += ":"
            scan_drive = next((d for d in drives if (d.get("drive") or "").upper() == td), None)
            primary = scan_drive or primary
            walk_roots = [td + "\\"]
        else:
            walk_roots = [
                d["mountpoint"]
                for d in drives
                if d.get("mountpoint") and _exists(d["mountpoint"])
            ]
            if not walk_roots:
                walk_roots = [
                    (primary or {}).get("mountpoint")
                    or os.environ.get("SystemDrive", "C:") + "\\"
                ]

        # 1) Fast known locations.
        step("cleanup locations")
        cleanup_deadline = time.monotonic() + 25
        cleanup_locations = self._cleanup_locations(cleanup_deadline)

        # 2) Heavy filesystem walk (all fixed drives for full scan; one drive when targeted).
        step("walking filesystem tree")
        tree = self._walk_tree(walk_roots, time.monotonic() + tree_budget)
        dup_candidates = tree.pop("_dup_candidates", {})

        # 3) Installed apps + footprint.
        step("application footprint")
        apps = self._installed_apps()
        footprint = self._app_footprint(apps, time.monotonic() + 40)

        # 4) Developer / AI / cloud / windows / recovery / VM.
        project_roots = [
            os.path.expanduser("~"),
            os.path.join(os.environ.get("SystemDrive", "C:") + "\\", "dev"),
            os.path.join(os.environ.get("SystemDrive", "C:") + "\\", "projects"),
            "d:\\", "e:\\",
        ]
        step("developer storage")
        developer = self._developer_storage(time.monotonic() + 40)
        developer["node_modules"] = self._node_modules_scan(project_roots, time.monotonic() + 30)
        developer["git_repositories"] = self._git_repos(project_roots, time.monotonic() + 30)
        step("AI / ML models")
        ai_models = self._ai_models(time.monotonic() + 30)
        step("cloud storage")
        cloud = self._cloud_storage(time.monotonic() + 30)
        step("windows storage")
        windows = self._windows_storage(time.monotonic() + 40)
        step("recovery / restore")
        recovery = self._recovery_analysis()
        step("downloads / media / archives")
        downloads = self._downloads_analysis(time.monotonic() + 25)
        media = self._media_from_tree(tree)
        archives = self._archives_from_tree(tree)
        step("virtual machines")
        vm = self._vm_storage(time.monotonic() + 30)

        # 5) Duplicate detection.
        step("duplicate detection")
        duplicates = self._detect_duplicates(dup_candidates, time.monotonic() + duplicate_budget)

        # 6) Cleanup recommendations + growth/prediction + health.
        recs = self._cleanup_recommendations(
            cleanup_locations, downloads, duplicates, footprint.get("docker")
        )
        growth = self.growth_and_prediction(primary, history)
        health = self._health_score(primary, recs["total_potential_gb"], growth)

        # 7) Change tracking.
        top_file_paths = [f["path"] for f in tree.get("top_files", [])[:200]]
        changes = self.change_tracking(
            [a["name"] for a in apps], top_file_paths, previous_snapshot
        )

        report = {
            "generated_at": _now().isoformat(),
            "mode": "deep",
            "drives": drives,
            "primary_drive": primary,
            "scanned_drive": (primary or {}).get("drive") or target_drive,
            "scanned_drives": [d.get("drive") for d in drives if d.get("drive")],
            "walk_roots": walk_roots,
            "tree": tree,
            "file_type_distribution": tree.get("file_type_distribution", []),
            "application_footprint": footprint,
            "developer_storage": developer,
            "ai_models": ai_models,
            "downloads": downloads,
            "media": media,
            "archives": archives,
            "cloud_storage": cloud,
            "windows_storage": windows,
            "recovery": recovery,
            "vm_storage": vm,
            "duplicates": duplicates,
            "cleanup_locations": cleanup_locations,
            "cleanup": recs,
            "growth": growth,
            "change_tracking": changes,
            "health": health,
            # Light snapshot persisted for next run's change-tracking / prediction.
            "snapshot": {
                "scanned_at": _now().isoformat(),
                "primary_free_gb": (primary or {}).get("free_gb"),
                "primary_used_pct": (primary or {}).get("used_pct"),
                "apps": [a["name"] for a in apps],
                "top_files": top_file_paths,
            },
            "scan_duration_seconds": round(time.monotonic() - start, 1),
        }
        step(f"complete in {report['scan_duration_seconds']}s")
        return report

    # ---- media / archive views derived from the tree walk ------------ #
    def _media_from_tree(self, tree: dict) -> dict:
        files = tree.get("top_files", [])
        def by_ext(exts: set[str]) -> list[dict]:
            return [f for f in files if os.path.splitext(f["path"])[1].lower() in exts][:25]
        return {
            "largest_videos": by_ext(_VIDEO_EXTS),
            "largest_images": by_ext(_IMAGE_EXTS),
            "largest_audio": by_ext(_AUDIO_EXTS),
        }

    def _archives_from_tree(self, tree: dict) -> dict:
        now = time.time()
        files = tree.get("top_files", [])
        archives: list[dict] = []
        old90 = old180 = old365 = 0
        for f in files:
            ext = os.path.splitext(f["path"])[1].lower()
            if ext not in (_ARCHIVE_EXTS | _ISO_EXTS):
                continue
            try:
                age = (now - os.path.getmtime(f["path"])) / 86400
            except OSError:
                age = 0
            gb = f.get("size_gb") or 0
            if age > 365:
                old365 += gb
            elif age > 180:
                old180 += gb
            elif age > 90:
                old90 += gb
            archives.append({"path": f["path"], "size_gb": gb, "age_days": round(age)})
        return {
            "archives": archives[:30],
            "count": len(archives),
            "older_than_90d_gb": round(old90, 2),
            "older_than_180d_gb": round(old180, 2),
            "older_than_365d_gb": round(old365, 2),
        }
