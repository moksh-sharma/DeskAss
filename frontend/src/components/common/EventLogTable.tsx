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
      <div className="card px-5 py-8 text-center text-empty bg-base-850">
        No recent error event logs recorded in the event log buffers.
      </div>
    );
  }

  return (
    <div className="card overflow-hidden bg-base-850">
      <div className="overflow-x-auto">
        <table className="w-full text-xs text-left">
          <thead>
            <tr className="text-content-muted border-b border-base-700 font-extrabold uppercase tracking-wider text-[9px] bg-base-800/20">
              <th className="px-4 py-3">Timestamp</th>
              <th className="px-4 py-3">Log Channel</th>
              <th className="px-4 py-3">Source & ID</th>
              <th className="px-4 py-3">Description</th>
              <th className="px-4 py-3 text-right">Actions</th>
            </tr>
          </thead>
          <tbody>
            {entries.slice(0, limit).map((e, idx) => (
              <tr key={idx} className="border-b border-base-700/40 last:border-0 hover:bg-base-800/30 transition-colors">
                <td className="px-4 py-3 text-content-body font-medium whitespace-nowrap">
                  {e.time_generated ? formatDateTime(e.time_generated) : "Unknown"}
                </td>
                <td className="px-4 py-3 text-content-secondary font-bold whitespace-nowrap">{e.log_name}</td>
                <td className="px-4 py-3 text-content-secondary font-mono whitespace-nowrap">
                  {e.source} <span className="text-content-muted font-bold select-none">·</span>{" "}
                  <span className="text-accent font-semibold">ID {e.event_id}</span>
                </td>
                <td className="px-4 py-3 text-content-body font-medium max-w-[280px] truncate" title={e.message}>
                  {e.message}
                </td>
                <td className="px-4 py-3 text-right whitespace-nowrap">
                  <button
                    onClick={() => onDiagnose(e)}
                    disabled={busy}
                    className="rounded-lg bg-accent/10 hover:bg-accent/20 border border-accent/20 text-accent px-2.5 py-1 text-[10px] font-bold uppercase tracking-wider transition-all hover:-translate-y-px active:scale-95 duration-100 disabled:opacity-50"
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
