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
    <aside className="glass-sidebar flex h-full w-72 shrink-0 flex-col border-l">
      <div className="flex items-center gap-3 border-b border-white/40 px-5 py-5">
        <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-gradient-to-br from-emerald-400 to-teal-500 text-white shadow-glow-sm">
          <ScanIcon className="h-5 w-5" />
        </div>
        <div className="min-w-0">
          <div className="truncate text-sm font-extrabold tracking-tight text-content-primary">Issue Scan</div>
          <div className="mt-0.5 flex items-center gap-1.5 text-[11px] font-medium text-content-muted">
            {isDiagnosing ? (
              <>
                <span className="h-2 w-2 animate-pulse rounded-full bg-accent" />
                Scanning…
              </>
            ) : hasScans ? (
              <>
                <span className="h-2 w-2 rounded-full bg-severity-healthy" />
                {scans.length} issue scan{scans.length === 1 ? "" : "s"}
              </>
            ) : (
              <>
                <span className="h-2 w-2 rounded-full bg-content-faint/50" />
                Awaiting issue
              </>
            )}
          </div>
        </div>
      </div>

      <LenisScroll className="min-h-0 flex-1" contentClassName="px-4 py-4">
        {!isDiagnosing && !hasScans && (
          <div className="px-2 py-10 text-center text-empty">
            Describe an issue in chat to run a targeted scan. Each issue you report will appear here with its scan
            results.
          </div>
        )}

        {hasScans && (
          <div className="space-y-4">
            {scans.length > 1 && <h4 className="text-label px-1">All issue scans</h4>}
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
