import type { DiagnosisResult, InvestigationReport, InventoryItem } from "@/types";

/** True when text looks like a legacy semicolon-separated inventory dump. */
export function isDenseInventoryText(text?: string | null): boolean {
  if (!text) return false;
  return text.includes(";") && text.length > 120;
}

/** Collect structured inventory rows from diagnosis or investigation findings. */
export function resolveInventoryItems(
  diagnosis?: DiagnosisResult | null,
  investigation?: InvestigationReport | null,
): InventoryItem[] {
  if (diagnosis?.inventory_items && diagnosis.inventory_items.length > 0) {
    return diagnosis.inventory_items;
  }
  for (const f of investigation?.findings ?? []) {
    if (f.inventory_items && f.inventory_items.length > 0) {
      return f.inventory_items;
    }
  }
  return [];
}

/** Split prose into unique sentences (fallback when API omits detail_lines). */
export function splitDetailLines(text?: string | null): string[] {
  if (!text?.trim()) return [];
  const seen = new Set<string>();
  const lines: string[] = [];
  for (const part of text.split(/(?<=[.!?])\s+/)) {
    const p = part.trim();
    if (!p) continue;
    const normalized = p.endsWith(".") || p.endsWith("!") || p.endsWith("?") ? p : `${p}.`;
    const key = normalized.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    lines.push(normalized);
  }
  return lines;
}

/** Line-by-line issue details for the diagnosis card. */
export function resolveDetailLines(
  diagnosis?: DiagnosisResult | null,
  investigation?: InvestigationReport | null,
): string[] {
  if (diagnosis?.detail_lines?.length) {
    return diagnosis.detail_lines;
  }

  const parts: string[] = [];
  const summary = diagnosis?.issue_summary?.trim();
  const root = diagnosis?.root_cause?.trim();
  if (summary) parts.push(summary);
  if (root && root.toLowerCase() !== summary?.toLowerCase() && !summary?.toLowerCase().includes(root.toLowerCase())) {
    parts.push(root);
  }
  if (!parts.length && diagnosis?.reasoning?.trim()) {
    parts.push(diagnosis.reasoning.trim());
  }

  const fromDiagnosis = splitDetailLines(parts.join(" "));
  if (fromDiagnosis.length) return fromDiagnosis;

  const finding = investigation?.findings?.[0];
  return splitDetailLines(finding?.detected);
}

/** Short summary for inventory-style answers. */
export function inventorySummary(items: InventoryItem[], area?: string): string {
  const n = items.length;
  if (area?.toLowerCase() === "drivers") {
    return `${n} installed driver(s) found.`;
  }
  return `${n} item(s) found.`;
}

/**
 * Merge investigation inventory into diagnosis and replace legacy paragraph dumps
 * with a concise summary + table data for the UI.
 */
export function normalizeDiagnosis(
  diagnosis: DiagnosisResult,
  investigation?: InvestigationReport | null,
): DiagnosisResult {
  const items = resolveInventoryItems(diagnosis, investigation);
  if (!items.length) return diagnosis;

  const area = investigation?.findings?.[0]?.area;
  const short = inventorySummary(items, area);
  const clean = (text?: string) => (isDenseInventoryText(text) ? short : text ?? "");

  return {
    ...diagnosis,
    inventory_items: items,
    issue_summary: clean(diagnosis.issue_summary) || short,
    root_cause: clean(diagnosis.root_cause) || short,
    reasoning: clean(diagnosis.reasoning) || short,
    confidence_reasons: (diagnosis.confidence_reasons ?? []).map((r) => clean(r) || short),
    detail_lines: diagnosis.detail_lines?.length
      ? diagnosis.detail_lines
      : splitDetailLines(clean(diagnosis.issue_summary) || short),
  };
}

export function formatIntentLabel(intent: string): string {
  return intent.replace(/_/g, " ");
}

export function formatQueryIntent(intent?: string | null): string | null {
  if (!intent) return null;
  const labels: Record<string, string> = {
    troubleshooting: "fault detection",
    informational: "informational",
    inventory: "inventory",
    holistic: "holistic",
  };
  return labels[intent] ?? intent;
}
