import { useStore } from "@/store/useStore";
import { FindingCard } from "@/components/common/FindingCard";
import { EventLogTable } from "@/components/common/EventLogTable";
import { formatDateTime } from "@/lib/format";
import type { EventLogEntry, MachineScanReport } from "@/types";

function notableLogs(entries: EventLogEntry[]): EventLogEntry[] {
  return entries.filter((e) => {
    const level = (e.level || "").toLowerCase();
    return level === "error" || level === "critical" || level === "warning";
  });
}

export function MachineScanTroubleshooter({ report }: { report: MachineScanReport }) {
  const resolveIssue = useStore((s) => s.resolveIssue);
  const isDiagnosing = useStore((s) => s.isDiagnosing);

  const findings = report.findings ?? [];
  const logs = notableLogs(report.event_logs?.entries ?? []);

  const handleResolveEvent = (e: EventLogEntry) => {
    const when = e.time_generated ? formatDateTime(e.time_generated) : "recently";
    const issue =
      `I have a Windows ${e.level.toLowerCase()} in my ${e.log_name} event log` +
      `${e.category ? ` related to ${e.category}` : ""}. ` +
      `Source: ${e.source}${e.event_id ? `, Event ID ${e.event_id}` : ""} (occurred ${when}). ` +
      `Message: "${e.message}". ` +
      `What is causing this, and how do I resolve it?`;
    resolveIssue(issue);
  };

  return (
    <div className="mt-4 space-y-6">
      <div className="space-y-4">
        <h2 className="text-section-title border-b border-base-700/20 pb-2">
          Troubleshooter Findings ({findings.length})
        </h2>
        {findings.length === 0 ? (
          <div className="card px-5 py-8 text-center text-empty bg-base-850">
            No critical or warning issues detected by the troubleshooter.
          </div>
        ) : (
          <div className="space-y-3">
            {findings.map((f, idx) => (
              <FindingCard key={`${f.id}-${idx}`} finding={f} onAskAi={resolveIssue} busy={isDiagnosing} />
            ))}
          </div>
        )}
      </div>

      <div className="space-y-4">
        <h2 className="text-section-title border-b border-base-700/20 pb-2">
          Event Log Alerts ({logs.length})
        </h2>
        {logs.length === 0 ? (
          <div className="card px-5 py-8 text-center text-empty bg-base-850">
            No recent error or warning events in Windows event logs.
          </div>
        ) : (
          <EventLogTable entries={logs} onDiagnose={handleResolveEvent} busy={isDiagnosing} />
        )}
      </div>
    </div>
  );
}
