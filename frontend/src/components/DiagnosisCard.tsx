import type { DiagnosisResult } from "@/types";
import { SeverityBadge } from "@/components/common/SeverityBadge";
import { severityColor } from "@/lib/format";

// Icons for beautiful headings
function TargetIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2.5">
      <path strokeLinecap="round" strokeLinejoin="round" d="M12 11c0 3.517-1.009 6.799-2.753 9.571m-3.44-2.04l.054-.09A13.916 13.916 0 008 11a4 4 0 118 0c0 1.017-.07 2.019-.203 3m-2.118 6.844A21.88 21.88 0 0015.171 17m3.839 1.132c.645-2.266.99-4.659.99-7.132A8 8 0 008 4.07M3 15.364c.64-1.319 1-2.8 1-4.364 0-1.457.39-2.823 1.07-4" />
    </svg>
  );
}

function ReasoningIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2.5">
      <path strokeLinecap="round" strokeLinejoin="round" d="M9.663 17h4.673M12 3v1m6.364.364l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
    </svg>
  );
}

function GaugeIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2.5">
      <path strokeLinecap="round" strokeLinejoin="round" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
    </svg>
  );
}

function MicroscopeIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2.5">
      <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
    </svg>
  );
}

function WrenchIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2.5">
      <path strokeLinecap="round" strokeLinejoin="round" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
      <path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
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

function ShieldCheckIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2.5">
      <path strokeLinecap="round" strokeLinejoin="round" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
    </svg>
  );
}

function BookIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2.5">
      <path strokeLinecap="round" strokeLinejoin="round" d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" />
    </svg>
  );
}

function Section({
  title,
  icon: Icon,
  children,
}: {
  title: string;
  icon: React.ComponentType<{ className?: string }>;
  children: React.ReactNode;
}) {
  return (
    <div className="mt-5 pt-4 border-t border-base-700/30 first:border-0 first:mt-0 first:pt-0">
      <h4 className="mb-2.5 flex items-center gap-2 text-label">
        <Icon className="h-4 w-4 text-content-muted" />
        <span>{title}</span>
      </h4>
      {children}
    </div>
  );
}

export function DiagnosisCard({ d }: { d: DiagnosisResult }) {
  const isConversational = d.is_conversational;

  return (
    <div className="card mt-1 w-full max-w-3xl p-6 shadow-xl border border-base-700/50 bg-base-850 hover:border-base-600/40 transition-all duration-200">
      {/* Top Header Badge */}
      <div className="flex justify-between items-center gap-2">
        <SeverityBadge severity={d.severity} />
        {d.confidence !== undefined && !isConversational && (
          <div className="flex items-center gap-1.5 text-xs font-bold text-content-body">
            <span className="text-label">AI Confidence:</span>
            <span className={`text-sm ${d.confidence >= 80 ? "text-severity-healthy" : d.confidence >= 50 ? "text-severity-warning" : "text-severity-critical"}`}>
              {d.confidence}%
            </span>
          </div>
        )}
      </div>

      {/* Main Issue Title Summary */}
      {d.issue_summary && (
        <h3 className="mt-4 text-lg font-bold text-white tracking-tight leading-snug border-b border-base-700/30 pb-3">
          {d.issue_summary}
        </h3>
      )}

      {/* Root Cause Details */}
      {d.root_cause && (
        <Section title="Likely Root Cause" icon={TargetIcon}>
          <div className="rounded-xl border border-base-700/40 bg-base-900/40 px-4 py-3 text-sm text-gray-100 font-medium shadow-inner leading-relaxed">
            {d.root_cause}
          </div>
        </Section>
      )}

      {/* Logic Reasoning */}
      {d.reasoning && (
        <Section title="Engineering Reasoning" icon={ReasoningIcon}>
          <p className="whitespace-pre-wrap text-body text-content-secondary bg-base-800/10 rounded-lg">
            {d.reasoning}
          </p>
        </Section>
      )}

      {/* Confidence Reasons */}
      {d.confidence_reasons.length > 0 && (
        <Section title="Confidence Factors" icon={GaugeIcon}>
          <ul className="grid grid-cols-1 gap-2 text-caption text-content-secondary sm:grid-cols-2">
            {d.confidence_reasons.map((r, i) => (
              <li key={i} className="flex gap-2.5 items-start bg-base-800/40 border border-base-700/20 rounded-lg px-3 py-2 shadow-sm">
                <span className="text-accent text-sm leading-none font-black select-none">•</span>
                <span className="leading-normal">{r}</span>
              </li>
            ))}
          </ul>
        </Section>
      )}

      {/* Hard supporting facts */}
      {d.evidence.length > 0 && (
        <Section title="Observed Telemetry Facts" icon={MicroscopeIcon}>
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
            {d.evidence.map((e, i) => (
              <div key={i} className="flex items-center justify-between rounded-xl border border-base-700/45 bg-base-900/30 px-3.5 py-2.5 shadow-inner transition-colors hover:bg-base-900/50 duration-150">
                <span className="text-xs font-semibold text-content-body">{e.label}</span>
                <span className={`text-xs font-bold tracking-wide ${severityColor(e.severity)}`}>
                  {e.value}
                </span>
              </div>
            ))}
          </div>
        </Section>
      )}

      {/* Concrete proposed fixes */}
      {d.recommended_fixes.length > 0 && (
        <Section title="Recommended System Actions" icon={WrenchIcon}>
          <div className="space-y-3">
            {d.recommended_fixes.map((f, i) => (
              <div key={i} className="rounded-xl border border-base-700/40 bg-base-900/20 p-4 hover:bg-base-900/30 transition-all duration-150 shadow-sm relative overflow-hidden group">
                <div className="absolute top-0 left-0 h-full w-1 bg-accent/40 group-hover:bg-accent transition-colors" />
                <div className="flex items-start justify-between gap-2">
                  <span className="text-sm font-bold text-white tracking-tight">{f.title}</span>
                  {f.requires_confirmation && (
                    <span className="rounded-full bg-severity-warning/10 border border-severity-warning/20 px-2 py-0.5 text-[9px] font-bold uppercase tracking-wider text-severity-warning">
                      Needs confirmation
                    </span>
                  )}
                </div>
                <p className="mt-1.5 text-caption text-content-secondary">{f.description}</p>
                {f.safe_action && (
                  <div className="mt-2 flex items-center gap-1.5 rounded-lg bg-base-800/80 px-2.5 py-1.5 text-[11px] border border-base-700/40 font-mono text-accent">
                    <span className="text-accent/60 font-sans font-extrabold text-[10px] uppercase tracking-wider select-none">Action:</span>
                    <span className="truncate">{f.safe_action}</span>
                  </div>
                )}
              </div>
            ))}
          </div>
        </Section>
      )}

      {/* Stepper Steps resolution */}
      {d.resolution_steps.length > 0 && (
        <Section title="Step-by-Step Resolution Guide" icon={ListIcon}>
          <ol className="space-y-2.5 text-caption text-content-secondary">
            {d.resolution_steps.map((s, i) => (
              <li key={i} className="flex gap-3 items-start p-3 bg-base-900/10 border border-base-700/10 rounded-xl hover:border-base-700/30 transition-colors duration-150">
                <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-lg bg-gradient-to-tr from-accent to-blue-400 text-[10px] font-black text-white shadow-md shadow-accent/10">
                  {i + 1}
                </span>
                <span className="pt-0.5 leading-relaxed text-gray-200 font-medium">{s}</span>
              </li>
            ))}
          </ol>
        </Section>
      )}

      {/* Preventive Tips */}
      {d.prevention_tips.length > 0 && (
        <Section title="Prevention & Best Practices" icon={ShieldCheckIcon}>
          <ul className="space-y-2 text-caption text-content-secondary bg-base-900/15 border border-base-700/15 rounded-xl p-4">
            {d.prevention_tips.map((t, i) => (
              <li key={i} className="flex gap-2.5 items-start">
                <span className="text-severity-healthy text-sm font-bold select-none leading-none">✓</span>
                <span className="leading-relaxed font-medium">{t}</span>
              </li>
            ))}
          </ul>
        </Section>
      )}

      {/* Knowledge reference pills */}
      {d.knowledge_references.length > 0 && (
        <Section title="Grounded KB Documentation" icon={BookIcon}>
          <div className="flex flex-wrap gap-2">
            {d.knowledge_references.map((r) => (
              <span
                key={r.doc_id}
                title={r.snippet}
                className="rounded-xl border border-base-700 bg-base-900/20 px-3 py-1.5 text-[11px] font-semibold text-content-secondary shadow-sm flex items-center gap-1.5 hover:border-accent/40 cursor-help transition-all duration-150"
              >
                <span className="h-1.5 w-1.5 rounded-full bg-accent/70" />
                <span className="max-w-[140px] truncate text-white">{r.title}</span>
                <span className="text-content-muted font-bold select-none">·</span>
                <span className="text-label">{r.category}</span>
                <span className="rounded bg-accent/10 text-accent px-1 text-[9px] font-extrabold">{Math.round(r.score * 100)}% Match</span>
              </span>
            ))}
          </div>
        </Section>
      )}
    </div>
  );
}
