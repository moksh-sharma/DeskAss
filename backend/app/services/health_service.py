"""Builds the Machine Health Report for the full diagnostic scan."""
from __future__ import annotations

from app.models.schemas import (
    HealthCheck,
    HealthReport,
    Severity,
    SystemDiagnostics,
    TroubleshooterFinding,
)
from app.services.diagnostics_service import (
    CPU_CRIT,
    CPU_WARN,
    DISK_CRIT,
    DISK_WARN,
    RAM_CRIT,
    RAM_WARN,
)
from app.models.schemas import EventLogSummary

_RANK = {Severity.healthy: 0, Severity.info: 1, Severity.warning: 2, Severity.critical: 3}


class HealthService:
    """Turns raw diagnostics + logs into a graded health report."""

    def build_report(
        self,
        diagnostics: SystemDiagnostics,
        event_logs: EventLogSummary,
        findings: list[TroubleshooterFinding] | None = None,
    ) -> HealthReport:
        findings = findings or []
        checks: list[HealthCheck] = []
        recommendations: list[str] = []

        # CPU
        cpu_status = self._level(diagnostics.cpu.usage_percent, CPU_WARN, CPU_CRIT)
        checks.append(HealthCheck(name="CPU", status=cpu_status,
                                  detail=f"{diagnostics.cpu.usage_percent}% utilisation"))
        if cpu_status != Severity.healthy:
            top = diagnostics.top_cpu_processes[0].name if diagnostics.top_cpu_processes else "a process"
            recommendations.append(f"High CPU usage - review '{top}' in Task Manager.")

        # RAM
        ram_status = self._level(diagnostics.memory.usage_percent, RAM_WARN, RAM_CRIT)
        checks.append(HealthCheck(name="Memory", status=ram_status,
                                  detail=f"{diagnostics.memory.usage_percent}% used, {diagnostics.memory.available_gb} GB free"))
        if ram_status != Severity.healthy:
            recommendations.append("High memory pressure - close unused apps or add RAM.")

        # Disk
        for disk in diagnostics.disks:
            d_status = self._level(disk.usage_percent, DISK_WARN, DISK_CRIT)
            checks.append(HealthCheck(name=f"Disk {disk.device}", status=d_status,
                                      detail=f"{disk.usage_percent}% used, {disk.free_gb} GB free"))
            if d_status != Severity.healthy:
                recommendations.append(f"Disk {disk.device} is low on space - run Disk Cleanup / clear temp files.")

        # Network
        net_status = Severity.healthy if diagnostics.network.internet_connected else Severity.warning
        checks.append(HealthCheck(name="Network", status=net_status,
                                  detail="Internet reachable" if diagnostics.network.internet_connected else "No internet connectivity"))
        if net_status != Severity.healthy:
            recommendations.append("No internet - check Wi-Fi/VPN/adapter and DNS settings.")

        # Battery
        if diagnostics.battery.present:
            b_status = Severity.warning if (diagnostics.battery.percent or 100) < 20 and not diagnostics.battery.charging else Severity.healthy
            checks.append(HealthCheck(name="Battery", status=b_status,
                                      detail=f"{diagnostics.battery.percent}% {'charging' if diagnostics.battery.charging else 'on battery'}"))

        # Event logs
        if event_logs.available:
            # A few error events over several days is normal on Windows; only escalate
            # on a high volume. Specific crash/disk/power patterns are surfaced as findings.
            log_status = Severity.healthy
            if event_logs.error_count >= 20:
                log_status = Severity.critical
            elif event_logs.error_count >= 10:
                log_status = Severity.warning
            elif event_logs.error_count > 0:
                log_status = Severity.info
            checks.append(HealthCheck(name="Event Logs", status=log_status,
                                      detail=f"{event_logs.error_count} errors, {event_logs.warning_count} warnings"))
            if log_status in (Severity.warning, Severity.critical):
                recommendations.append("Recent error events detected - review the Event Log analysis for crashing apps.")
        else:
            checks.append(HealthCheck(name="Event Logs", status=Severity.info,
                                      detail=event_logs.note or "Unavailable"))

        overall = max((c.status for c in checks), key=lambda s: _RANK[s])
        # Findings can raise the overall severity even if headline metrics look fine.
        if findings:
            worst_finding = max((f.severity for f in findings), key=lambda s: _RANK[s])
            if _RANK[worst_finding] > _RANK[overall]:
                overall = worst_finding
        if not recommendations:
            recommendations.append("System looks healthy. No action required.")

        checks_total = len(checks)
        checks_passed = sum(1 for c in checks if c.status == Severity.healthy)
        issue_count = sum(1 for f in findings if f.severity in (Severity.warning, Severity.critical))
        suggestion_count = sum(1 for f in findings if f.severity == Severity.info)

        def _plural(n: int) -> str:
            return "s" if n != 1 else ""

        if issue_count:
            summary = (
                f"Scan complete: found {issue_count} issue{_plural(issue_count)} that need attention"
            )
            if suggestion_count:
                summary += f" and {suggestion_count} suggestion{_plural(suggestion_count)}"
            summary += f" ({checks_passed}/{checks_total} checks passed)."
        elif suggestion_count:
            summary = (
                f"Scan complete: no critical issues. {suggestion_count} suggestion{_plural(suggestion_count)} "
                f"to improve your PC ({checks_passed}/{checks_total} checks passed)."
            )
        else:
            summary = f"Scan complete: no problems found. All {checks_total} checks passed."

        return HealthReport(
            overall_status=overall,
            checks=checks,
            findings=findings,
            checks_passed=checks_passed,
            checks_total=checks_total,
            summary=summary,
            diagnostics=diagnostics,
            event_logs=event_logs,
            recommendations=recommendations,
        )

    @staticmethod
    def _level(value: float, warn: float, crit: float) -> Severity:
        if value >= crit:
            return Severity.critical
        if value >= warn:
            return Severity.warning
        return Severity.healthy
