"""Performance live probe pack: CPU, RAM, uptime, top processes, startup load."""
from __future__ import annotations

import time

import psutil

from app.models.schemas import ProbeCheck, ProbeResult, Severity, TroubleshooterFinding
from app.services.probes.base import IS_WINDOWS, ProbeContext, ProbeOutcome, ps_json

DOMAIN = "performance"
TITLE = "Performance"

MB = 1024 ** 2
CPU_WARN, CPU_CRIT = 75.0, 90.0
RAM_WARN, RAM_CRIT = 85.0, 92.0
UPTIME_WARN_HOURS = 48.0

# Dev/assistant tooling we should not tell users to kill.
_DEV_PROCESSES = {"python.exe", "pythonw.exe", "node.exe", "uvicorn.exe", "electron.exe", "code.exe"}
_IGNORE_PROCESSES = {"system idle process", "memory compression", "memcompression"}


def _level(value: float, warn: float, crit: float) -> Severity:
    if value >= crit:
        return Severity.critical
    if value >= warn:
        return Severity.warning
    return Severity.healthy


def _top_cpu() -> tuple[str, float] | None:
    procs = []
    for p in psutil.process_iter(["name"]):
        try:
            p.cpu_percent(None)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    time.sleep(0.4)
    ncpu = psutil.cpu_count() or 1
    for p in psutil.process_iter(["name"]):
        try:
            cpu = p.cpu_percent(None) / ncpu
            name = (p.info.get("name") or "").strip()
            if name and name.lower() not in _IGNORE_PROCESSES:
                procs.append((name, round(cpu, 1)))
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    if not procs:
        return None
    procs.sort(key=lambda x: x[1], reverse=True)
    return procs[0]


def _startup_count() -> int:
    if not IS_WINDOWS:
        return 0
    data = ps_json(
        "(Get-CimInstance Win32_StartupCommand -ErrorAction SilentlyContinue | Measure-Object).Count "
        "| ConvertTo-Json -Compress"
    )
    try:
        return int(data) if data is not None else 0
    except (TypeError, ValueError):
        return 0


def investigate(ctx: ProbeContext) -> ProbeOutcome:
    checks: list[ProbeCheck] = []
    findings: list[TroubleshooterFinding] = []

    cpu = psutil.cpu_percent(interval=0.5)
    vm = psutil.virtual_memory()
    ram = vm.percent
    try:
        uptime_h = (time.time() - psutil.boot_time()) / 3600.0
    except Exception:
        uptime_h = 0.0

    checks.append(ProbeCheck(label="CPU usage", value=f"{cpu}%", status=_level(cpu, CPU_WARN, CPU_CRIT)))
    checks.append(ProbeCheck(
        label="Memory usage",
        value=f"{ram}% ({round(vm.available/ (1024**3),1)} GB free)",
        status=_level(ram, RAM_WARN, RAM_CRIT),
    ))
    days = round(uptime_h / 24, 1)
    checks.append(ProbeCheck(
        label="Uptime",
        value=f"{days} days",
        status=Severity.warning if uptime_h >= 72 else (Severity.info if uptime_h >= UPTIME_WARN_HOURS else Severity.healthy),
    ))

    top = _top_cpu()
    if top:
        checks.append(ProbeCheck(
            label="Top CPU process",
            value=f"{top[0]} ({top[1]}%)",
            status=_level(top[1], 40, 70),
        ))

    startup = _startup_count()
    if startup:
        checks.append(ProbeCheck(
            label="Startup programs",
            value=str(startup),
            status=Severity.info if startup < 10 else Severity.warning,
        ))

    # Findings
    if cpu >= CPU_WARN and top and top[1] >= 40 and top[0].lower() not in _DEV_PROCESSES:
        findings.append(TroubleshooterFinding(
            id="perf_high_cpu",
            title="High CPU Usage",
            area="Performance",
            severity=Severity.critical if cpu >= CPU_CRIT else Severity.warning,
            detected=f"CPU is at {cpu}% with '{top[0]}' using {top[1]}%.",
            likely_cause=f"The process '{top[0]}' (or background tasks like an update/AV scan) is consuming the CPU.",
            resolution_steps=[
                "Open Task Manager (Ctrl+Shift+Esc) and sort by CPU.",
                f"If '{top[0]}' isn't essential, select it and End task.",
                "Let any Windows Update or antivirus scan finish.",
                "Disable unneeded startup apps (Task Manager > Startup apps).",
                "Restart if usage stays high.",
            ],
            ask_ai_prompt=f"My CPU is at {cpu}% with {top[0]} on top. What's causing it and how do I fix it?",
        ))

    if ram >= RAM_WARN:
        findings.append(TroubleshooterFinding(
            id="perf_high_ram",
            title="High Memory Usage",
            area="Performance",
            severity=Severity.critical if ram >= RAM_CRIT else Severity.warning,
            detected=f"RAM is at {ram}% ({round(vm.available/(1024**3),1)} GB free).",
            likely_cause="Too many apps/browser tabs open, or an app with a memory leak.",
            resolution_steps=[
                "Close memory-heavy apps and extra browser tabs (Task Manager > Memory).",
                "Restart the browser to release leaked memory.",
                "Restart the PC if uptime is high.",
                "Consider adding RAM if this is constant.",
            ],
            ask_ai_prompt=f"My memory is at {ram}%. How do I reduce memory usage?",
        ))

    # Uptime/slowness - restart-first guidance when metrics are otherwise normal.
    slow = any(s in ctx.symptoms for s in ("slow",)) or "performance" in ctx.domains
    if uptime_h >= UPTIME_WARN_HOURS and slow and cpu < CPU_WARN and ram < RAM_WARN:
        findings.append(TroubleshooterFinding(
            id="perf_long_uptime",
            title="PC Needs a Restart",
            area="Performance",
            severity=Severity.info if uptime_h < 72 else Severity.warning,
            detected=f"The PC has been on for {days} days; CPU ({cpu}%) and RAM ({ram}%) are within normal range.",
            likely_cause="Long uptime lets memory leaks and stale handles build up and leaves updates pending - "
            "a common cause of gradual slowness even when metrics look fine.",
            resolution_steps=[
                "Save your work and restart the PC (Start > Power > Restart).",
                "After restart, install pending updates: Settings > Windows Update.",
                "Trim startup apps if boot is slow (Task Manager > Startup apps).",
            ],
            ask_ai_prompt=f"My PC has been on {days} days and feels slow but CPU/RAM look normal. Should I restart?",
        ))

    return ProbeOutcome(
        result=ProbeResult(domain=DOMAIN, title=TITLE, available=True, checks=checks),
        findings=findings,
    )
