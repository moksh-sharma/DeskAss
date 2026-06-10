import { useStore } from "@/store/useStore";
import { api } from "@/api/client";
import { LenisScroll } from "@/components/LenisScroll";
import { formatDateTime } from "@/lib/format";

function scanStatusColor(status: string): string {
  const s = (status || "").toLowerCase();
  if (s === "critical") return "text-severity-critical font-semibold";
  if (s === "warning") return "text-severity-warning font-semibold";
  return "text-severity-healthy font-semibold";
}

// Inline SVGs for beautiful design
function TrashIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
      <path strokeLinecap="round" strokeLinejoin="round" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
    </svg>
  );
}

function PdfIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
      <path strokeLinecap="round" strokeLinejoin="round" d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
    </svg>
  );
}

function JsonIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
      <path strokeLinecap="round" strokeLinejoin="round" d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4" />
    </svg>
  );
}

function ChatIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
      <path strokeLinecap="round" strokeLinejoin="round" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
    </svg>
  );
}

function CpuIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
      <rect x="4" y="4" width="16" height="16" rx="2" />
      <path d="M9 9h6v6H9z" />
      <path d="M9 1v3M15 1v3M9 20v3M15 20v3M20 9h3M20 15h3M1 9h3M1 15h3" />
    </svg>
  );
}

function GridIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
      <path strokeLinecap="round" strokeLinejoin="round" d="M4 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2V6zM14 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V6zM4 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2v-2zM14 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2z" />
    </svg>
  );
}

export function Sidebar() {
  const sessions = useStore((s) => s.sessions);
  const currentSessionId = useStore((s) => s.currentSessionId);
  const newSession = useStore((s) => s.newSession);
  const loadSession = useStore((s) => s.loadSession);
  const removeSession = useStore((s) => s.removeSession);
  const machineScanHistory = useStore((s) => s.machineScanHistory);
  const currentMachineScanId = useStore((s) => s.currentMachineScanId);
  const loadMachineScan = useStore((s) => s.loadMachineScan);
  const removeMachineScan = useStore((s) => s.removeMachineScan);
  const runMachineScan = useStore((s) => s.runMachineScan);
  const isMachineScanning = useStore((s) => s.isMachineScanning);
  const setView = useStore((s) => s.setView);

  return (
    <aside className="flex h-full w-72 shrink-0 flex-col border-r border-base-700/60 bg-base-850 shadow-xl">
      {/* Branding Header */}
      <div className="flex items-center gap-3 px-5 py-5 border-b border-base-700/40 bg-base-800/20">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-gradient-to-tr from-accent to-blue-400 text-xl font-black text-white shadow-lg shadow-accent/15 transition-transform hover:scale-105 duration-200">
          C
        </div>
        <div className="min-w-0">
          <div className="text-sm font-extrabold text-white tracking-wide truncate">Cache AI Assistant</div>
          <div className="text-[11px] text-content-body font-medium flex items-center gap-1.5 mt-0.5">
            <span className="h-1.5 w-1.5 rounded-full bg-green-500 animate-pulse"></span>
            IT Support Engineer
          </div>
        </div>
      </div>

      {/* Main Actions Box */}
      <div className="p-4 space-y-2 border-b border-base-700/30">
        <button
          onClick={newSession}
          className="btn-primary w-full shadow-lg shadow-accent/10 hover:shadow-accent/20 flex items-center justify-center gap-2 py-2.5 rounded-lg text-sm font-semibold transition-all hover:-translate-y-px active:translate-y-0 duration-150"
        >
          <ChatIcon className="h-4 w-4" />
          + New Session
        </button>
        <button
          onClick={runMachineScan}
          disabled={isMachineScanning}
          className="btn-ghost w-full flex items-center justify-center gap-2 py-2.5 rounded-lg text-sm font-medium border border-base-700/60 hover:border-base-600 transition-all active:scale-[0.98] duration-150"
        >
          <CpuIcon className={`h-4 w-4 ${isMachineScanning ? "animate-spin text-accent" : "text-gray-400"}`} />
          {isMachineScanning ? "Scanning System…" : "Full System Scan"}
        </button>
        <button
          onClick={() => setView("dashboard")}
          className="btn-ghost w-full flex items-center justify-center gap-2 py-2.5 rounded-lg text-sm font-medium border border-base-700/60 hover:border-base-600 transition-all active:scale-[0.98] duration-150"
        >
          <GridIcon className="h-4 w-4 text-gray-400" />
          System Dashboard
        </button>
      </div>

      {/* Scrollable History lists */}
      <div className="flex min-h-0 flex-1 flex-col py-3 space-y-4">
        
        {/* Session History */}
        <div className="flex flex-col min-h-0 flex-1">
          <div className="px-5 text-label flex items-center justify-between">
            <span>Session History</span>
            <span className="rounded-full bg-base-700/60 px-2 py-0.5 text-[9px] font-medium text-content-body">
              {sessions.length}
            </span>
          </div>
          <LenisScroll className="mt-2 min-h-0 flex-1" contentClassName="px-2 space-y-1">
            {sessions.length === 0 ? (
              <div className="px-3 py-6 text-center text-empty">No sessions yet.</div>
            ) : (
              sessions.map((s) => (
                <div
                  key={s.id}
                  className={`group relative mb-0.5 cursor-pointer rounded-lg px-3 py-2.5 transition-all duration-150 ${
                    currentSessionId === s.id
                      ? "bg-base-700/90 text-white shadow-md border-l-2 border-accent"
                      : "hover:bg-base-750 text-content-body"
                  }`}
                  onClick={() => loadSession(s.id)}
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="truncate text-xs font-semibold">{s.title || "Untitled Session"}</span>
                    {/* Hover actions */}
                    <div className="flex shrink-0 items-center gap-1 opacity-0 transition-opacity group-hover:opacity-100 z-10">
                      <a
                        href={api.exportSessionUrl(s.id, "pdf")}
                        onClick={(e) => e.stopPropagation()}
                        className="rounded p-1 bg-base-800/80 text-gray-400 hover:text-accent hover:bg-base-700 transition-colors"
                        title="Export PDF"
                      >
                        <PdfIcon className="h-3.5 w-3.5" />
                      </a>
                      <a
                        href={api.exportSessionUrl(s.id, "json")}
                        onClick={(e) => e.stopPropagation()}
                        className="rounded p-1 bg-base-800/80 text-gray-400 hover:text-accent hover:bg-base-700 transition-colors"
                        title="Export JSON"
                      >
                        <JsonIcon className="h-3.5 w-3.5" />
                      </a>
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          removeSession(s.id);
                        }}
                        className="rounded p-1 bg-base-800/80 text-gray-400 hover:text-severity-critical hover:bg-base-700 transition-colors"
                        title="Delete Session"
                      >
                        <TrashIcon className="h-3.5 w-3.5" />
                      </button>
                    </div>
                  </div>
                  <div className="mt-1 flex items-center justify-between text-[10px] text-content-muted">
                    <span className="font-medium">{s.message_count} messages</span>
                    <span>{formatDateTime(s.updated_at)}</span>
                  </div>
                </div>
              ))
            )}
          </LenisScroll>
        </div>

        {/* Full Scan History */}
        <div className="flex flex-col min-h-0 flex-1 border-t border-base-700/20 pt-3">
          <div className="px-5 text-label flex items-center justify-between">
            <span>Full Scan History</span>
            <span className="rounded-full bg-base-700/60 px-2 py-0.5 text-[9px] font-medium text-content-body">
              {machineScanHistory.length}
            </span>
          </div>
          <LenisScroll className="mt-2 min-h-0 flex-1" contentClassName="px-2 pb-4 space-y-1">
            <button
              onClick={runMachineScan}
              disabled={isMachineScanning}
              className="btn-ghost mb-2 w-full text-xs font-semibold flex items-center justify-center gap-1.5 py-1.5 border border-dashed border-base-700 hover:border-base-600 rounded-lg text-content-body"
            >
              <CpuIcon className={`h-3.5 w-3.5 ${isMachineScanning ? "animate-spin text-accent" : ""}`} />
              {isMachineScanning ? "Scanning PC…" : "+ New Full Scan"}
            </button>
            {machineScanHistory.length === 0 ? (
              <div className="px-3 py-6 text-center text-empty">No scans saved yet.</div>
            ) : (
              machineScanHistory.map((s) => (
                <div
                  key={s.id}
                  className={`group relative mb-0.5 cursor-pointer rounded-lg px-3 py-2.5 transition-all duration-150 ${
                    currentMachineScanId === s.id
                      ? "bg-base-700/90 text-white shadow-md border-l-2 border-accent"
                      : "hover:bg-base-750 text-content-body"
                  }`}
                  onClick={() => loadMachineScan(s.id)}
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="truncate text-xs font-semibold">{s.title}</span>
                    <div className="flex shrink-0 items-center gap-1">
                      {s.has_ai_summary && (
                        <span className="rounded bg-accent/15 px-1.5 py-0.5 text-[8px] font-bold uppercase tracking-wider text-accent border border-accent/20">
                          AI
                        </span>
                      )}
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          removeMachineScan(s.id);
                        }}
                        className="rounded p-1 text-gray-400 opacity-0 transition-opacity bg-base-800/80 hover:text-severity-critical hover:bg-base-700 group-hover:opacity-100 z-10"
                        title="Delete Scan"
                      >
                        <TrashIcon className="h-3.5 w-3.5" />
                      </button>
                    </div>
                  </div>
                  <div className="mt-1 flex items-center justify-between text-[10px] text-content-muted">
                    <span className={scanStatusColor(s.health_status)}>
                      {s.health_score}/100 · {Math.round(s.scan_duration_seconds)}s
                    </span>
                    <span>{formatDateTime(s.scanned_at)}</span>
                  </div>
                </div>
              ))
            )}
          </LenisScroll>
        </div>

      </div>
    </aside>
  );
}
