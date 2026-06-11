import { useMemo } from "react";
import { useStore } from "@/store/useStore";
import { LenisScroll } from "@/components/LenisScroll";
import { IssueScanDetails } from "@/components/IssueScanDetails";
import type { ChatMessage, InvestigationReport } from "@/types";

function ScanIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4"
      />
    </svg>
  );
}

type ScanEntry = { messageId: string; report: InvestigationReport };

function collectInvestigations(messages: ChatMessage[]): ScanEntry[] {
  const entries: ScanEntry[] = [];
  for (const m of messages) {
    if (m.investigation) {
      entries.push({ messageId: m.id, report: m.investigation });
    }
  }
  return entries;
}

export function IssueScanSidebar() {
  const messages = useStore((s) => s.messages);
  const isDiagnosing = useStore((s) => s.isDiagnosing);

  const scans = useMemo(() => collectInvestigations(messages), [messages]);
  const hasScans = scans.length > 0;

  return (
    <aside className="flex h-full w-72 shrink-0 flex-col border-l border-base-700/60 bg-base-850 shadow-xl">
      <div className="flex items-center gap-3 border-b border-base-700/40 bg-base-800/20 px-5 py-5">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-gradient-to-tr from-emerald-500 to-teal-400 text-white shadow-lg shadow-emerald-500/15">
          <ScanIcon className="h-5 w-5" />
        </div>
        <div className="min-w-0">
          <div className="truncate text-sm font-extrabold tracking-wide text-white">Issue Scan</div>
          <div className="mt-0.5 flex items-center gap-1.5 text-[11px] font-medium text-content-body">
            {isDiagnosing ? (
              <>
                <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-accent" />
                Scanning…
              </>
            ) : hasScans ? (
              <>
                <span className="h-1.5 w-1.5 rounded-full bg-severity-healthy" />
                {scans.length} issue scan{scans.length === 1 ? "" : "s"}
              </>
            ) : (
              <>
                <span className="h-1.5 w-1.5 rounded-full bg-base-600" />
                Awaiting issue
              </>
            )}
          </div>
        </div>
      </div>

      <LenisScroll className="min-h-0 flex-1" contentClassName="px-4 py-4">
        {isDiagnosing && (
          <div className="mb-4 flex flex-col items-center justify-center rounded-xl border border-base-700/30 bg-base-900/20 px-3 py-8 text-center">
            <div className="h-8 w-8 animate-spin rounded-full border-2 border-accent/30 border-t-accent" />
            <p className="mt-4 text-xs font-semibold text-content-secondary">
              Running issue scan…
            </p>
            <p className="mt-1 text-[11px] text-content-muted">
              Checks for your latest issue will appear below when ready.
            </p>
          </div>
        )}

        {!isDiagnosing && !hasScans && (
          <div className="px-2 py-10 text-center text-empty">
            Describe an issue in chat to run a targeted scan. Each issue you report will appear
            here with its scan results.
          </div>
        )}

        {hasScans && (
          <div className="space-y-4">
            {scans.length > 1 && (
              <h4 className="text-label px-1">All issue scans</h4>
            )}
            {scans.map((entry, index) => (
              <IssueScanDetails
                key={entry.messageId}
                report={entry.report}
                showHeading={scans.length === 1}
                scanIndex={scans.length > 1 ? index + 1 : undefined}
              />
            ))}
          </div>
        )}
      </LenisScroll>
    </aside>
  );
}
