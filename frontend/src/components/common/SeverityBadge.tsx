import type { Severity } from "@/types";
import { severityBg } from "@/lib/format";

function statusColorBullet(severity: Severity): string {
  switch (severity) {
    case "Critical":
      return "bg-severity-critical";
    case "Warning":
      return "bg-severity-warning";
    case "Healthy":
      return "bg-severity-healthy";
    default:
      return "bg-severity-info";
  }
}

export function SeverityBadge({ severity }: { severity: Severity }) {
  const isUrgent = severity === "Critical" || severity === "Warning";
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-[10px] font-bold uppercase tracking-wider ${severityBg(
        severity,
      )}`}
    >
      <span className={`relative flex h-1.5 w-1.5 shrink-0`}>
        {isUrgent && (
          <span className={`animate-ping absolute inline-flex h-full w-full rounded-full opacity-75 ${statusColorBullet(severity)}`} />
        )}
        <span className={`relative inline-flex rounded-full h-1.5 w-1.5 ${statusColorBullet(severity)}`} />
      </span>
      {severity}
    </span>
  );
}
