"""Read-side analytics over continuous-monitoring telemetry.

Turns the raw telemetry / event / snapshot tables into trends, predictions,
anomaly & alert feeds, incident reconstruction, a machine "memory", a digital
twin and auto-generated reports. All methods open their own short-lived DB
sessions so they are safe to call from sync code (e.g. the diagnosis path).
"""
from __future__ import annotations

import contextlib
import json
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session as OrmSession

from app.core.logging import get_logger
from app.db.database import session_scope
from app.db.models import MonitorEvent, MonitorInventorySnapshot, TelemetrySample

logger = get_logger(__name__)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


# --------------------------------------------------------------------------- #
#  Temporal parsing for incident reconstruction
# --------------------------------------------------------------------------- #
_INCIDENT_WORDS = re.compile(
    r"\b(froze|frozen|freeze|hang|hung|crash|crashed|restart|rebooted|reboot|"
    r"blue ?screen|bsod|shut\s?down|slow(ed)?\s?down|unresponsive|stopped working|"
    r"happened|went wrong|earlier|just now)\b",
    re.I,
)
_AGO = re.compile(r"\b(\d+)\s*(second|sec|minute|min|hour|hr|day)s?\s+ago\b", re.I)


def looks_like_incident(text: str) -> bool:
    t = text or ""
    return bool(_INCIDENT_WORDS.search(t) or _AGO.search(t) or
               re.search(r"\b(yesterday|last night|this morning|this afternoon|last week)\b", t, re.I))


def parse_incident_time(text: str) -> tuple[datetime, int]:
    """Return (anchor_utc, window_minutes) for an incident reference.

    Offsets are relative to 'now', so timezone differences don't matter.
    """
    now = _utc_now()
    t = text or ""
    m = _AGO.search(t)
    if m:
        n = int(m.group(1))
        unit = m.group(2).lower()
        if unit.startswith("sec"):
            return now - timedelta(seconds=n), 15
        if unit.startswith("min"):
            return now - timedelta(minutes=n), 20
        if unit.startswith(("hour", "hr")):
            return now - timedelta(hours=n), 60
        if unit.startswith("day"):
            return now - timedelta(days=n), 240
    low = t.lower()
    if "last night" in low:
        return now - timedelta(hours=12), 300
    if "yesterday" in low:
        return now - timedelta(hours=20), 360
    if "this morning" in low:
        return now.replace(hour=3, minute=0, second=0, microsecond=0) if now.hour >= 3 else now - timedelta(hours=4), 240
    if "this afternoon" in low:
        return now - timedelta(hours=4), 240
    if "last week" in low:
        return now - timedelta(days=5), 1440
    # Default: the recent past.
    return now - timedelta(minutes=20), 30


class TelemetryAnalyticsService:
    """Analytics, prediction and incident reconstruction over telemetry."""

    # ================================================================== #
    #  Helpers
    # ================================================================== #
    @staticmethod
    def _samples(db: OrmSession, since: datetime, until: datetime | None = None,
                 exclude_daily: bool = True) -> list[TelemetrySample]:
        q = select(TelemetrySample).where(TelemetrySample.ts >= since)
        if until is not None:
            q = q.where(TelemetrySample.ts <= until)
        if exclude_daily:
            q = q.where(TelemetrySample.tier != "daily")
        q = q.order_by(TelemetrySample.ts.asc())
        return list(db.execute(q).scalars().all())

    @staticmethod
    def _avg(values: list[float | None]) -> float | None:
        vals = [v for v in values if v is not None]
        return round(sum(vals) / len(vals), 1) if vals else None

    # ================================================================== #
    #  Status (dashboard header + AI context)
    # ================================================================== #
    def status(self) -> dict[str, Any]:
        with session_scope() as db:
            latest = db.execute(
                select(TelemetrySample).where(TelemetrySample.tier != "daily")
                .order_by(TelemetrySample.ts.desc()).limit(1)
            ).scalars().first()
            total = db.execute(select(func.count(TelemetrySample.id))).scalar() or 0
            first = db.execute(
                select(func.min(TelemetrySample.ts))
            ).scalar()
            day_ago = _utc_now() - timedelta(hours=24)
            alerts = db.execute(
                select(func.count(MonitorEvent.id)).where(
                    MonitorEvent.ts >= day_ago,
                    MonitorEvent.category.in_(["alert", "anomaly"]))
            ).scalar() or 0
            if not latest:
                return {"active": total > 0, "samples": total, "current": None,
                        "alerts_24h": alerts, "monitoring_since": None}
            return {
                "active": True,
                "samples": total,
                "monitoring_since": first.isoformat() + "Z" if first else None,
                "alerts_24h": alerts,
                "current": {
                    "ts": latest.ts.isoformat() + "Z",
                    "cpu_pct": latest.cpu_pct,
                    "mem_used_pct": latest.mem_used_pct,
                    "mem_available_gb": latest.mem_available_gb,
                    "disk_free_gb": latest.disk_free_gb,
                    "disk_used_pct": latest.disk_used_pct,
                    "net_up_mb_s": latest.net_up_mb_s,
                    "net_down_mb_s": latest.net_down_mb_s,
                    "gpu_pct": latest.gpu_pct,
                    "battery_pct": latest.battery_pct,
                    "process_count": latest.process_count,
                },
            }

    # ================================================================== #
    #  Trends
    # ================================================================== #
    def trends(self, days: int = 7, points: int = 120) -> dict[str, Any]:
        since = _utc_now() - timedelta(days=days)
        with session_scope() as db:
            samples = self._samples(db, since)
        if not samples:
            return {"days": days, "points": [], "averages": {}, "samples": 0}
        # Bucket into ~`points` time buckets and average each.
        bucket_size = max(1, len(samples) // points)
        series: list[dict] = []
        for i in range(0, len(samples), bucket_size):
            chunk = samples[i:i + bucket_size]
            series.append({
                "t": chunk[len(chunk) // 2].ts.isoformat() + "Z",
                "cpu": self._avg([c.cpu_pct for c in chunk]),
                "mem": self._avg([c.mem_used_pct for c in chunk]),
                "disk_free": self._avg([c.disk_free_gb for c in chunk]),
                "net_down": self._avg([c.net_down_mb_s for c in chunk]),
                "net_up": self._avg([c.net_up_mb_s for c in chunk]),
            })
        averages = {
            "cpu": self._avg([c.cpu_pct for c in samples]),
            "cpu_max": round(max((c.cpu_pct for c in samples), default=0), 1),
            "mem": self._avg([c.mem_used_pct for c in samples]),
            "mem_max": round(max((c.mem_used_pct for c in samples), default=0), 1),
            "disk_free": self._avg([c.disk_free_gb for c in samples]),
            "net_down": self._avg([c.net_down_mb_s for c in samples]),
            "latency": self._avg([c.latency_ms for c in samples]),
        }
        return {"days": days, "samples": len(samples), "points": series, "averages": averages}

    # ================================================================== #
    #  Events / alerts feed
    # ================================================================== #
    def events(self, *, limit: int = 80, category: str | None = None,
               days: int = 30) -> list[dict[str, Any]]:
        since = _utc_now() - timedelta(days=days)
        with session_scope() as db:
            q = select(MonitorEvent).where(MonitorEvent.ts >= since)
            if category:
                q = q.where(MonitorEvent.category == category)
            q = q.order_by(MonitorEvent.ts.desc()).limit(limit)
            rows = list(db.execute(q).scalars().all())
        return [self._event_dict(r) for r in rows]

    def alerts(self, *, hours: int = 48) -> list[dict[str, Any]]:
        since = _utc_now() - timedelta(hours=hours)
        with session_scope() as db:
            rows = list(db.execute(
                select(MonitorEvent).where(
                    MonitorEvent.ts >= since,
                    MonitorEvent.category.in_(["alert", "anomaly", "security"]),
                ).order_by(MonitorEvent.ts.desc()).limit(50)
            ).scalars().all())
        return [self._event_dict(r) for r in rows]

    def change_timeline(self, *, days: int = 30, limit: int = 80) -> list[dict[str, Any]]:
        since = _utc_now() - timedelta(days=days)
        with session_scope() as db:
            rows = list(db.execute(
                select(MonitorEvent).where(
                    MonitorEvent.ts >= since,
                    MonitorEvent.category.in_(["change", "device", "driver", "update", "security", "boot"]),
                ).order_by(MonitorEvent.ts.desc()).limit(limit)
            ).scalars().all())
        return [self._event_dict(r) for r in rows]

    @staticmethod
    def _event_dict(r: MonitorEvent) -> dict[str, Any]:
        return {
            "ts": r.ts.isoformat() + "Z", "category": r.category, "severity": r.severity,
            "title": r.title, "detail": r.detail,
        }

    # ================================================================== #
    #  Boot history
    # ================================================================== #
    def boot_history(self, *, limit: int = 20) -> dict[str, Any]:
        with session_scope() as db:
            boots = list(db.execute(
                select(MonitorEvent).where(MonitorEvent.category == "boot")
                .order_by(MonitorEvent.ts.desc()).limit(limit)
            ).scalars().all())
            latest_boot = db.execute(
                select(MonitorInventorySnapshot).where(MonitorInventorySnapshot.kind == "boot")
                .order_by(MonitorInventorySnapshot.ts.desc()).limit(1)
            ).scalars().first()
        uptime_hours = None
        if latest_boot:
            with contextlib.suppress(Exception):
                data = json.loads(latest_boot.data_json)
                bt = datetime.fromtimestamp(float(data["boot_time"]), tz=timezone.utc).replace(tzinfo=None)
                uptime_hours = round((_utc_now() - bt).total_seconds() / 3600, 1)
        return {
            "uptime_hours": uptime_hours,
            "boots": [self._event_dict(b) for b in boots],
            "boot_count": len(boots),
        }

    # ================================================================== #
    #  Predictions
    # ================================================================== #
    def predictions(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        with session_scope() as db:
            since = _utc_now() - timedelta(days=14)
            samples = self._samples(db, since)
        out["disk"] = self._predict_disk(samples)
        out["performance"] = self._predict_performance(samples)
        out["battery"] = self._predict_battery(samples)
        return out

    def _predict_disk(self, samples: list[TelemetrySample]) -> dict[str, Any]:
        pts = [(s.ts, s.disk_free_gb) for s in samples if s.disk_free_gb]
        if len(pts) < 5:
            return {"available": False}
        slope = self._linfit_per_day(pts)  # GB free change per day (negative = filling)
        latest_free = pts[-1][1]
        result = {"available": True, "free_gb": round(latest_free, 1),
                  "change_gb_per_day": round(slope, 3)}
        if slope < -0.05:
            result["days_until_full"] = int(latest_free / -slope)
        return result

    def _predict_performance(self, samples: list[TelemetrySample]) -> dict[str, Any]:
        now = _utc_now()
        wk = now - timedelta(days=7)
        this_week = [s for s in samples if s.ts >= wk]
        prev_week = [s for s in samples if s.ts < wk]
        cpu_now = self._avg([s.cpu_pct for s in this_week])
        cpu_prev = self._avg([s.cpu_pct for s in prev_week])
        mem_now = self._avg([s.mem_used_pct for s in this_week])
        mem_prev = self._avg([s.mem_used_pct for s in prev_week])
        regressed = bool(cpu_now and cpu_prev and cpu_now > cpu_prev + 8) or \
            bool(mem_now and mem_prev and mem_now > mem_prev + 8)
        return {
            "available": bool(cpu_prev or mem_prev),
            "cpu_this_week": cpu_now, "cpu_prev_week": cpu_prev,
            "mem_this_week": mem_now, "mem_prev_week": mem_prev,
            "regression_detected": regressed,
        }

    def _predict_battery(self, samples: list[TelemetrySample]) -> dict[str, Any]:
        batt = [s.battery_pct for s in samples if s.battery_pct is not None]
        if not batt:
            return {"available": False}
        return {"available": True, "current_pct": batt[-1],
                "note": "Battery telemetry is being collected; wear trends appear over time."}

    @staticmethod
    def _linfit_per_day(pts: list[tuple[datetime, float]]) -> float:
        """Least-squares slope of value vs time, expressed per day."""
        t0 = pts[0][0]
        xs = [(t - t0).total_seconds() / 86400 for t, _ in pts]
        ys = [v for _, v in pts]
        n = len(xs)
        sx, sy = sum(xs), sum(ys)
        sxx = sum(x * x for x in xs)
        sxy = sum(x * y for x, y in zip(xs, ys))
        denom = n * sxx - sx * sx
        if abs(denom) < 1e-9:
            return 0.0
        return (n * sxy - sx * sy) / denom

    # ================================================================== #
    #  Incident reconstruction
    # ================================================================== #
    def incident(self, when: datetime, window_minutes: int = 30,
                 event_log_entries: Optional[list[dict]] = None) -> dict[str, Any]:
        half = timedelta(minutes=window_minutes)
        start, end = when - half, when + half
        with session_scope() as db:
            samples = self._samples(db, start, end)
            events = list(db.execute(
                select(MonitorEvent).where(MonitorEvent.ts >= start, MonitorEvent.ts <= end)
                .order_by(MonitorEvent.ts.asc())
            ).scalars().all())

        timeline: list[dict] = []
        peak_cpu = peak_mem = 0.0
        min_disk = None
        crossed_mem95 = crossed_cpu95 = False
        for s in samples:
            peak_cpu = max(peak_cpu, s.cpu_pct or 0)
            peak_mem = max(peak_mem, s.mem_used_pct or 0)
            if s.disk_free_gb:
                min_disk = s.disk_free_gb if min_disk is None else min(min_disk, s.disk_free_gb)
            if (s.mem_used_pct or 0) >= 95 and not crossed_mem95:
                crossed_mem95 = True
                timeline.append({"ts": s.ts.isoformat() + "Z", "kind": "metric",
                                 "text": f"RAM reached {s.mem_used_pct}%"})
            if (s.cpu_pct or 0) >= 95 and not crossed_cpu95:
                crossed_cpu95 = True
                timeline.append({"ts": s.ts.isoformat() + "Z", "kind": "metric",
                                 "text": f"CPU reached {s.cpu_pct}%"})
        for e in events:
            timeline.append({"ts": e.ts.isoformat() + "Z", "kind": e.category,
                             "text": e.title, "severity": e.severity})
        # Event-log timestamps are local; convert to UTC and keep only the window.
        local_offset = datetime.now() - datetime.utcnow()
        log_hits = 0
        for entry in (event_log_entries or []):
            ts = entry.get("time_generated") or entry.get("timestamp")
            entry_utc = self._parse_local_to_utc(ts, local_offset)
            if entry_utc is None or not (start <= entry_utc <= end):
                continue
            log_hits += 1
            timeline.append({"ts": entry_utc.isoformat() + "Z", "kind": "event_log",
                             "text": f"{entry.get('source', 'System')}: {(entry.get('message') or '')[:120]}",
                             "severity": (entry.get("level") or "").lower()})
        timeline.sort(key=lambda x: str(x.get("ts") or ""))

        window_logs = [t for t in timeline if t.get("kind") == "event_log"]
        cause, confidence = self._probable_cause(
            peak_cpu, peak_mem, min_disk, events,
            [{"source": "", "message": t["text"]} for t in window_logs])
        return {
            "anchor": when.isoformat() + "Z",
            "window_minutes": window_minutes,
            "samples_found": len(samples),
            "peak_cpu_pct": round(peak_cpu, 1),
            "peak_mem_pct": round(peak_mem, 1),
            "min_disk_free_gb": round(min_disk, 1) if min_disk is not None else None,
            "timeline": timeline[:40],
            "probable_cause": cause,
            "confidence": confidence,
            "has_telemetry": len(samples) > 0,
        }

    @staticmethod
    def _parse_local_to_utc(ts: Any, offset: timedelta) -> datetime | None:
        if not ts:
            return None
        if isinstance(ts, datetime):
            return ts.replace(tzinfo=None) - offset
        try:
            local = datetime.fromisoformat(str(ts).replace("Z", "")).replace(tzinfo=None)
        except (ValueError, TypeError):
            return None
        return local - offset

    @staticmethod
    def _probable_cause(peak_cpu: float, peak_mem: float, min_disk: float | None,
                        events: list[MonitorEvent], logs: list[dict]) -> tuple[str, int]:
        bsod = any("bsod" in (e.title or "").lower() or "blue screen" in (e.title or "").lower() for e in events)
        crash = any(e.category == "crash" for e in events) or \
            any("crash" in (l.get("source", "") + l.get("message", "")).lower() for l in logs)
        svc_fail = any(e.category == "service" for e in events)
        if bsod:
            return "System crash (BSOD) — driver or hardware fault", 90
        if min_disk is not None and min_disk < 1:
            return "Disk exhaustion — system drive ran out of space", 88
        if peak_mem >= 95:
            return "Memory exhaustion — RAM saturated, heavy paging likely caused the freeze", 92
        if peak_cpu >= 95:
            return "CPU saturation — a process pinned the CPU near 100%", 85
        if crash:
            return "Application crash during this window", 75
        if svc_fail:
            return "A critical service stopped during this window", 70
        if peak_mem == 0 and peak_cpu == 0:
            return "No telemetry was recorded for this period (monitor may not have been running yet)", 25
        return "No single dominant cause; resource levels looked normal in telemetry", 45

    # ================================================================== #
    #  Machine memory (long-term understanding)
    # ================================================================== #
    def machine_memory(self) -> dict[str, Any]:
        facts: list[str] = []
        with session_scope() as db:
            samples14 = self._samples(db, _utc_now() - timedelta(days=14))
            day = _utc_now() - timedelta(days=7)
            recent_events = list(db.execute(
                select(MonitorEvent).where(MonitorEvent.ts >= day)
                .order_by(MonitorEvent.ts.desc()).limit(200)
            ).scalars().all())

        # Disk trend.
        disk_pts = [(s.ts, s.disk_free_gb) for s in samples14 if s.disk_free_gb]
        if len(disk_pts) >= 5:
            slope = self._linfit_per_day(disk_pts)
            if slope < -0.2:
                facts.append(f"Free disk space has been decreasing by ~{abs(round(slope, 1))} GB/day.")
            elif slope > 0.2:
                facts.append(f"Free disk space has been increasing by ~{round(slope, 1)} GB/day.")

        # Sustained memory.
        mem_avg = self._avg([s.mem_used_pct for s in samples14])
        if mem_avg and mem_avg >= 80:
            facts.append(f"Memory usage has averaged {mem_avg}% over the past 14 days — consistently high.")

        # Top memory consumer over time (from detailed samples).
        top_app = self._frequent_top_mem(samples14)
        if top_app:
            facts.append(f"{top_app['name']} has been the top memory consumer, averaging ~{top_app['avg_mb']} MB.")

        # Repeated alerts / crashes / changes.
        by_title: dict[str, int] = {}
        for e in recent_events:
            if e.category in ("alert", "anomaly", "crash", "service"):
                by_title[e.title] = by_title.get(e.title, 0) + 1
        for title, count in sorted(by_title.items(), key=lambda kv: kv[1], reverse=True)[:3]:
            if count >= 2:
                facts.append(f"\"{title}\" occurred {count} times in the last 7 days.")

        installs = [e for e in recent_events if e.category == "change" and "installed" in e.title.lower()]
        if installs:
            facts.append(f"{len(installs)} software change(s) in the last 7 days "
                         f"(latest: {installs[0].title}).")

        return {"facts": facts, "generated_at": _utc_now().isoformat() + "Z"}

    @staticmethod
    def _frequent_top_mem(samples: list[TelemetrySample]) -> dict[str, Any] | None:
        counts: dict[str, list[float]] = {}
        for s in samples:
            if not s.top_json:
                continue
            with contextlib.suppress(Exception):
                data = json.loads(s.top_json)
                top = (data.get("top_mem") or [])
                if top:
                    name = top[0].get("name") or "?"
                    counts.setdefault(name, []).append(float(top[0].get("mem_mb") or 0))
        if not counts:
            return None
        best = max(counts.items(), key=lambda kv: len(kv[1]))
        name, vals = best
        if len(vals) < 3:
            return None
        return {"name": name, "avg_mb": round(sum(vals) / len(vals)), "samples": len(vals)}

    # ================================================================== #
    #  Digital twin
    # ================================================================== #
    def digital_twin(self) -> dict[str, Any]:
        status = self.status()
        trends = self.trends(days=7)
        boot = self.boot_history(limit=5)
        return {
            "current_state": status.get("current"),
            "monitoring_since": status.get("monitoring_since"),
            "samples": status.get("samples"),
            "baseline_7d": trends.get("averages"),
            "uptime_hours": boot.get("uptime_hours"),
            "recent_changes": self.change_timeline(days=14, limit=12),
            "known_issues": self.alerts(hours=24),
            "machine_memory": self.machine_memory().get("facts"),
        }

    # ================================================================== #
    #  Auto-generated reports
    # ================================================================== #
    def report(self, period: str = "daily") -> dict[str, Any]:
        days = {"daily": 1, "weekly": 7, "monthly": 30}.get(period, 1)
        trends = self.trends(days=days)
        avg = trends.get("averages") or {}
        changes = self.change_timeline(days=days, limit=30)
        alerts = self.alerts(hours=days * 24)
        preds = self.predictions()

        # Simple telemetry health score.
        score = 100
        if (avg.get("cpu") or 0) > 70:
            score -= 15
        if (avg.get("mem") or 0) > 85:
            score -= 20
        if any(a["severity"] == "critical" for a in alerts):
            score -= 25
        disk = preds.get("disk") or {}
        if disk.get("days_until_full") is not None and disk["days_until_full"] < 30:
            score -= 20
        score = max(0, score)
        status = "Healthy" if score >= 80 else "Warning" if score >= 50 else "Critical"

        risks: list[str] = []
        if disk.get("days_until_full") is not None and disk["days_until_full"] < 45:
            risks.append(f"Disk projected full in ~{disk['days_until_full']} days.")
        if (preds.get("performance") or {}).get("regression_detected"):
            risks.append("Performance has regressed versus the prior week.")
        for a in alerts[:3]:
            if a["severity"] in ("critical", "warning"):
                risks.append(a["title"])

        recommendations: list[str] = []
        if disk.get("days_until_full") is not None and disk["days_until_full"] < 45:
            recommendations.append("Run the Storage Analysis and clear recoverable space.")
        if (avg.get("mem") or 0) > 85:
            recommendations.append("Close memory-heavy apps or add RAM; check the top memory consumer.")
        if not recommendations:
            recommendations.append("No action needed — system is operating within normal ranges.")

        return {
            "period": period, "generated_at": _utc_now().isoformat() + "Z",
            "health_score": score, "status": status,
            "averages": avg,
            "major_changes": changes[:10],
            "alerts": alerts[:10],
            "risks": risks,
            "recommendations": recommendations,
        }

    # ================================================================== #
    #  Compact context for the AI diagnosis path
    # ================================================================== #
    def diagnosis_context(self) -> dict[str, Any]:
        status = self.status()
        return {
            "current": status.get("current"),
            "baseline_7d": self.trends(days=7).get("averages"),
            "recent_alerts": self.alerts(hours=72)[:6],
            "recent_changes": self.change_timeline(days=14, limit=8),
            "machine_memory": self.machine_memory().get("facts"),
            "predictions": self.predictions(),
        }
