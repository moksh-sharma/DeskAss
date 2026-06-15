import type { InvestigationReport, ProbeCheck } from "@/types";
import { SeverityBadge } from "@/components/common/SeverityBadge";
import { severityColor } from "@/lib/format";

function statusDot(status: ProbeCheck["status"]): string {
  switch (status) {
    case "Critical":
      return "bg-severity-critical shadow-md shadow-red-300/30";
    case "Warning":
      return "bg-severity-warning shadow-md shadow-amber-300/30";
    case "Healthy":
      return "bg-severity-healthy shadow-md shadow-emerald-300/30";
    default:
      return "bg-severity-info shadow-md shadow-sky-300/30";
  }
}

export function IssueScanDetails({
  report,
  showHeading = true,
  scanIndex,
}: {
  report: InvestigationReport;
  showHeading?: boolean;
  scanIndex?: number;
}) {
  const { profile, probes } = report;
  const issueProbes = probes.filter((p) => p.available);
  const totalChecks = issueProbes.reduce((n, p) => n + p.checks.length, 0);

  if (issueProbes.length === 0) return null;

  const domainLabel = profile.primary_domain ?? profile.domains[0];
  const metaParts: string[] = [];
  if (totalChecks > 0) metaParts.push(`${totalChecks} check${totalChecks === 1 ? "" : "s"}`);
  if (report.scan_duration_seconds != null && report.scan_duration_seconds > 0) {
    metaParts.push(`${Math.round(report.scan_duration_seconds)}s`);
  }

  const heading =
    scanIndex != null ? `Issue ${scanIndex}` : showHeading ? "Scans for this issue" : undefined;

  return (
    <div className="space-y-2">
      {heading && <h4 className="text-label px-1">{heading}</h4>}
      <div className="glass-card rounded-xl px-3 py-3 text-xs leading-relaxed text-content-secondary">
        {report.issue && <p className="font-medium text-content-primary">"{report.issue}"</p>}

        <div
          className={
            report.issue ? "mt-2.5 flex flex-wrap items-center gap-2" : "flex flex-wrap items-center gap-2"
          }
        >
          {domainLabel && (
            <span className="rounded-full border border-accent/25 bg-accent/10 px-2 py-0.5 text-[9px] font-bold uppercase tracking-wider text-accent">
              {domainLabel}
            </span>
          )}
          <SeverityBadge severity={report.overall_status} />
        </div>

        {metaParts.length > 0 && (
          <p className="mt-2 text-[10px] font-medium text-content-muted">{metaParts.join(" · ")}</p>
        )}

        <ul className={metaParts.length > 0 || report.issue ? "mt-2.5 space-y-1.5" : "space-y-1.5"}>
          {issueProbes.flatMap((probe) =>
            probe.checks.map((c, i) => (
              <li key={`${probe.domain}-${i}`} className="flex items-start justify-between gap-2">
                <div className="flex min-w-0 items-start gap-2">
                  <span className={`mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full ${statusDot(c.status)}`} />
                  <span className="font-medium text-content-body">{c.label}</span>
                </div>
                <span className={`shrink-0 text-right font-bold ${severityColor(c.status)}`}>
                  {c.value}
                </span>
              </li>
            )),
          )}
        </ul>
      </div>
    </div>
  );
}
