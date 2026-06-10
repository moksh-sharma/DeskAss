import type { Severity } from "@/types";

export function severityColor(severity: Severity): string {
  switch (severity) {
    case "Critical":
      return "text-severity-critical";
    case "Warning":
      return "text-severity-warning";
    case "Healthy":
      return "text-severity-healthy";
    default:
      return "text-severity-info";
  }
}

export function severityBg(severity: Severity): string {
  switch (severity) {
    case "Critical":
      return "bg-severity-critical/15 text-severity-critical border-severity-critical/30";
    case "Warning":
      return "bg-severity-warning/15 text-severity-warning border-severity-warning/30";
    case "Healthy":
      return "bg-severity-healthy/15 text-severity-healthy border-severity-healthy/30";
    default:
      return "bg-severity-info/15 text-severity-info border-severity-info/30";
  }
}

export function usageColor(percent: number): string {
  if (percent >= 90) return "bg-severity-critical";
  if (percent >= 75) return "bg-severity-warning";
  return "bg-severity-healthy";
}

/** Parse API timestamps (UTC, with or without a Z suffix) into local display time. */
export function parseApiDate(iso: string): Date {
  if (!iso) return new Date(NaN);
  const trimmed = iso.trim();
  // Naive UTC from SQLite / Python (no offset) → treat as UTC.
  const asUtc =
    trimmed.includes("T") &&
    !trimmed.endsWith("Z") &&
    !/[+-]\d{2}:\d{2}$/.test(trimmed)
      ? `${trimmed}Z`
      : trimmed;
  return new Date(asUtc);
}

export function formatTime(iso: string): string {
  try {
    const d = parseApiDate(iso);
    if (Number.isNaN(d.getTime())) return iso;
    return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  } catch {
    return iso;
  }
}

export function formatDateTime(iso: string): string {
  try {
    const d = parseApiDate(iso);
    if (Number.isNaN(d.getTime())) return iso;
    return d.toLocaleString();
  } catch {
    return iso;
  }
}

export function clamp(value: number, lo = 0, hi = 100): number {
  return Math.max(lo, Math.min(hi, value));
}
