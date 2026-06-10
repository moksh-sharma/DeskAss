"""Live machine inventory: installed software, running processes, and services.

This lets the investigation match ANY application or service the user names -
not just a hardcoded list. Results are cached with a short TTL so repeated
diagnoses don't repeatedly hit the registry / service manager.
"""
from __future__ import annotations

import sys
import threading
import time
from dataclasses import dataclass, field

import psutil

from app.core.logging import get_logger

logger = get_logger(__name__)

IS_WINDOWS = sys.platform == "win32"


@dataclass
class InstalledApp:
    name: str
    version: str | None = None
    publisher: str | None = None
    install_date: str | None = None


@dataclass
class ServiceEntry:
    name: str
    display_name: str
    status: str
    start_type: str


@dataclass
class InventorySnapshot:
    installed_apps: list[InstalledApp] = field(default_factory=list)
    process_names: set[str] = field(default_factory=set)  # lowercased exe names
    services: list[ServiceEntry] = field(default_factory=list)
    collected_at: float = 0.0


class SystemInventory:
    """Caches a snapshot of installed apps, processes and services."""

    def __init__(self, ttl_seconds: float = 60.0) -> None:
        self._ttl = ttl_seconds
        self._lock = threading.Lock()
        self._snapshot: InventorySnapshot | None = None

    # ------------------------------------------------------------------ #
    #  Public API
    # ------------------------------------------------------------------ #
    def snapshot(self, *, refresh: bool = False) -> InventorySnapshot:
        with self._lock:
            now = time.time()
            if (
                not refresh
                and self._snapshot is not None
                and (now - self._snapshot.collected_at) < self._ttl
            ):
                return self._snapshot
            snap = InventorySnapshot(
                installed_apps=self._collect_installed_apps(),
                process_names=self._collect_process_names(),
                services=self._collect_services(),
                collected_at=now,
            )
            self._snapshot = snap
            logger.info(
                "Inventory refreshed: %d apps, %d processes, %d services",
                len(snap.installed_apps), len(snap.process_names), len(snap.services),
            )
            return snap

    # ------------------------------------------------------------------ #
    #  Collectors (defensive - never raise)
    # ------------------------------------------------------------------ #
    def _collect_process_names(self) -> set[str]:
        names: set[str] = set()
        for p in psutil.process_iter(["name"]):
            try:
                n = (p.info.get("name") or "").strip().lower()
                if n:
                    names.add(n)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return names

    def _collect_services(self) -> list[ServiceEntry]:
        out: list[ServiceEntry] = []
        if not IS_WINDOWS or not hasattr(psutil, "win_service_iter"):
            return out
        try:
            for svc in psutil.win_service_iter():
                try:
                    info = svc.as_dict()
                    out.append(ServiceEntry(
                        name=str(info.get("name", "")),
                        display_name=str(info.get("display_name", "")),
                        status=str(info.get("status", "")),
                        start_type=str(info.get("start_type", "")),
                    ))
                except (psutil.NoSuchProcess, psutil.AccessDenied, Exception):
                    continue
        except Exception as exc:  # pragma: no cover - host dependent
            logger.debug("Service enumeration failed: %s", exc)
        return out

    def _collect_installed_apps(self) -> list[InstalledApp]:
        if not IS_WINDOWS:
            return []
        apps: dict[str, InstalledApp] = {}
        try:
            import winreg  # type: ignore

            roots = [
                (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
                (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
                (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
            ]
            for hive, path in roots:
                try:
                    with winreg.OpenKey(hive, path) as key:
                        count = winreg.QueryInfoKey(key)[0]
                        for i in range(count):
                            try:
                                sub = winreg.EnumKey(key, i)
                                with winreg.OpenKey(key, sub) as subkey:
                                    name = self._reg(subkey, "DisplayName")
                                    if not name:
                                        continue
                                    if name in apps:
                                        continue
                                    apps[name] = InstalledApp(
                                        name=name,
                                        version=self._reg(subkey, "DisplayVersion"),
                                        publisher=self._reg(subkey, "Publisher"),
                                        install_date=self._reg(subkey, "InstallDate"),
                                    )
                            except OSError:
                                continue
                except FileNotFoundError:
                    continue
        except Exception as exc:  # pragma: no cover
            logger.debug("Installed-app enumeration failed: %s", exc)
        return list(apps.values())

    @staticmethod
    def _reg(key, name: str):  # type: ignore[no-untyped-def]
        try:
            import winreg  # type: ignore

            value, _ = winreg.QueryValueEx(key, name)
            return str(value).strip() if value not in (None, "") else None
        except (FileNotFoundError, OSError):
            return None
