"""Windows Event Log collection and analysis.

On Windows this uses ``pywin32`` (``win32evtlog``) to read the Application and
System logs, filtering for errors and warnings. On non-Windows platforms it
gracefully returns an empty, "unavailable" summary so the rest of the pipeline
keeps working in development.
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta

from app.core.logging import get_logger
from app.models.schemas import EventLogEntry, EventLogSummary

logger = get_logger(__name__)

IS_WINDOWS = sys.platform == "win32"

# Keywords used to categorise interesting events for the troubleshooting domain.
_CATEGORY_KEYWORDS = {
    "Outlook": ["outlook"],
    "Teams": ["teams", "ms-teams"],
    "Office": ["office", "winword", "excel", "officeclicktorun"],
    "Driver": ["driver", "device"],
    "Service": ["service", "scm", "service control manager"],
    "Application Hang": ["hang", "not responding"],
    "Application Crash": ["faulting application", "application error", "appcrash", ".dll", "crash"],
    "Kernel": ["kernel"],
    "Disk": ["disk", "ntfs", "volume"],
}

_LEVEL_NAMES = {1: "Error", 2: "Warning", 4: "Information", 8: "Audit Success", 16: "Audit Failure"}


class EventLogService:
    """Reads recent Windows event-log errors and warnings."""

    def collect(self, *, hours_back: int = 72, max_per_log: int = 60) -> EventLogSummary:
        if not IS_WINDOWS:
            return EventLogSummary(
                available=False,
                note="Windows Event Log is only available on Windows hosts.",
            )
        try:
            return self._collect_windows(hours_back=hours_back, max_per_log=max_per_log)
        except Exception as exc:  # pragma: no cover - depends on host
            logger.warning("Event log collection failed: %s", exc)
            return EventLogSummary(available=False, note=f"Event log collection failed: {exc}")

    def _collect_windows(self, *, hours_back: int, max_per_log: int) -> EventLogSummary:
        import win32con  # type: ignore
        import win32evtlog  # type: ignore
        import winerror  # type: ignore

        cutoff = datetime.now() - timedelta(hours=hours_back)
        entries: list[EventLogEntry] = []
        error_count = 0
        warning_count = 0

        flags = win32evtlog.EVENTLOG_BACKWARDS_READ | win32evtlog.EVENTLOG_SEQUENTIAL_READ

        for log_name in ("Application", "System"):
            handle = win32evtlog.OpenEventLog(None, log_name)
            collected = 0
            try:
                while collected < max_per_log:
                    records = win32evtlog.ReadEventLog(handle, flags, 0)
                    if not records:
                        break
                    for rec in records:
                        event_type = rec.EventType
                        # Only Errors (1) and Warnings (2).
                        if event_type not in (win32con.EVENTLOG_ERROR_TYPE, win32con.EVENTLOG_WARNING_TYPE):
                            continue
                        gen_time = self._parse_time(rec.TimeGenerated)
                        if gen_time and gen_time < cutoff:
                            collected = max_per_log  # stop: older than window
                            break
                        message = self._format_message(rec)
                        level = "Error" if event_type == win32con.EVENTLOG_ERROR_TYPE else "Warning"
                        if level == "Error":
                            error_count += 1
                        else:
                            warning_count += 1
                        entries.append(
                            EventLogEntry(
                                source=str(rec.SourceName),
                                log_name=log_name,
                                level=level,
                                event_id=rec.EventID & 0xFFFF,
                                time_generated=gen_time,
                                message=message[:1500],
                                category=self._categorise(str(rec.SourceName), message),
                            )
                        )
                        collected += 1
                        if collected >= max_per_log:
                            break
            finally:
                win32evtlog.CloseEventLog(handle)

        entries.sort(key=lambda e: e.time_generated or datetime.min, reverse=True)
        return EventLogSummary(
            available=True,
            error_count=error_count,
            warning_count=warning_count,
            entries=entries,
        )

    # ------------------------------------------------------------------ #
    @staticmethod
    def _parse_time(value) -> datetime | None:  # type: ignore[no-untyped-def]
        try:
            # pywintypes.datetime -> python datetime
            return datetime.fromtimestamp(int(value))
        except (TypeError, ValueError, OSError):
            try:
                return datetime(value.year, value.month, value.day, value.hour, value.minute, value.second)
            except Exception:
                return None

    @staticmethod
    def _format_message(rec) -> str:  # type: ignore[no-untyped-def]
        try:
            import win32evtlogutil  # type: ignore

            msg = win32evtlogutil.SafeFormatMessage(rec, rec.SourceName)
            if msg:
                return " ".join(msg.split())
        except Exception:
            pass
        if rec.StringInserts:
            return " ".join(str(s) for s in rec.StringInserts)
        return f"Event {rec.EventID & 0xFFFF} from {rec.SourceName}"

    @staticmethod
    def _categorise(source: str, message: str) -> str | None:
        haystack = f"{source} {message}".lower()
        for category, keywords in _CATEGORY_KEYWORDS.items():
            if any(k in haystack for k in keywords):
                return category
        return None
