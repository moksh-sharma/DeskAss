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
      <div className="glass-card overflow-visible rounded-xl px-3 py-3 text-xs leading-relaxed text-content-secondary">
        {report.issue && (
          <p className="whitespace-normal break-words font-medium text-content-primary">
            &ldquo;{report.issue}&rdquo;
          </p>
        )}

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
          <p className="mt-2 whitespace-normal break-words text-[10px] font-medium text-content-muted">
            {metaParts.join(" · ")}
          </p>
        )}

        <ul className={metaParts.length > 0 || report.issue ? "mt-2.5 space-y-2" : "space-y-2"}>
          {issueProbes.flatMap((probe) =>
            probe.checks.map((c, i) => (
              <li
                key={`${probe.domain}-${i}`}
                className="rounded-lg border border-white/45 bg-white/30 px-2.5 py-2"
              >
                <div className="flex items-start gap-2">
                  <span className={`mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full ${statusDot(c.status)}`} />
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-col gap-0.5">
                      <span className="whitespace-normal break-words font-medium text-content-body">
                        {c.label}
                      </span>
                      {c.value && (
                        <span
                          className={`whitespace-normal break-words font-bold ${severityColor(c.status)}`}
                        >
                          {c.value}
                        </span>
                      )}
                    </div>
                    {c.detail && (
                      <p className="mt-1 whitespace-normal break-all font-mono text-[10px] leading-snug text-content-muted">
                        {c.detail}
                      </p>
                    )}
                  </div>
                </div>
              </li>
            )),
          )}
        </ul>
      </div>
    </div>
  );
}
