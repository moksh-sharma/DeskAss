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
  const [open, setOpen] = useState(false);
  const accentBorder =
    finding.severity === "Critical"
      ? "border-red-200/60 bg-gradient-to-r from-red-50/60 to-white/30"
      : finding.severity === "Warning"
        ? "border-amber-200/60 bg-gradient-to-r from-amber-50/60 to-white/30"
        : "border-white/55";

  return (
    <div className={`card relative overflow-hidden border transition-all duration-200 ${accentBorder}`}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-start justify-between gap-3 px-5 py-4 text-left transition-colors hover:bg-white/25"
      >
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className={`text-sm font-bold tracking-tight ${severityColor(finding.severity)}`}>
              {finding.title}
            </span>
            <span className="rounded-full border border-white/60 bg-white/50 px-2 py-0.5 text-[9px] font-extrabold uppercase tracking-widest text-content-muted backdrop-blur-sm">
              {finding.area}
            </span>
          </div>
          <p className="mt-1.5 whitespace-normal break-words text-caption">{finding.detected}</p>
        </div>
        <span
          className={`mt-1 shrink-0 text-[10px] font-extrabold text-content-faint transition-transform duration-200 ${
            open ? "rotate-180" : ""
          }`}
        >
          ▼
        </span>
      </button>

      {open && (
        <div className="space-y-4 border-t border-white/40 px-5 py-4">
          {finding.likely_cause && (
            <div>
              <h5 className="text-label flex items-center gap-1.5">
                <ShieldAlertIcon className="h-3.5 w-3.5 text-content-muted" />
                Likely Cause
              </h5>
              <p className="mt-1 whitespace-normal break-words text-caption">{finding.likely_cause}</p>
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
                  <li key={i} className="flex items-start gap-2.5 rounded-xl border border-white/50 bg-white/35 p-2.5 backdrop-blur-sm">
                    <span className="flex h-5 w-5 shrink-0 select-none items-center justify-center rounded-lg bg-accent-shine text-[10px] font-black text-white shadow-glow-sm">
                      {i + 1}
                    </span>
                    <span className="whitespace-normal break-words pt-0.5 text-caption">{s}</span>
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
                  className="rounded-xl border border-white/55 bg-white/40 px-3 py-1 text-[10px] font-semibold text-content-body shadow-glass-sm backdrop-blur-sm"
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
              className="btn-primary flex items-center gap-2 px-4 py-2 text-xs disabled:pointer-events-none"
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
