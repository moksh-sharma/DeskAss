import type { DiagnosisResult } from "@/types";
import { SeverityBadge } from "@/components/common/SeverityBadge";
import { VisualGuideSection } from "@/components/VisualGuideSection";

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
    <div className="mt-5 border-t border-white/40 pt-4 first:mt-0 first:border-0 first:pt-0">
      <h4 className="mb-2.5 flex items-center gap-2 text-label">
        <Icon className="h-4 w-4 text-accent/70" />
        <span>{title}</span>
      </h4>
      {children}
    </div>
  );
}

function issueDetailsText(d: DiagnosisResult): string {
  const parts: string[] = [];
  if (d.issue_summary?.trim()) parts.push(d.issue_summary.trim());
  if (d.root_cause?.trim() && d.root_cause.trim() !== d.issue_summary?.trim()) {
    parts.push(d.root_cause.trim());
  }
  if (parts.length === 0 && d.reasoning?.trim()) parts.push(d.reasoning.trim());
  return parts.join(" ");
}

export function DiagnosisCard({ d }: { d: DiagnosisResult }) {
  const isConversational = d.is_conversational;
  const issueText = issueDetailsText(d);

  return (
    <div className="glass-card mt-1 w-full max-w-3xl p-6">
      <div className="flex items-center justify-between gap-2">
        <SeverityBadge severity={d.severity} />
      </div>

      {issueText && !isConversational && (
        <div className="mt-4">
          <h4 className="text-label">Issue Details</h4>
          <p className="mt-2.5 rounded-xl border border-white/60 bg-white/45 px-4 py-3 text-sm font-medium leading-relaxed text-content-primary backdrop-blur-sm">
            {issueText}
          </p>
        </div>
      )}

      {isConversational && d.issue_summary && (
        <p className="mt-4 text-sm leading-relaxed text-content-primary">{d.issue_summary}</p>
      )}

      {d.recommended_fixes.length > 0 && (
        <Section title="Recommended System Actions" icon={WrenchIcon}>
          <div className="space-y-3">
            {d.recommended_fixes.map((f, i) => (
              <div
                key={i}
                className="group relative overflow-hidden rounded-xl border border-white/55 bg-white/38 p-4 backdrop-blur-sm transition-all duration-200 hover:bg-white/55"
              >
                <div className="absolute left-0 top-0 h-full w-1 bg-gradient-to-b from-accent to-accent-light transition-colors group-hover:from-accent-hover group-hover:to-accent" />
                <div className="flex items-start justify-between gap-2">
                  <span className="text-sm font-bold tracking-tight text-content-primary">{f.title}</span>
                  {f.requires_confirmation && (
                    <span className="rounded-full border border-amber-200/60 bg-amber-50/80 px-2 py-0.5 text-[9px] font-bold uppercase tracking-wider text-severity-warning">
                      Needs confirmation
                    </span>
                  )}
                </div>
                <p className="mt-1.5 text-caption">{f.description}</p>
                {f.safe_action && (
                  <div className="mt-2 flex items-center gap-1.5 rounded-lg border border-accent/20 bg-accent/5 px-2.5 py-1.5 font-mono text-[11px] text-accent">
                    <span className="select-none font-sans text-[10px] font-extrabold uppercase tracking-wider text-accent/60">
                      Action:
                    </span>
                    <span className="truncate">{f.safe_action}</span>
                  </div>
                )}
              </div>
            ))}
          </div>
        </Section>
      )}

      {d.visual_guide && d.visual_guide.steps.length > 0 && (
        <Section title="Step-by-Step Resolution Guide" icon={ListIcon}>
          <VisualGuideSection guide={d.visual_guide} />
        </Section>
      )}

      {d.visual_guide && d.resolution_steps.length > 0 && (
        <Section title="Still Not Working?" icon={ListIcon}>
          <ul className="space-y-2 rounded-xl border border-white/45 bg-white/30 p-4 text-caption backdrop-blur-sm">
            {d.resolution_steps.slice(0, 3).map((s, i) => (
              <li key={i} className="flex items-start gap-2.5">
                <span className="select-none text-sm font-bold leading-none text-accent">•</span>
                <span className="font-medium leading-relaxed text-content-secondary">{s}</span>
              </li>
            ))}
          </ul>
        </Section>
      )}

      {!d.visual_guide && d.resolution_steps.length > 0 && (
        <Section title="Step-by-Step Resolution Guide" icon={ListIcon}>
          <ol className="space-y-2.5 text-caption">
            {d.resolution_steps.map((s, i) => (
              <li
                key={i}
                className="flex items-start gap-3 rounded-xl border border-white/45 bg-white/30 p-3 backdrop-blur-sm transition-colors duration-150 hover:bg-white/50"
              >
                <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-lg bg-accent-shine text-[10px] font-black text-white shadow-glow-sm">
                  {i + 1}
                </span>
                <span className="pt-0.5 font-medium leading-relaxed text-content-secondary">{s}</span>
              </li>
            ))}
          </ol>
        </Section>
      )}

      {d.prevention_tips.length > 0 && (
        <Section title="Keep It Working" icon={ShieldCheckIcon}>
          <ul className="space-y-2 rounded-xl border border-white/45 bg-white/30 p-4 text-caption backdrop-blur-sm">
            {d.prevention_tips.slice(0, 3).map((t, i) => (
              <li key={i} className="flex items-start gap-2.5">
                <span className="select-none text-sm font-bold leading-none text-severity-healthy">✓</span>
                <span className="font-medium leading-relaxed">{t}</span>
              </li>
            ))}
          </ul>
        </Section>
      )}
    </div>
  );
}
