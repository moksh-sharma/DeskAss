import { useState } from "react";
import { severityColor } from "@/lib/format";
import type { TroubleshooterFinding } from "@/types";

function ShieldAlertIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2.5">
      <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
    </svg>
  );
}

function ListIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2.5">
      <path strokeLinecap="round" strokeLinejoin="round" d="M4 6h16M4 12h16M4 18h7" />
    </svg>
  );
}

function AskIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2.5">
      <path strokeLinecap="round" strokeLinejoin="round" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
    </svg>
  );
}

export function FindingCard({
  finding,
  onAskAi,
  busy,
}: {
  finding: TroubleshooterFinding;
  onAskAi: (prompt: string) => void;
  busy: boolean;
}) {
  const [open, setOpen] = useState(true);
  const accentBorder =
    finding.severity === "Critical"
      ? "border-severity-critical/40 shadow-severity-critical/5 bg-gradient-to-r from-severity-critical/5 to-transparent"
      : finding.severity === "Warning"
        ? "border-severity-warning/40 shadow-severity-warning/5 bg-gradient-to-r from-severity-warning/5 to-transparent"
        : "border-base-700 bg-base-850";

  return (
    <div className={`card border ${accentBorder} p-5 hover:border-base-600 transition-all duration-200 relative overflow-hidden group`}>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className={`text-sm font-bold tracking-tight ${severityColor(finding.severity)}`}>
              {finding.title}
            </span>
            <span className="rounded-full bg-base-700 px-2 py-0.5 text-[9px] font-extrabold uppercase tracking-widest text-content-body border border-base-600/30">
              {finding.area}
            </span>
          </div>
          <p className="mt-1.5 text-caption text-content-secondary">{finding.detected}</p>
        </div>
        <button
          onClick={() => setOpen((v) => !v)}
          className="shrink-0 px-2.5 py-1 text-[11px] font-bold uppercase text-accent hover:bg-accent/10 border border-transparent hover:border-accent/20 rounded-lg transition-colors select-none"
        >
          {open ? "Collapse" : "Expand"}
        </button>
      </div>

      {open && (
        <div className="mt-4 pt-4 border-t border-base-700/30 space-y-4">
          {finding.likely_cause && (
            <div>
              <h5 className="text-label flex items-center gap-1.5">
                <ShieldAlertIcon className="h-3.5 w-3.5 text-content-muted" />
                Likely Cause
              </h5>
              <p className="mt-1 text-caption text-content-secondary">{finding.likely_cause}</p>
            </div>
          )}

          {finding.resolution_steps.length > 0 && (
            <div>
              <h5 className="text-label flex items-center gap-1.5">
                <ListIcon className="h-3.5 w-3.5 text-content-muted" />
                Actionable Fix Steps
              </h5>
              <ol className="mt-2 space-y-1.5">
                {finding.resolution_steps.map((s, i) => (
                  <li key={i} className="flex items-start gap-2.5 rounded-xl border border-base-700 bg-base-750 p-2.5">
                    <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-lg bg-accent text-[10px] font-black text-white shadow-sm shadow-accent/10 select-none">
                      {i + 1}
                    </span>
                    <span className="pt-0.5 text-caption text-content-secondary">{s}</span>
                  </li>
                ))}
              </ol>
            </div>
          )}

          {finding.references && finding.references.length > 0 && (
            <div className="flex flex-wrap gap-2 pt-1">
              {finding.references.map((r) => (
                <span
                  key={r.doc_id}
                  title={r.snippet}
                  className="rounded-xl border border-base-700 bg-base-900/30 px-3 py-1 text-[10px] font-semibold text-content-body shadow-sm"
                >
                  📄 {r.title}
                </span>
              ))}
            </div>
          )}

          <div className="pt-1">
            <button
              onClick={() => onAskAi(finding.ask_ai_prompt)}
              disabled={busy || !finding.ask_ai_prompt}
              className="rounded-xl bg-accent px-4 py-2 text-xs font-bold uppercase tracking-wider text-white shadow-md shadow-accent/10 hover:shadow-accent/20 transition-all hover:-translate-y-px active:translate-y-0 disabled:opacity-50 disabled:pointer-events-none flex items-center gap-2"
            >
              <AskIcon className="h-4 w-4" />
              Ask AI for Detailed Fix
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
