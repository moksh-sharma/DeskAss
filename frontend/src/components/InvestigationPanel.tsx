import { useState } from "react";
import type { InvestigationReport, ProbeCheck } from "@/types";
import { severityColor } from "@/lib/format";

function statusDot(status: ProbeCheck["status"]): string {
  switch (status) {
    case "Critical":
      return "bg-severity-critical shadow-md shadow-severity-critical/20";
    case "Warning":
      return "bg-severity-warning shadow-md shadow-severity-warning/20";
    case "Healthy":
      return "bg-severity-healthy shadow-md shadow-severity-healthy/20";
    default:
      return "bg-severity-info shadow-md shadow-severity-info/20";
  }
}

export function InvestigationPanel({ report }: { report: InvestigationReport }) {
  const [open, setOpen] = useState(true);
  const { profile, probes } = report;

  const availableProbes = probes.filter((p) => p.available);
  const totalChecks = availableProbes.reduce((n, p) => n + p.checks.length, 0);
  if (availableProbes.length === 0) return null;

  return (
    <div className="card mt-2 w-full max-w-3xl overflow-hidden p-0 border border-base-700/50 bg-base-850 hover:border-base-600/40 transition-colors duration-150 shadow-md">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between gap-3 px-5 py-4 text-left hover:bg-base-800/30 transition-colors relative"
      >
        <div className="absolute top-0 left-0 h-full w-1.5 bg-accent/40" />
        <div className="flex flex-col">
          <span className="text-label flex items-center gap-1.5">
            <span className="h-1.5 w-1.5 rounded-full bg-accent animate-pulse" />
            Issue Scan (full system data)
          </span>
          <span className="text-caption text-content-secondary font-semibold mt-1">
            {availableProbes.map((p) => p.title.replace(" (issue scan)", "")).join(" · ")} · {totalChecks} Checks
            {report.scan_duration_seconds != null && report.scan_duration_seconds > 0
              ? ` · ${Math.round(report.scan_duration_seconds)}s`
              : ""}
            {report.scan_health_score != null ? ` · Health ${report.scan_health_score}/100` : ""}
          </span>
        </div>
        <div className="flex items-center gap-2.5">
          {profile.domains.length > 0 && (
            <span className="rounded-full bg-accent/10 border border-accent/20 px-2 py-0.5 text-[9px] font-bold uppercase tracking-wider text-accent">
              {profile.primary_domain ?? profile.domains[0]}
            </span>
          )}
          <span className={`text-xs text-gray-500 font-bold transition-transform duration-150 transform ${open ? "rotate-180" : ""}`}>
            ▼
          </span>
        </div>
      </button>

      {open && (
        <div className="border-t border-base-700/30 px-5 py-4 bg-base-900/10 space-y-4">
          {availableProbes.map((probe) => (
            <div key={probe.domain} className="space-y-2 last:mb-0">
              <h5 className="text-label">{probe.title}</h5>
              <div className="space-y-1.5 bg-base-900/20 border border-base-700/25 rounded-xl p-3 shadow-inner">
                {probe.checks.map((c, i) => (
                  <div key={i} className="flex items-start justify-between gap-3 text-xs py-1 first:pt-0 last:pb-0 border-b border-base-700/20 last:border-0 hover:bg-base-800/10 px-1 rounded transition-colors duration-100">
                    <div className="flex items-start gap-2">
                      <span className={`mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full ${statusDot(c.status)}`} />
                      <span className="text-content-body font-medium">{c.label}</span>
                    </div>
                    <span className={`text-right font-bold ${severityColor(c.status)}`}>{c.value}</span>
                  </div>
                ))}
              </div>
            </div>
          ))}
          <p className="mt-2 border-t border-base-700/30 pt-2.5 text-[9px] font-semibold text-content-muted uppercase tracking-wide">
            Full hardware & software scan ran in the background; only checks related to your issue are shown.
          </p>
        </div>
      )}
    </div>
  );
}
