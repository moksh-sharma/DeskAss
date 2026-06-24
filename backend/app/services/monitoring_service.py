"""Continuous monitoring engine.

A lightweight background sampler that records system telemetry, detects changes
(software/devices/services/security), raises proactive alerts and anomalies, and
tracks boot history. All data lands in SQLite so the AI can answer *what happened,
when did it start, what changed, is it getting worse* from historical evidence.

Design (pragmatic, bounded):
* One master tick every ``monitoring_sample_seconds`` (default 30s) writes a
  telemetry row (tier ``critical``).
* Every ``monitoring_detailed_minutes`` the row is enriched (top processes, GPU,
  latency) and tagged ``detailed`` for longer retention.
* Every ``monitoring_deep_minutes`` we snapshot inventory and run change
  detection + boot history.
* Once per day we write a ``daily`` aggregate (kept forever) and prune old rows.
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import shutil
import socket
import subprocess
import sys
import time
from collections import deque
from datetime import datetime, timedelta, timezone
from typing import Any

import psutil

from app.core.config import Settings
from app.core.logging import get_logger
from app.db.database import session_scope
from app.db.models import MonitorEvent, MonitorInventorySnapshot, TelemetrySample

logger = get_logger(__name__)

IS_WINDOWS = sys.platform == "win32"
GB = 1024 ** 3
MB = 1024 ** 2


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class MonitoringService:
    """Background telemetry sampler + change/anomaly/alert detector."""

    def __init__(self, settings: Settings, cache: Any = None) -> None:
        self._s = settings
        self._cache = cache  # MachineCacheService | None - instant-read summaries
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()

        # Rolling windows for live anomaly detection (last ~30 min at 30s cadence).
        self._cpu_hist: deque[float] = deque(maxlen=60)
        self._mem_hist: deque[float] = deque(maxlen=60)

        # Counter caches for I/O rate computation.
        self._prev_disk: Any = None
        self._prev_net: Any = None
        self._prev_t: float | None = None

        # Debounce: event-key -> monotonic timestamp of last emit.
        self._last_emit: dict[str, float] = {}

        # Tier scheduling bookkeeping (monotonic seconds).
        self._last_detailed = 0.0
        self._last_deep = 0.0
        self._last_daily = 0.0
        self._last_prune = 0.0
        self._last_cache = 0.0
        self._last_process = 0.0
        self._boot_time = psutil.boot_time()

    # ================================================================== #
    #  Lifecycle
    # ================================================================== #
    def start(self) -> None:
        if not self._s.monitoring_enabled:
            logger.info("Continuous monitoring disabled (monitoring_enabled=false).")
            return
        if self._task and not self._task.done():
            return
        psutil.cpu_percent(None)  # prime the CPU counter
        self._task = asyncio.create_task(self._run(), name="monitoring-loop")
        logger.info(
            "Continuous monitoring started (cpu/ram=%ss disk/net=%ss processes=%ss deep=%smin).",
            self._s.monitoring_cpu_ram_seconds,
            self._s.monitoring_disk_net_seconds,
            self._s.monitoring_process_seconds,
            self._s.monitoring_deep_minutes,
        )

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
        logger.info("Continuous monitoring stopped.")

    # ================================================================== #
    #  Main loop
    # ================================================================== #
    async def _run(self) -> None:
        # Record a boot event on startup so history always has an anchor.
        await asyncio.to_thread(self._record_boot, startup=True)
        interval = max(5, int(self._s.monitoring_sample_seconds))
        while not self._stop.is_set():
            try:
                await asyncio.to_thread(self._tick)
            except Exception as exc:  # pragma: no cover - never let the loop die
                logger.warning("Monitoring tick failed: %s", exc)
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=interval)
            except asyncio.TimeoutError:
                pass

    def _tick(self) -> None:
        now = time.monotonic()
        detailed_due = (now - self._last_detailed) >= self._s.monitoring_detailed_minutes * 60
        deep_due = (now - self._last_deep) >= self._s.monitoring_deep_minutes * 60
        process_due = (now - self._last_process) >= self._s.monitoring_process_seconds
        daily_due = (now - self._last_daily) >= 86400
        prune_due = (now - self._last_prune) >= 3600

        sample = self._collect(detailed=detailed_due, processes=process_due)
        tier = "detailed" if detailed_due else "critical"
        if detailed_due:
            self._last_detailed = now
        if process_due:
            self._last_process = now
        self._persist_sample(sample, tier)
        self._check_thresholds(sample)
        self._check_anomalies(sample)

        if deep_due:
            self._last_deep = now
            with contextlib.suppress(Exception):
                self._deep_snapshot()
            self._record_boot()

        if daily_due:
            self._last_daily = now
            with contextlib.suppress(Exception):
                self._write_daily_aggregate()

        if prune_due:
            self._last_prune = now
            with contextlib.suppress(Exception):
                self._prune()

        cache_due = (now - self._last_cache) >= max(15, self._s.cache_refresh_seconds)
        if cache_due and self._cache is not None:
            self._last_cache = now
            with contextlib.suppress(Exception):
                self._cache.refresh()

    # ================================================================== #
    #  Telemetry collection
    # ================================================================== #
    def _collect(self, *, detailed: bool, processes: bool = False) -> dict[str, Any]:
        now_t = time.time()
        elapsed = (now_t - self._prev_t) if self._prev_t else None
        self._prev_t = now_t

        s: dict[str, Any] = {}
        with contextlib.suppress(Exception):
            s["cpu_pct"] = round(psutil.cpu_percent(None), 1)
        with contextlib.suppress(Exception):
            freq = psutil.cpu_freq()
            s["cpu_freq_mhz"] = round(freq.current, 0) if freq else None
        with contextlib.suppress(Exception):
            vm = psutil.virtual_memory()
            s["mem_used_pct"] = vm.percent
            s["mem_available_gb"] = round(vm.available / GB, 2)
        with contextlib.suppress(Exception):
            sw = psutil.swap_memory()
            s["pagefile_pct"] = sw.percent
        with contextlib.suppress(Exception):
            sysdrive = (psutil.disk_usage((psutil.disk_partitions()[0].mountpoint)
                        if not IS_WINDOWS else "C:\\"))
            s["disk_free_gb"] = round(sysdrive.free / GB, 2)
            s["disk_used_pct"] = sysdrive.percent

        # I/O rates from counter deltas.
        with contextlib.suppress(Exception):
            dio = psutil.disk_io_counters()
            if dio and self._prev_disk and elapsed and elapsed > 0:
                s["disk_read_mb_s"] = round(max(0, dio.read_bytes - self._prev_disk.read_bytes) / MB / elapsed, 2)
                s["disk_write_mb_s"] = round(max(0, dio.write_bytes - self._prev_disk.write_bytes) / MB / elapsed, 2)
            self._prev_disk = dio
        with contextlib.suppress(Exception):
            nio = psutil.net_io_counters()
            if nio and self._prev_net and elapsed and elapsed > 0:
                s["net_up_mb_s"] = round(max(0, nio.bytes_sent - self._prev_net.bytes_sent) / MB / elapsed, 3)
                s["net_down_mb_s"] = round(max(0, nio.bytes_recv - self._prev_net.bytes_recv) / MB / elapsed, 3)
            self._prev_net = nio
        with contextlib.suppress(Exception):
            s["process_count"] = len(psutil.pids())
        with contextlib.suppress(Exception):
            batt = psutil.sensors_battery()
            if batt is not None:
                s["battery_pct"] = round(batt.percent, 1)
        with contextlib.suppress(Exception):
            s["cpu_temp_c"] = self._cpu_temp()

        if detailed:
            with contextlib.suppress(Exception):
                s["latency_ms"] = self._latency()
            with contextlib.suppress(Exception):
                gpu = self._gpu()
                if gpu:
                    s.update(gpu)
        if detailed or processes:
            with contextlib.suppress(Exception):
                s["top_json"] = json.dumps(self._top_processes())
        return s

    @staticmethod
    def _cpu_temp() -> float | None:
        if not hasattr(psutil, "sensors_temperatures"):
            return None
        temps = psutil.sensors_temperatures()
        for entries in (temps or {}).values():
            for e in entries:
                if e.current and e.current > 0:
                    return round(e.current, 1)
        return None

    @staticmethod
    def _latency(host: str = "8.8.8.8", port: int = 53, timeout: float = 1.0) -> float | None:
        start = time.monotonic()
        try:
            with socket.create_connection((host, port), timeout=timeout):
                return round((time.monotonic() - start) * 1000, 1)
        except OSError:
            return None

    @staticmethod
    def _gpu() -> dict[str, Any] | None:
        exe = shutil.which("nvidia-smi")
        if not exe:
            return None
        try:
            out = subprocess.run(
                [exe, "--query-gpu=utilization.gpu,memory.used,memory.total,temperature.gpu",
                 "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=5,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            line = (out.stdout or "").strip().splitlines()
            if not line:
                return None
            parts = [p.strip() for p in line[0].split(",")]
            util, used, total, temp = (float(parts[0]), float(parts[1]), float(parts[2]), float(parts[3]))
            return {
                "gpu_pct": util,
                "gpu_mem_pct": round(used / total * 100, 1) if total else None,
                "gpu_temp_c": temp,
            }
        except (OSError, ValueError, IndexError, subprocess.TimeoutExpired):
            return None

    @staticmethod
    def _top_processes(top_n: int = 5) -> dict[str, Any]:
        # Prime per-process CPU counters, briefly wait, then read deltas so the
        # cache/history can answer "which app used the most CPU", not just memory.
        ncpu = psutil.cpu_count(logical=True) or 1
        for p in psutil.process_iter():
            with contextlib.suppress(psutil.NoSuchProcess, psutil.AccessDenied):
                p.cpu_percent(None)
        time.sleep(0.3)
        procs: list[dict] = []
        for p in psutil.process_iter(["pid", "name", "memory_info"]):
            with contextlib.suppress(psutil.NoSuchProcess, psutil.AccessDenied):
                mem = p.info["memory_info"].rss / MB if p.info.get("memory_info") else 0.0
                cpu = p.cpu_percent(None) / ncpu
                procs.append({"pid": p.info["pid"], "name": p.info.get("name") or "?",
                              "mem_mb": round(mem, 1), "cpu_pct": round(cpu, 1)})
        by_mem = sorted(procs, key=lambda x: x["mem_mb"], reverse=True)[:top_n]
        by_cpu = sorted(procs, key=lambda x: x["cpu_pct"], reverse=True)[:top_n]
        return {"top_mem": by_mem, "top_cpu": by_cpu}

    # ================================================================== #
    #  Persistence
    # ================================================================== #
    def _persist_sample(self, s: dict[str, Any], tier: str) -> None:
        cpu = s.get("cpu_pct") or 0.0
        mem = s.get("mem_used_pct") or 0.0
        self._cpu_hist.append(cpu)
        self._mem_hist.append(mem)
        with session_scope() as db:
            db.add(TelemetrySample(
                ts=_utc_now(),
                tier=tier,
                cpu_pct=cpu,
                cpu_freq_mhz=s.get("cpu_freq_mhz"),
                cpu_temp_c=s.get("cpu_temp_c"),
                mem_used_pct=mem,
                mem_available_gb=s.get("mem_available_gb") or 0.0,
                pagefile_pct=s.get("pagefile_pct"),
                disk_free_gb=s.get("disk_free_gb") or 0.0,
                disk_used_pct=s.get("disk_used_pct") or 0.0,
                disk_read_mb_s=s.get("disk_read_mb_s"),
                disk_write_mb_s=s.get("disk_write_mb_s"),
                net_up_mb_s=s.get("net_up_mb_s"),
                net_down_mb_s=s.get("net_down_mb_s"),
                latency_ms=s.get("latency_ms"),
                gpu_pct=s.get("gpu_pct"),
                gpu_mem_pct=s.get("gpu_mem_pct"),
                gpu_temp_c=s.get("gpu_temp_c"),
                battery_pct=s.get("battery_pct"),
                process_count=s.get("process_count"),
                top_json=s.get("top_json"),
            ))

    def _emit(self, category: str, severity: str, title: str,
              detail: str | None = None, meta: dict | None = None,
              *, debounce_key: str | None = None, debounce_s: float = 3600) -> None:
        if debounce_key:
            last = self._last_emit.get(debounce_key)
            now = time.monotonic()
            if last is not None and (now - last) < debounce_s:
                return
            self._last_emit[debounce_key] = now
        with session_scope() as db:
            db.add(MonitorEvent(
                ts=_utc_now(), category=category, severity=severity, title=title,
                detail=detail, meta_json=json.dumps(meta, default=str) if meta else None,
            ))
        logger.info("Monitor event [%s/%s] %s", category, severity, title)

    # ================================================================== #
    #  Threshold alerts + anomaly detection
    # ================================================================== #
    def _check_thresholds(self, s: dict[str, Any]) -> None:
        disk_used = s.get("disk_used_pct") or 0
        mem = s.get("mem_used_pct") or 0
        cpu = s.get("cpu_pct") or 0
        batt = s.get("battery_pct")

        if disk_used >= 90:
            self._emit("alert", "critical" if disk_used >= 95 else "warning",
                       f"Low disk space ({round(100 - disk_used)}% free)",
                       f"System drive is {disk_used}% full ({s.get('disk_free_gb')} GB free).",
                       debounce_key="disk_low")
        if mem >= 95:
            self._emit("alert", "critical", f"Memory critically high ({mem}%)",
                       f"RAM usage reached {mem}% ({s.get('mem_available_gb')} GB free).",
                       debounce_key="mem_high")
        # CPU must be high two ticks in a row to count (avoid transient spikes).
        if cpu >= 95 and len(self._cpu_hist) >= 2 and self._cpu_hist[-2] >= 90:
            self._emit("alert", "warning", f"Sustained high CPU ({cpu}%)",
                       "CPU has been near 100% across consecutive samples.",
                       debounce_key="cpu_high")
        if batt is not None and batt <= 10:
            self._emit("alert", "warning", f"Battery low ({batt}%)",
                       "Battery charge is very low.", debounce_key="batt_low")

    def _check_anomalies(self, s: dict[str, Any]) -> None:
        self._anomaly("cpu", s.get("cpu_pct") or 0, self._cpu_hist, floor=70)
        self._anomaly("memory", s.get("mem_used_pct") or 0, self._mem_hist, floor=75)

    def _anomaly(self, metric: str, value: float, hist: deque[float], floor: float) -> None:
        if len(hist) < 20:
            return
        data = list(hist)[:-1]  # exclude current
        mean = sum(data) / len(data)
        var = sum((x - mean) ** 2 for x in data) / len(data)
        std = var ** 0.5
        if std < 3:
            return
        if value >= floor and value > mean + 3 * std:
            self._emit("anomaly", "warning",
                       f"Abnormal {metric} usage ({round(value)}%)",
                       f"{metric.title()} is well above its recent baseline "
                       f"(~{round(mean)}% ± {round(std)}%).",
                       debounce_key=f"anomaly_{metric}", debounce_s=1800)

    # ================================================================== #
    #  Boot history
    # ================================================================== #
    def _record_boot(self, *, startup: bool = False) -> None:
        boot = psutil.boot_time()
        last = self._latest_snapshot("boot")
        last_boot = (last or {}).get("boot_time") if last else None
        changed = last_boot is None or abs(boot - float(last_boot)) > 5
        if changed:
            boot_dt = datetime.fromtimestamp(boot, tz=timezone.utc).replace(tzinfo=None)
            self._save_snapshot("boot", {"boot_time": boot, "boot_at": boot_dt.isoformat()})
            if not startup or last_boot is not None:
                self._emit("boot", "info", "System booted",
                           f"Windows started at {boot_dt.isoformat()}Z.",
                           meta={"boot_at": boot_dt.isoformat()})

    # ================================================================== #
    #  Deep snapshot + change detection
    # ================================================================== #
    def _deep_snapshot(self) -> None:
        self._diff_apps()
        self._diff_services()
        self._diff_startup()
        self._diff_security()

    def _diff_apps(self) -> None:
        current = self._installed_apps()
        if not current:
            return
        prev = self._latest_snapshot("apps")
        self._save_snapshot("apps", current)
        if not prev:
            return
        prev_map = {a["name"]: a.get("version") for a in prev.get("items", [])}
        cur_map = {a["name"]: a.get("version") for a in current["items"]}
        for name, ver in cur_map.items():
            if name not in prev_map:
                self._emit("change", "info", f"Software installed: {name}",
                           f"Version {ver}" if ver else None, meta={"app": name, "version": ver})
            elif prev_map[name] != ver and ver:
                self._emit("change", "info", f"Application updated: {name}",
                           f"{prev_map[name]} → {ver}", meta={"app": name, "from": prev_map[name], "to": ver})
        for name in prev_map:
            if name not in cur_map:
                self._emit("change", "info", f"Software removed: {name}", meta={"app": name})

    def _diff_services(self) -> None:
        current = self._auto_services()
        if not current:
            return
        prev = self._latest_snapshot("services")
        self._save_snapshot("services", current)
        if not prev:
            return
        prev_map = {x["name"]: x["status"] for x in prev.get("items", [])}
        cur_map = {x["name"]: x["status"] for x in current["items"]}
        for name, status in cur_map.items():
            old = prev_map.get(name)
            if old == "running" and status != "running":
                self._emit("service", "warning", f"Service stopped: {name}",
                           f"Auto-start service '{name}' is no longer running ({status}).",
                           meta={"service": name, "status": status})

    def _diff_startup(self) -> None:
        current = self._startup_entries()
        prev = self._latest_snapshot("startup")
        self._save_snapshot("startup", current)
        if not prev:
            return
        prev_set = set(prev.get("items", []))
        cur_set = set(current["items"])
        for name in cur_set - prev_set:
            self._emit("change", "info", f"New startup entry: {name}",
                       meta={"startup": name})
        for name in prev_set - cur_set:
            self._emit("change", "info", f"Startup entry removed: {name}",
                       meta={"startup": name})

    def _diff_security(self) -> None:
        current = self._security_state()
        if not current.get("items"):
            return
        prev = self._latest_snapshot("security")
        self._save_snapshot("security", current)
        if not prev:
            return
        old = prev.get("items", {})
        new = current["items"]
        for key, label in (("defender_av", "Antivirus"), ("defender_rtp", "Real-time protection"),
                           ("firewall", "Firewall")):
            if key in old and key in new and old[key] != new[key]:
                sev = "critical" if not new[key] else "info"
                self._emit("security", sev, f"{label} {'disabled' if not new[key] else 'enabled'}",
                           f"{label} changed from {old[key]} to {new[key]}.",
                           meta={key: new[key]})

    # ---- snapshot collectors (Windows-aware, defensive) -------------- #
    def _installed_apps(self) -> dict[str, Any]:
        items: list[dict] = []
        if IS_WINDOWS:
            with contextlib.suppress(Exception):
                import winreg  # type: ignore
                roots = [
                    (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
                    (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
                    (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
                ]
                seen: set[str] = set()
                for hive, path in roots:
                    with contextlib.suppress(OSError):
                        with winreg.OpenKey(hive, path) as key:
                            for i in range(winreg.QueryInfoKey(key)[0]):
                                with contextlib.suppress(OSError):
                                    sub = winreg.EnumKey(key, i)
                                    with winreg.OpenKey(key, sub) as sk:
                                        name = self._reg(sk, "DisplayName")
                                        if not name or name in seen:
                                            continue
                                        seen.add(name)
                                        items.append({"name": name, "version": self._reg(sk, "DisplayVersion")})
        return {"items": items}

    @staticmethod
    def _reg(key, name: str):  # type: ignore[no-untyped-def]
        with contextlib.suppress(Exception):
            import winreg  # type: ignore
            value, _ = winreg.QueryValueEx(key, name)
            return str(value).strip() if value not in (None, "") else None
        return None

    @staticmethod
    def _auto_services() -> dict[str, Any]:
        items: list[dict] = []
        if IS_WINDOWS and hasattr(psutil, "win_service_iter"):
            with contextlib.suppress(Exception):
                for svc in psutil.win_service_iter():
                    with contextlib.suppress(Exception):
                        info = svc.as_dict()
                        if "auto" in str(info.get("start_type", "")).lower():
                            items.append({"name": info.get("name"), "status": info.get("status")})
        return {"items": items}

    def _startup_entries(self) -> dict[str, Any]:
        items: list[str] = []
        if IS_WINDOWS:
            with contextlib.suppress(Exception):
                import winreg  # type: ignore
                keys = [
                    (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run"),
                    (winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\Run"),
                ]
                for hive, path in keys:
                    with contextlib.suppress(OSError):
                        with winreg.OpenKey(hive, path) as key:
                            idx = 0
                            while True:
                                try:
                                    name, _v, _t = winreg.EnumValue(key, idx)
                                    items.append(name)
                                    idx += 1
                                except OSError:
                                    break
        return {"items": items}

    @staticmethod
    def _security_state() -> dict[str, Any]:
        items: dict[str, Any] = {}
        if not IS_WINDOWS:
            return {"items": items}
        with contextlib.suppress(Exception):
            out = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command",
                 "$s=Get-MpComputerStatus -ErrorAction SilentlyContinue;"
                 "$f=(Get-NetFirewallProfile -ErrorAction SilentlyContinue | Where-Object {$_.Enabled -eq $true}).Count;"
                 "[pscustomobject]@{av=$s.AntivirusEnabled; rtp=$s.RealTimeProtectionEnabled; fw=($f -gt 0)} | ConvertTo-Json -Compress"],
                capture_output=True, text=True, timeout=20,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            data = json.loads((out.stdout or "").strip() or "{}")
            items = {
                "defender_av": bool(data.get("av")),
                "defender_rtp": bool(data.get("rtp")),
                "firewall": bool(data.get("fw")),
            }
        return {"items": items}

    # ---- snapshot store helpers -------------------------------------- #
    def _save_snapshot(self, kind: str, data: dict[str, Any]) -> None:
        with session_scope() as db:
            db.add(MonitorInventorySnapshot(ts=_utc_now(), kind=kind, data_json=json.dumps(data, default=str)))

    def _latest_snapshot(self, kind: str) -> dict[str, Any] | None:
        from sqlalchemy import select
        with session_scope() as db:
            row = db.execute(
                select(MonitorInventorySnapshot)
                .where(MonitorInventorySnapshot.kind == kind)
                .order_by(MonitorInventorySnapshot.ts.desc()).limit(1)
            ).scalars().first()
            if not row:
                return None
            with contextlib.suppress(json.JSONDecodeError):
                return json.loads(row.data_json)
        return None

    # ================================================================== #
    #  Daily aggregate + retention
    # ================================================================== #
    def _write_daily_aggregate(self) -> None:
        from sqlalchemy import func, select
        since = _utc_now() - timedelta(hours=24)
        with session_scope() as db:
            row = db.execute(
                select(
                    func.avg(TelemetrySample.cpu_pct),
                    func.max(TelemetrySample.cpu_pct),
                    func.avg(TelemetrySample.mem_used_pct),
                    func.max(TelemetrySample.mem_used_pct),
                    func.min(TelemetrySample.disk_free_gb),
                    func.avg(TelemetrySample.net_down_mb_s),
                ).where(TelemetrySample.ts >= since, TelemetrySample.tier != "daily")
            ).first()
            if not row or row[0] is None:
                return
            db.add(TelemetrySample(
                ts=_utc_now(), tier="daily",
                cpu_pct=round(row[0] or 0, 1),
                mem_used_pct=round(row[2] or 0, 1),
                mem_available_gb=0.0,
                disk_free_gb=round(row[4] or 0, 2),
                disk_used_pct=0.0,
                top_json=json.dumps({
                    "cpu_avg": round(row[0] or 0, 1), "cpu_max": round(row[1] or 0, 1),
                    "mem_avg": round(row[2] or 0, 1), "mem_max": round(row[3] or 0, 1),
                    "disk_free_min": round(row[4] or 0, 2),
                    "net_down_avg": round(row[5] or 0, 3),
                }),
            ))
        logger.info("Wrote daily telemetry aggregate.")

    def _prune(self) -> None:
        from sqlalchemy import delete
        now = _utc_now()
        fine_cut = now - timedelta(days=self._s.monitoring_retention_fine_days)
        det_cut = now - timedelta(days=self._s.monitoring_retention_detailed_days)
        ev_cut = now - timedelta(days=365)
        snap_cut = now - timedelta(days=180)
        with session_scope() as db:
            db.execute(delete(TelemetrySample).where(
                TelemetrySample.tier == "critical", TelemetrySample.ts < fine_cut))
            db.execute(delete(TelemetrySample).where(
                TelemetrySample.tier == "detailed", TelemetrySample.ts < det_cut))
            db.execute(delete(MonitorEvent).where(MonitorEvent.ts < ev_cut))
            # Keep only the latest few snapshots per kind beyond the retention window.
            db.execute(delete(MonitorInventorySnapshot).where(
                MonitorInventorySnapshot.kind != "boot",
                MonitorInventorySnapshot.ts < snap_cut))
        logger.info("Pruned old telemetry / events.")
