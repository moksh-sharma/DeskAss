"""Shared helpers for live probe packs."""
from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass, field
from typing import Any

from app.core.logging import get_logger
from app.models.schemas import ProbeResult, Severity, TroubleshooterFinding

logger = get_logger(__name__)

IS_WINDOWS = sys.platform == "win32"


@dataclass
class ProbeContext:
    """Context passed to every probe: the parsed issue details plus a live
    snapshot of installed apps, running processes and services so probes can
    match arbitrary applications/services the user names."""

    message: str = ""
    domains: list[str] = field(default_factory=list)
    apps: list[str] = field(default_factory=list)
    symptoms: list[str] = field(default_factory=list)
    # Inventory (populated by the investigation service).
    installed_apps: list[Any] = field(default_factory=list)   # list[InstalledApp]
    process_names: set[str] = field(default_factory=set)      # lowercased exe names
    services: list[Any] = field(default_factory=list)         # list[ServiceEntry]


@dataclass
class ProbeOutcome:
    """What a probe returns: observed facts + deterministic findings."""

    result: ProbeResult
    findings: list[TroubleshooterFinding] = field(default_factory=list)


def run_powershell(script: str, timeout: float = 20.0) -> tuple[bool, str]:
    """Run a PowerShell snippet and return ``(ok, stdout)``.

    Never raises - on any failure returns ``(False, error_text)`` so probes stay
    defensive and one failing query can't break the investigation.
    """
    if not IS_WINDOWS:
        return False, "not windows"
    try:
        completed = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy", "Bypass",
                "-Command", script,
            ],
            capture_output=True,
            text=True,
            timeout=timeout,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if completed.returncode != 0 and not completed.stdout.strip():
            return False, (completed.stderr or "").strip()
        return True, completed.stdout.strip()
    except subprocess.TimeoutExpired:
        return False, f"timed out after {timeout}s"
    except Exception as exc:  # pragma: no cover - host dependent
        logger.debug("PowerShell probe failed: %s", exc)
        return False, str(exc)


def ps_json(script: str, timeout: float = 20.0) -> Any:
    """Run PowerShell that ends in ``ConvertTo-Json`` and parse the result.

    Returns a dict/list on success, or ``None`` on any failure. Single-object
    results are returned as dicts; multi-object as lists.
    """
    # Force array output so single rows still parse to a list when expected.
    ok, out = run_powershell(script, timeout=timeout)
    if not ok or not out:
        return None
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        logger.debug("Probe JSON parse failed for output: %s", out[:200])
        return None


def as_list(value: Any) -> list[Any]:
    """Normalise ConvertTo-Json output (dict or list) into a list."""
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def get_service(name: str) -> dict | None:
    """Return a service's state with Status/StartType as readable strings.

    ``Get-Service`` serialises Status/StartType as enum *integers* under
    ConvertTo-Json, so we force ``.ToString()`` to get values like
    'Running' / 'Manual' instead of 4 / 3.
    """
    data = ps_json(
        f"Get-Service -Name '{name}' -ErrorAction SilentlyContinue | "
        "Select-Object Name,"
        "@{N='Status';E={$_.Status.ToString()}},"
        "@{N='StartType';E={$_.StartType.ToString()}} | "
        "ConvertTo-Json -Compress"
    )
    if isinstance(data, list):
        return data[0] if data else None
    return data


def unavailable(domain: str, title: str, note: str) -> ProbeOutcome:
    """Build an outcome for when a probe can't run (e.g. non-Windows)."""
    return ProbeOutcome(
        result=ProbeResult(domain=domain, title=title, available=False, note=note),
        findings=[],
    )


# Device "Problem" codes that are NOT real faults:
#   0  = no problem
#   45 = device not currently connected (phantom/hidden device)
_NON_FAULT_PROBLEM_CODES = {0, 45}


def is_real_device_problem(status: str | None, problem: object = None) -> bool:
    """True only for genuine device faults - ignores disconnected/phantom devices.

    Windows lists hidden/disconnected devices with Status 'Unknown' and Problem
    code 45 ('not connected'); those must not be reported as faults.
    """
    s = (status or "").strip().lower()
    if s == "error":
        return True
    if s in ("", "ok", "unknown", "degraded"):
        # 'Unknown' is almost always a disconnected device (code 45).
        if s == "unknown":
            return False
    try:
        code = int(problem) if problem is not None else 0
    except (TypeError, ValueError):
        code = 0
    return code not in _NON_FAULT_PROBLEM_CODES


def worst_status(statuses: list[Severity]) -> Severity:
    rank = {Severity.healthy: 0, Severity.info: 1, Severity.warning: 2, Severity.critical: 3}
    worst = Severity.healthy
    for s in statuses:
        if rank[s] > rank[worst]:
            worst = s
    return worst
