import { formatDateTime } from "@/lib/format";
import type { EventLogEntry } from "@/types";

export function EventLogTable({
  entries,
  onDiagnose,
  busy,
  limit = 15,
}: {
  entries: EventLogEntry[];
  onDiagnose: (entry: EventLogEntry) => void;
  busy?: boolean;
  limit?: number;
}) {
  if (entries.length === 0) {
    return (
      <div className="glass-card px-5 py-8 text-center text-empty">
        No recent error event logs recorded in the event log buffers.
      </div>
    );
  }

  return (
    <div className="glass-card overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs">
          <thead>
            <tr className="border-b border-white/40 bg-white/30 text-[9px] font-extrabold uppercase tracking-wider text-content-muted">
              <th className="px-4 py-3">Timestamp</th>
              <th className="px-4 py-3">Log Channel</th>
              <th className="px-4 py-3">Source & ID</th>
              <th className="px-4 py-3">Description</th>
              <th className="px-4 py-3 text-right">Actions</th>
            </tr>
          </thead>
          <tbody>
            {entries.slice(0, limit).map((e, idx) => (
              <tr key={idx} className="border-b border-white/30 transition-colors last:border-0 hover:bg-white/35">
                <td className="whitespace-nowrap px-4 py-3 font-medium text-content-body">
                  {e.time_generated ? formatDateTime(e.time_generated) : "Unknown"}
                </td>
                <td className="whitespace-nowrap px-4 py-3 font-bold text-content-secondary">{e.log_name}</td>
                <td className="whitespace-nowrap px-4 py-3 font-mono text-content-secondary">
                  {e.source} <span className="select-none font-bold text-content-muted">·</span>{" "}
                  <span className="font-semibold text-accent">ID {e.event_id}</span>
                </td>
                <td className="max-w-[280px] truncate px-4 py-3 font-medium text-content-body" title={e.message}>
                  {e.message}
                </td>
                <td className="whitespace-nowrap px-4 py-3 text-right">
                  <button
                    onClick={() => onDiagnose(e)}
                    disabled={busy}
                    className="rounded-lg border border-accent/25 bg-accent/10 px-2.5 py-1 text-[10px] font-bold uppercase tracking-wider text-accent transition-all hover:bg-accent/18 active:scale-95 disabled:opacity-50"
                  >
                    Diagnose
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
