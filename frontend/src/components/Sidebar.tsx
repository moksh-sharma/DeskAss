import { useStore } from "@/store/useStore";
import { api } from "@/api/client";
import { LenisScroll } from "@/components/LenisScroll";
import { formatDateTime } from "@/lib/format";
import { useState, type ReactNode } from "react";

function scanStatusColor(status: string): string {
  const s = (status || "").toLowerCase();
  if (s === "critical") return "text-severity-critical font-semibold";
  if (s === "warning") return "text-severity-warning font-semibold";
  return "text-severity-healthy font-semibold";
}

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

function BoltIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2.5">
      <path strokeLinecap="round" strokeLinejoin="round" d="M13 10V3L4 14h7v7l9-11h-7z" />
    </svg>
  );
}

function HistoryIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
      <path strokeLinecap="round" strokeLinejoin="round" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
    </svg>
  );
}

function ScanIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
      <path strokeLinecap="round" strokeLinejoin="round" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4" />
    </svg>
  );
}

function ChevronLeftIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2.5">
      <path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" />
    </svg>
  );
}

function ChevronRightIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2.5">
      <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
    </svg>
  );
}

function SectionHead({
  icon,
  iconVariant,
  titleVariant,
  title,
  badge,
}: {
  icon: ReactNode;
  iconVariant: "violet" | "sky" | "emerald";
  titleVariant: "violet" | "sky" | "emerald";
  title: string;
  badge?: ReactNode;
}) {
  return (
    <div className="sidebar-section-head">
      <div className={`sidebar-section-head-icon sidebar-section-head-icon--${iconVariant}`}>{icon}</div>
      <span className={`sidebar-section-title sidebar-section-title--${titleVariant}`}>{title}</span>
      {badge}
    </div>
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
  const view = useStore((s) => s.view);
  const [collapsed, setCollapsed] = useState(false);

  return (
    <div
      className={`relative h-full shrink-0 transition-[width] duration-300 ease-in-out ${
        collapsed ? "w-12" : "w-72"
      }`}
    >
      <aside
        className={`glass-sidebar flex h-full flex-col border-r transition-[width] duration-300 ease-in-out ${
          collapsed ? "w-12 items-center" : "w-72"
        }`}
      >
        {collapsed ? (
          /* Collapsed rail — toggle stays inside sidebar */
          <div className="flex w-full flex-col items-center gap-3 pt-4">
            <button
              type="button"
              onClick={() => setCollapsed(false)}
              className="flex h-9 w-9 items-center justify-center rounded-xl border border-white/70 bg-white/75 text-content-muted shadow-glass-sm backdrop-blur-md transition-all hover:bg-white hover:text-accent"
              title="Open sidebar"
              aria-label="Open sidebar"
              aria-expanded={false}
            >
              <ChevronRightIcon className="h-4 w-4" />
            </button>
            <button
              type="button"
              onClick={() => {
                setCollapsed(false);
                setView("chat");
              }}
              className="flex h-9 w-9 items-center justify-center rounded-xl bg-accent-shine text-sm font-black text-white shadow-glow-sm"
              title="HelpDesk Assistant"
            >
              H
            </button>
          </div>
        ) : (
          <>
      {/* ── Zone 1: Brand identity ── */}
      <div className="sidebar-brand-zone relative shrink-0">
        <button
          type="button"
          onClick={() => setCollapsed(true)}
          className="absolute right-3 top-1/2 z-10 flex h-8 w-8 -translate-y-1/2 items-center justify-center rounded-xl border border-white/70 bg-white/75 text-content-muted shadow-glass-sm backdrop-blur-md transition-all hover:bg-white hover:text-accent"
          title="Close sidebar"
          aria-label="Close sidebar"
          aria-expanded={true}
        >
          <ChevronLeftIcon className="h-4 w-4" />
        </button>
        <button
          type="button"
          onClick={() => setView("chat")}
          className={`flex w-full items-center gap-3 px-5 py-5 pr-12 text-left transition-colors hover:bg-white/30 ${
            view === "chat" ? "bg-white/20" : ""
          }`}
        >
          <div className="relative flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-accent-shine text-lg font-black text-white shadow-glow-sm transition-transform duration-300 hover:scale-105">
            H
            <span className="absolute -bottom-0.5 -right-0.5 h-3 w-3 rounded-full border-2 border-white bg-severity-healthy" />
          </div>
          <div className="min-w-0">
            <div className="truncate text-sm font-extrabold tracking-tight text-content-primary">
              HelpDesk Assistant
            </div>
            <div className="mt-0.5 flex items-center gap-1.5 text-[11px] font-medium text-indigo-600/80">
              <span className="relative flex h-2 w-2">
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-severity-healthy opacity-60" />
                <span className="relative inline-flex h-2 w-2 rounded-full bg-severity-healthy" />
              </span>
              IT Support Engineer
            </div>
          </div>
        </button>
      </div>

      {/* ── Zone 2: Quick actions ── */}
      <div className="sidebar-actions-zone shrink-0">
        <SectionHead
          icon={<BoltIcon className="h-3.5 w-3.5" />}
          iconVariant="violet"
          titleVariant="violet"
          title="Quick Actions"
        />
        <div className="mt-1 space-y-1.5">
          <button onClick={newSession} className="btn-primary w-full py-2.5 text-sm font-semibold normal-case tracking-normal">
            <ChatIcon className="h-4 w-4" />
            New Session
          </button>
          <button
            onClick={runMachineScan}
            disabled={isMachineScanning}
            className={`btn-ghost w-full py-2.5 text-sm font-medium normal-case tracking-normal ${
              view === "machine-scan" ? "border-violet-300/50 bg-violet-100/40 text-violet-700" : ""
            }`}
          >
            <CpuIcon className={`h-4 w-4 ${isMachineScanning ? "animate-spin text-accent" : "text-content-muted"}`} />
            {isMachineScanning ? "Scanning System…" : "Full System Scan"}
          </button>
          <button
            onClick={() => setView("dashboard")}
            className={`btn-ghost w-full py-2.5 text-sm font-medium normal-case tracking-normal ${
              view === "dashboard" ? "border-violet-300/50 bg-violet-100/40 text-violet-700" : ""
            }`}
          >
            <GridIcon className="h-4 w-4 text-content-muted" />
            System Dashboard
          </button>
        </div>
      </div>

      <div className="sidebar-divider-ornament shrink-0">
        <span className="text-[8px] font-bold uppercase tracking-[0.2em] text-content-faint">History</span>
      </div>

      {/* ── Zone 3: Session history ── */}
      <div className="sidebar-sessions-zone flex min-h-0 flex-1 flex-col">
        <SectionHead
          icon={<HistoryIcon className="h-3.5 w-3.5" />}
          iconVariant="sky"
          titleVariant="sky"
          title="Session History"
          badge={<span className="sidebar-count-badge sidebar-count-badge--sky">{sessions.length}</span>}
        />
        <LenisScroll className="min-h-0 flex-1" contentClassName="px-2 pb-1 space-y-1">
          {sessions.length === 0 ? (
            <div className="px-3 py-5 text-center text-[11px] italic text-sky-700/60">No sessions yet.</div>
          ) : (
            sessions.map((s) => (
              <div
                key={s.id}
                className={`session-item group ${currentSessionId === s.id ? "session-item-active" : "session-item-inactive"}`}
                onClick={() => loadSession(s.id)}
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="truncate text-xs font-semibold">{s.title || "Untitled Session"}</span>
                  <div className="z-10 flex shrink-0 items-center gap-1 opacity-0 transition-opacity group-hover:opacity-100">
                    <a
                      href={api.exportSessionUrl(s.id, "pdf")}
                      onClick={(e) => e.stopPropagation()}
                      className="rounded-lg bg-white/60 p-1 text-content-muted backdrop-blur-sm transition-colors hover:bg-white/90 hover:text-sky-600"
                      title="Export PDF"
                    >
                      <PdfIcon className="h-3.5 w-3.5" />
                    </a>
                    <a
                      href={api.exportSessionUrl(s.id, "json")}
                      onClick={(e) => e.stopPropagation()}
                      className="rounded-lg bg-white/60 p-1 text-content-muted backdrop-blur-sm transition-colors hover:bg-white/90 hover:text-sky-600"
                      title="Export JSON"
                    >
                      <JsonIcon className="h-3.5 w-3.5" />
                    </a>
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        removeSession(s.id);
                      }}
                      className="rounded-lg bg-white/60 p-1 text-content-muted backdrop-blur-sm transition-colors hover:bg-white/90 hover:text-severity-critical"
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

      {/* ── Zone 4: Full scan history ── */}
      <div className="sidebar-scans-zone mt-2 flex min-h-0 flex-1 flex-col">
        <SectionHead
          icon={<ScanIcon className="h-3.5 w-3.5" />}
          iconVariant="emerald"
          titleVariant="emerald"
          title="Full Scan History"
          badge={<span className="sidebar-count-badge sidebar-count-badge--emerald">{machineScanHistory.length}</span>}
        />
        <LenisScroll className="min-h-0 flex-1" contentClassName="px-2 pb-3 space-y-1">
          <button
            onClick={runMachineScan}
            disabled={isMachineScanning}
            className="btn-ghost mb-1.5 w-full border border-dashed border-emerald-300/50 bg-emerald-50/30 py-1.5 text-xs font-semibold normal-case tracking-normal text-emerald-700/80 hover:border-emerald-400/60 hover:bg-emerald-50/50"
          >
            <CpuIcon className={`h-3.5 w-3.5 ${isMachineScanning ? "animate-spin text-emerald-600" : ""}`} />
            {isMachineScanning ? "Scanning PC…" : "+ New Full Scan"}
          </button>
          {machineScanHistory.length === 0 ? (
            <div className="px-3 py-5 text-center text-[11px] italic text-emerald-700/60">No scans saved yet.</div>
          ) : (
            machineScanHistory.map((s) => (
              <div
                key={s.id}
                className={`session-item group ${
                  currentMachineScanId === s.id ? "session-item-active scan-item-active" : "session-item-inactive"
                }`}
                onClick={() => loadMachineScan(s.id)}
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="truncate text-xs font-semibold">{s.title}</span>
                  <div className="flex shrink-0 items-center gap-1">
                    {s.has_ai_summary && (
                      <span className="rounded-full border border-emerald-300/40 bg-emerald-100/60 px-1.5 py-0.5 text-[8px] font-bold uppercase tracking-wider text-emerald-700">
                        AI
                      </span>
                    )}
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        removeMachineScan(s.id);
                      }}
                      className="z-10 rounded-lg bg-white/60 p-1 text-content-muted opacity-0 backdrop-blur-sm transition-all hover:bg-white/90 hover:text-severity-critical group-hover:opacity-100"
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
          </>
        )}
    </aside>
    </div>
  );
}
