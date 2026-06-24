import type { ReactNode } from "react";
import { useStore } from "@/store/useStore";
import { CollapsibleSection } from "@/components/common/CollapsibleSection";
import { LoadingAnimation } from "@/components/LoadingAnimation";
import { LenisScroll } from "@/components/LenisScroll";
import { MachineScanTroubleshooter } from "@/components/MachineScanTroubleshooter";
import { StorageReportSections } from "@/components/StorageView";
import { formatDateTime } from "@/lib/format";
import type { MachineHealthReport, MachineScanReport, StorageReport } from "@/types";

function statusColor(status: string): string {
  const s = (status || "").toLowerCase();
  if (s === "critical" || s === "critical error") return "text-severity-critical font-bold";
  if (s === "warning") return "text-severity-warning font-bold";
  if (s === "healthy" || s === "ok") return "text-severity-healthy font-bold";
  return "text-severity-info font-bold";
}

function ringColor(score: number): string {
  if (score >= 80) return "#10b981"; // modern emerald
  if (score >= 50) return "#f59e0b"; // amber
  return "#f43f5e"; // modern rose
}

function ScoreRing({ score, status }: { score: number; status: string }) {
  const radius = 52;
  const circ = 2 * Math.PI * radius;
  const offset = circ * (1 - score / 100);
  return (
    <div className="relative h-32 w-32 shrink-0 select-none">
      <svg className="h-full w-full -rotate-90" viewBox="0 0 120 120">
        <circle cx="60" cy="60" r={radius} fill="none" stroke="rgba(255,255,255,0.55)" strokeWidth="8" />
        <circle
          cx="60"
          cy="60"
          r={radius}
          fill="none"
          stroke={ringColor(score)}
          strokeWidth="8"
          strokeLinecap="round"
          strokeDasharray={circ}
          strokeDashoffset={offset}
          className="transition-all duration-1000 ease-out"
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="text-3xl font-black text-content-primary tracking-tight">{score}</span>
        <span className={`text-[10px] font-bold uppercase tracking-wider mt-0.5 ${statusColor(status)}`}>{status}</span>
      </div>
    </div>
  );
}

/** Render an arbitrary value (primitive / object / array) as readable rows. */
function Val({ value }: { value: unknown }) {
  if (value === null || value === undefined || value === "") return <span className="text-content-muted">-</span>;
  if (typeof value === "boolean") return <span className="font-bold text-content-secondary">{value ? "Yes" : "No"}</span>;
  if (typeof value === "number" || typeof value === "string") return <span className="font-semibold text-content-secondary">{String(value)}</span>;
  if (Array.isArray(value)) {
    if (value.length === 0) return <span className="text-content-muted">None</span>;
    return <span className="font-semibold text-content-secondary">{value.length} item(s)</span>;
  }
  return <span className="text-content-body">{Object.keys(value as object).length} field(s)</span>;
}

function KV({ label, value }: { label: string; value: unknown }) {
  return (
    <div className="flex items-baseline justify-between gap-3 border-b border-white/40/30 py-2.5 text-xs last:border-0 hover:bg-white/35/10 px-1 rounded transition-colors">
      <span className="text-content-body font-medium">{label}</span>
      <span className="text-right font-medium text-content-primary">
        <Val value={value} />
      </span>
    </div>
  );
}

function Table({ rows, columns }: { rows: any[]; columns: { key: string; label: string }[] }) {
  if (!rows || rows.length === 0) return <p className="text-empty">No records found.</p>;
  return (
    <div className="overflow-hidden rounded-xl border border-white/40/30 shadow-inner">
      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs">
          <thead>
            <tr className="text-content-muted bg-white/35/30 uppercase tracking-wider text-[9px] font-bold border-b border-white/40/30">
              {columns.map((c) => (
                <th key={c.key} className="px-3.5 py-2.5 font-extrabold">
                  {c.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={i} className="border-t border-white/40/20 hover:bg-white/35/20 transition-colors">
                {columns.map((c) => (
                  <td key={c.key} className="px-3.5 py-2 text-content-secondary font-medium">
                    {r[c.key] === null || r[c.key] === undefined || r[c.key] === ""
                      ? "-"
                      : typeof r[c.key] === "boolean"
                        ? r[c.key]
                          ? "Yes"
                          : "No"
                        : String(r[c.key])}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function fmtGB(gb: number | null | undefined): string {
  if (gb === null || gb === undefined) return "-";
  if (gb >= 1) return `${gb.toFixed(gb >= 100 ? 0 : 1)} GB`;
  if (gb > 0) return `${Math.round(gb * 1024)} MB`;
  return "0";
}

function StorageAnalysisSection({ report }: { report: StorageReport }) {
  const health = report.health ?? { overall_score: 0, overall_status: "Unknown", notes: [] as string[] };
  const primary = report.primary_drive;
  return (
    <CollapsibleSection
      title="Storage Analysis"
      subtitle={`${health.overall_score}/100 · ~${fmtGB(report.cleanup?.total_potential_gb)} recoverable · ${report.scan_duration_seconds}s`}
    >
      <div className="mb-4 grid gap-3 sm:grid-cols-3">
        <div className="rounded-xl border border-white/30 bg-white/30 px-4 py-3 text-center">
          <div className="text-[10px] font-bold uppercase tracking-wider text-content-muted">
            {primary ? `${primary.drive} free` : "Free space"}
          </div>
          <div className="mt-1 text-lg font-black text-content-primary">{fmtGB(primary?.free_gb)}</div>
        </div>
        <div className="rounded-xl border border-white/30 bg-white/30 px-4 py-3 text-center">
          <div className="text-[10px] font-bold uppercase tracking-wider text-content-muted">Recoverable</div>
          <div className="mt-1 text-lg font-black text-severity-healthy">{fmtGB(report.cleanup?.total_potential_gb)}</div>
        </div>
        <div className="rounded-xl border border-white/30 bg-white/30 px-4 py-3 text-center">
          <div className="text-[10px] font-bold uppercase tracking-wider text-content-muted">Days until full</div>
          <div className="mt-1 text-lg font-black text-content-primary">
            {report.growth?.days_until_full != null ? report.growth.days_until_full : "-"}
          </div>
        </div>
      </div>
      {(health.notes ?? []).length > 0 && (
        <ul className="mb-4 space-y-1 text-xs text-content-secondary">
          {(health.notes as string[]).map((n, i) => (
            <li key={i} className="flex gap-2">
              <span className="text-accent">•</span>
              {n}
            </li>
          ))}
        </ul>
      )}
      <StorageReportSections report={report} collapsible={false} />
    </CollapsibleSection>
  );
}

type PillTone = "critical" | "warning" | "healthy" | "muted";

const PILL_TONES: Record<PillTone, string> = {
  critical: "bg-severity-critical/10 text-severity-critical border-severity-critical/30",
  warning: "bg-severity-warning/10 text-severity-warning border-severity-warning/30",
  healthy: "bg-severity-healthy/10 text-severity-healthy border-severity-healthy/30",
  muted: "bg-white/30 text-content-muted border-white/40",
};

function StatusPill({ tone, children }: { tone: PillTone; children: ReactNode }) {
  return (
    <span
      className={`shrink-0 rounded-full border px-2 py-0.5 text-[9px] font-extrabold uppercase tracking-wider ${PILL_TONES[tone]}`}
    >
      {children}
    </span>
  );
}

function riskTone(level: string | undefined): PillTone {
  const l = (level || "").toLowerCase();
  if (l === "critical" || l === "high") return "critical";
  if (l === "medium" || l === "elevated") return "warning";
  if (l === "low") return "healthy";
  return "muted";
}

const PREDICTION_LABELS: Record<string, string> = {
  ssd_failure: "Disk / SSD failure",
  battery_failure: "Battery failure",
  crash_probability: "Crash probability",
  resource_exhaustion: "Resource exhaustion",
  disk_full: "Disk full",
};

function PredictiveSection({ predictive }: { predictive: any }) {
  const predictions = predictive?.predictions ?? {};
  const entries = Object.entries(predictions) as [string, any][];
  if (entries.length === 0) return null;
  const highCount = (predictive?.high_risk_areas ?? []).length;
  // Worst-first ordering.
  const order: Record<string, number> = { critical: 0, high: 1, medium: 2, elevated: 2, low: 3, "n/a": 4 };
  entries.sort((a, b) => (order[(a[1]?.risk || "").toLowerCase()] ?? 5) - (order[(b[1]?.risk || "").toLowerCase()] ?? 5));
  return (
    <CollapsibleSection
      title="Predictive Risk Analysis"
      subtitle={highCount > 0 ? `${highCount} high-risk area${highCount === 1 ? "" : "s"}` : "No high-risk areas"}
      accent={highCount > 0 ? "warning" : undefined}
    >
      <div className="space-y-2.5">
        {entries.map(([key, p]) => (
          <div
            key={key}
            className="rounded-xl border border-white/40/20 bg-white/30/10 p-3"
          >
            <div className="flex items-center justify-between gap-3">
              <span className="text-xs font-bold text-content-primary">{PREDICTION_LABELS[key] ?? key}</span>
              <StatusPill tone={riskTone(p?.risk)}>{p?.risk || "n/a"}</StatusPill>
            </div>
            {p?.detail && <p className="mt-1 text-caption text-content-secondary leading-relaxed">{p.detail}</p>}
            {(p?.evidence ?? []).length > 0 && (
              <ul className="mt-1.5 space-y-0.5">
                {(p.evidence as string[]).map((e, i) => (
                  <li key={i} className="flex gap-1.5 text-[11px] text-content-muted">
                    <span className="text-accent select-none">•</span>
                    <span>{e}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        ))}
      </div>
    </CollapsibleSection>
  );
}

function complianceTone(c: any): PillTone {
  if (c?.status === "pass") return "healthy";
  if (c?.status === "fail") return (c?.severity === "critical" || c?.severity === "high") ? "critical" : "warning";
  return "muted";
}

function ComplianceSection({ compliance }: { compliance: any }) {
  const controls = (compliance?.controls ?? []) as any[];
  if (controls.length === 0) return null;
  const score = compliance?.score;
  const status = compliance?.status ?? "Unknown";
  const passed = compliance?.passed_count ?? 0;
  const evaluated = compliance?.evaluated_count ?? 0;
  const tone: PillTone =
    typeof score === "number" ? (score >= 80 ? "healthy" : score >= 50 ? "warning" : "critical") : "muted";
  // Failing controls first, then by severity.
  const sevOrder: Record<string, number> = { critical: 0, high: 1, medium: 2, low: 3 };
  const sorted = [...controls].sort((a, b) => {
    const fa = a.status === "fail" ? 0 : a.status === "not_evaluated" ? 2 : 1;
    const fb = b.status === "fail" ? 0 : b.status === "not_evaluated" ? 2 : 1;
    if (fa !== fb) return fa - fb;
    return (sevOrder[a.severity] ?? 9) - (sevOrder[b.severity] ?? 9);
  });
  return (
    <CollapsibleSection
      title="Security Compliance"
      subtitle={`${score ?? "?"}/100 · ${status} · ${passed}/${evaluated} controls passed`}
      accent={tone === "critical" ? "warning" : undefined}
    >
      <div className="space-y-1.5">
        {sorted.map((c, i) => (
          <div
            key={i}
            className="flex items-start justify-between gap-3 rounded-xl border border-white/40/20 bg-white/30/10 px-3 py-2.5"
          >
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <span className="text-xs font-bold text-content-primary">{c.name}</span>
                <span className="text-[9px] font-bold uppercase tracking-wider text-content-muted">{c.severity}</span>
              </div>
              {c.detail && <p className="mt-0.5 text-[11px] text-content-secondary leading-relaxed">{c.detail}</p>}
            </div>
            <StatusPill tone={complianceTone(c)}>
              {c.status === "not_evaluated" ? "n/a" : c.status}
            </StatusPill>
          </div>
        ))}
      </div>
    </CollapsibleSection>
  );
}

function KnowledgeGraphSection({ graph }: { graph: any }) {
  const correlations = (graph?.correlations ?? []) as string[];
  const edges = (graph?.edges ?? []) as any[];
  const nodes = (graph?.nodes ?? []) as any[];
  if (correlations.length === 0 && edges.length === 0 && nodes.length === 0) return null;
  // Count nodes by type for a quick entity overview.
  const typeCounts: Record<string, number> = {};
  for (const n of nodes) typeCounts[n.type] = (typeCounts[n.type] ?? 0) + 1;
  return (
    <CollapsibleSection
      title="Knowledge Graph & Correlations"
      subtitle={`${graph?.node_count ?? nodes.length} entities · ${graph?.edge_count ?? edges.length} links`}
    >
      {Object.keys(typeCounts).length > 0 && (
        <div className="mb-3 flex flex-wrap gap-2">
          {Object.entries(typeCounts).map(([t, n]) => (
            <span
              key={t}
              className="rounded-lg border border-white/40/30 bg-white/35/30 px-2.5 py-1 text-[10px] font-bold text-content-secondary"
            >
              {t} · {n}
            </span>
          ))}
        </div>
      )}
      {correlations.length > 0 && (
        <div className="mb-3">
          <h4 className="mb-1 text-section-title">Correlations</h4>
          <ul className="space-y-1.5">
            {correlations.map((c, i) => (
              <li
                key={i}
                className="flex items-start gap-2 rounded-xl border border-white/40/10 bg-white/30/10 p-2.5 text-caption text-content-secondary"
              >
                <span className="select-none text-sm font-bold leading-none text-accent">•</span>
                <span className="leading-relaxed">{c}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
      {edges.length > 0 && (
        <div>
          <h4 className="mb-1 text-section-title">Relationships ({edges.length})</h4>
          <Table
            rows={edges.slice(0, 25).map((e) => ({
              source: e.source,
              relation: (e.relation || "").replace(/_/g, " "),
              target: e.target,
            }))}
            columns={[
              { key: "source", label: "From" },
              { key: "relation", label: "Relation" },
              { key: "target", label: "To" },
            ]}
          />
        </div>
      )}
    </CollapsibleSection>
  );
}

function ScorecardSection({ health }: { health: MachineHealthReport }) {
  const cats = Object.entries(health.categories ?? {});
  if (cats.length === 0) return null;
  const tone = (status: string): PillTone => {
    const s = (status || "").toLowerCase();
    if (s.includes("critical")) return "critical";
    if (s.includes("warn")) return "warning";
    if (s.includes("healthy") || s === "ok") return "healthy";
    return "muted";
  };
  return (
    <CollapsibleSection
      title="Executive Scorecard"
      subtitle={`${health.overall_score}/100 overall · ${cats.length} dimensions`}
    >
      <div className="grid gap-2.5 sm:grid-cols-2">
        {cats.map(([name, cat]) => (
          <div key={name} className="rounded-xl border border-white/40/20 bg-white/30/10 p-3">
            <div className="flex items-center justify-between gap-2">
              <span className="text-xs font-bold capitalize text-content-primary">{name}</span>
              <div className="flex items-center gap-2">
                <span className={`text-base font-extrabold ${statusColor(cat.status)}`}>{cat.score}</span>
                <StatusPill tone={tone(cat.status)}>{cat.status}</StatusPill>
              </div>
            </div>
            {(cat.notes ?? []).length > 0 && (
              <ul className="mt-1.5 space-y-0.5">
                {(cat.notes as string[]).slice(0, 4).map((n, i) => (
                  <li key={i} className="flex gap-1.5 text-[11px] text-content-muted">
                    <span className="text-accent select-none">•</span>
                    <span>{n}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        ))}
      </div>
    </CollapsibleSection>
  );
}

function IntelligenceSections({ report }: { report: MachineScanReport }) {
  const sw = report.software ?? {};
  return (
    <>
      <ScorecardSection health={report.health_report} />
      <PredictiveSection predictive={sw.predictive} />
      <ComplianceSection compliance={sw.compliance} />
      <KnowledgeGraphSection graph={sw.knowledge_graph} />
    </>
  );
}

function Body({ report }: { report: MachineScanReport }) {
  const hw = report.hardware ?? {};
  const sw = report.software ?? {};

  const cpu = hw.cpu ?? {};
  const ram = hw.ram ?? {};
  const perf = hw.performance ?? {};
  const devices = hw.devices ?? {};
  const ext = hw.external_devices ?? {};
  const extSummary = ext.summary ?? {};

  const os = sw.operating_system ?? {};
  const win = os.windows ?? {};
  const proc = sw.running_processes ?? {};
  const svc = sw.services ?? {};
  const startup = sw.startup_programs ?? {};
  const logs = sw.event_logs ?? {};
  const net = sw.network ?? {};
  const conn = net.connectivity ?? {};
  const sec = sw.security ?? {};
  const crash = sw.crash_analysis ?? {};
  const apps = sw.installed_applications ?? [];

  const deviceCategories: [string, any[]][] = Object.entries(devices.by_category ?? {});

  return (
    <div className="space-y-3">
      {/* ============================== HARDWARE ============================== */}
      <CollapsibleSection
        title="Hardware"
        subtitle={`${cpu.processor_name ?? "System"} · ${devices.total_count ?? 0} devices`}
      >
        {/* System identity / asset info */}
        {hw.system && (
          <div className="grid gap-4 md:grid-cols-2">
            <div>
              <h4 className="mb-1 text-section-title">System identity</h4>
              <KV label="Manufacturer" value={hw.system.manufacturer} />
              <KV label="Model" value={hw.system.model} />
              <KV label="System family" value={hw.system.system_family} />
              <KV label="Chassis" value={hw.system.chassis_type} />
            </div>
            <div>
              <h4 className="mb-1 text-section-title">Asset</h4>
              <KV label="Serial number" value={hw.system.serial_number} />
              <KV label="Asset tag" value={hw.system.asset_tag} />
              <KV label="UUID" value={hw.system.uuid} />
              <KV label="Role" value={hw.system.domain_role} />
            </div>
          </div>
        )}

        {/* Core components */}
        <div className="mt-4 grid gap-4 md:grid-cols-2">
          <div>
            <h4 className="mb-1 text-section-title">CPU</h4>
            <KV label="Processor" value={cpu.processor_name} />
            <KV label="Cores (phys/logical)" value={`${cpu.physical_cores ?? "?"} / ${cpu.logical_cores ?? "?"}`} />
            <KV label="Current usage" value={cpu.current_usage_pct != null ? `${cpu.current_usage_pct}%` : null} />
            <KV label="Frequency" value={cpu.current_frequency_mhz ? `${cpu.current_frequency_mhz} MHz` : null} />
            <KV label="Max frequency" value={cpu.max_frequency_mhz ? `${cpu.max_frequency_mhz} MHz` : null} />
            <KV label="L2 / L3 cache" value={cpu.l2_cache_kb || cpu.l3_cache_kb ? `${cpu.l2_cache_kb ?? "?"} KB / ${cpu.l3_cache_kb ?? "?"} KB` : null} />
            <KV label="Virtualization (firmware)" value={cpu.virtualization_firmware_enabled} />
            <KV label="Temperature" value={cpu.temperature_c ? `${cpu.temperature_c}°C` : null} />
          </div>
          <div>
            <h4 className="mb-1 text-section-title">Memory</h4>
            <KV label="Total" value={ram.total_gb ? `${ram.total_gb} GB` : null} />
            <KV label="Used" value={ram.used_gb ? `${ram.used_gb} GB` : null} />
            <KV label="Utilization" value={ram.utilization_pct != null ? `${ram.utilization_pct}%` : null} />
            <KV label="Modules" value={ram.module_count} />
            <KV label="Speed" value={ram.speed_mhz ? `${ram.speed_mhz} MHz` : null} />
            <KV
              label="Page file"
              value={
                ram.virtual_memory?.total_gb
                  ? `${ram.virtual_memory.used_gb ?? "?"} / ${ram.virtual_memory.total_gb} GB (${ram.virtual_memory.used_pct ?? "?"}%)`
                  : null
              }
            />
          </div>
        </div>

        {/* Live performance */}
        <div className="mt-4 grid gap-4 md:grid-cols-2">
          <div>
            <h4 className="mb-1 text-section-title">Performance - CPU / Memory</h4>
            <KV label="CPU current" value={perf.cpu?.current_pct != null ? `${perf.cpu.current_pct}%` : null} />
            <KV label="CPU average" value={perf.cpu?.average_pct != null ? `${perf.cpu.average_pct}%` : null} />
            <KV label="CPU peak" value={perf.cpu?.peak_pct != null ? `${perf.cpu.peak_pct}%` : null} />
            <KV label="Memory current" value={perf.memory?.current_pct != null ? `${perf.memory.current_pct}%` : null} />
            <KV label="Swap used" value={perf.memory?.swap_used_pct != null ? `${perf.memory.swap_used_pct}%` : null} />
          </div>
          <div>
            <h4 className="mb-1 text-section-title">Performance - Disk / Network I/O</h4>
            <KV label="Disk read" value={perf.disk?.read_mb_s != null ? `${perf.disk.read_mb_s} MB/s` : null} />
            <KV label="Disk write" value={perf.disk?.write_mb_s != null ? `${perf.disk.write_mb_s} MB/s` : null} />
            <KV label="Net upload" value={perf.network?.upload_mb_s != null ? `${perf.network.upload_mb_s} MB/s` : null} />
            <KV label="Net download" value={perf.network?.download_mb_s != null ? `${perf.network.download_mb_s} MB/s` : null} />
          </div>
        </div>

        {/* Storage */}
        <div className="mt-4">
          <h4 className="mb-1 text-section-title">Storage</h4>
          <Table
            rows={hw.storage?.logical_drives ?? []}
            columns={[
              { key: "drive", label: "Drive" },
              { key: "file_system", label: "FS" },
              { key: "total_gb", label: "Total GB" },
              { key: "free_gb", label: "Free GB" },
              { key: "usage_pct", label: "Used %" },
            ]}
          />
          {(hw.storage?.physical_disks ?? []).length > 0 && (
            <div className="mt-2">
              <h4 className="mb-1 text-section-title">Physical disks</h4>
              <Table
                rows={hw.storage.physical_disks}
                columns={[
                  { key: "name", label: "Disk" },
                  { key: "media_type", label: "Type" },
                  { key: "bus_type", label: "Bus" },
                  { key: "size_gb", label: "Size GB" },
                  { key: "firmware_version", label: "Firmware" },
                  { key: "serial_number", label: "Serial" },
                ]}
              />
            </div>
          )}
          {(hw.disk_health?.disks ?? []).length > 0 && (
            <div className="mt-2">
              <h4 className="mb-1 text-section-title">Disk health (SMART)</h4>
              <Table
                rows={hw.disk_health.disks}
                columns={[
                  { key: "name", label: "Disk" },
                  { key: "smart_health", label: "SMART" },
                  { key: "media_type", label: "Type" },
                  { key: "temperature_c", label: "Temp °C" },
                  { key: "wear_pct", label: "Wear %" },
                  { key: "power_on_hours", label: "Power-on hrs" },
                  { key: "read_errors", label: "Read errs" },
                  { key: "write_errors", label: "Write errs" },
                ]}
              />
            </div>
          )}
        </div>

        {/* GPU */}
        {(hw.gpu?.gpus ?? []).length > 0 && (
          <div className="mt-4">
            <h4 className="mb-1 text-section-title">GPU</h4>
            <Table
              rows={hw.gpu.gpus}
              columns={[
                { key: "model", label: "Model" },
                { key: "manufacturer", label: "Vendor" },
                { key: "driver_version", label: "Driver" },
                { key: "driver_date", label: "Driver date" },
                { key: "vram_gb", label: "VRAM GB" },
                { key: "resolution", label: "Resolution" },
              ]}
            />
          </div>
        )}

        {/* Monitors */}
        {(devices.monitors ?? []).length > 0 && (
          <div className="mt-4">
            <h4 className="mb-1 text-section-title">Monitors</h4>
            <Table
              rows={devices.monitors}
              columns={[
                { key: "manufacturer", label: "Manufacturer" },
                { key: "model", label: "Model" },
                { key: "serial_number", label: "Serial" },
                { key: "year_of_manufacture", label: "Year" },
              ]}
            />
          </div>
        )}

        {/* Battery + Motherboard */}
        <div className="mt-4 grid gap-4 md:grid-cols-2">
          <div>
            <h4 className="mb-1 text-section-title">Battery</h4>
            {hw.battery?.present ? (
              <>
                <KV label="Charge" value={`${hw.battery.percentage}%`} />
                <KV label="Charging" value={hw.battery.charging} />
                <KV label="Health" value={hw.battery.battery_health_pct ? `${hw.battery.battery_health_pct}%` : null} />
                <KV label="Remaining" value={hw.battery.estimated_remaining} />
              </>
            ) : (
              <p className="text-caption text-content-body">{hw.battery?.note ?? "No battery."}</p>
            )}
          </div>
          <div>
            <h4 className="mb-1 text-section-title">Motherboard / BIOS</h4>
            <KV label="Manufacturer" value={hw.motherboard?.manufacturer} />
            <KV label="Model" value={hw.motherboard?.model} />
            <KV label="BIOS version" value={hw.motherboard?.bios_version} />
            <KV label="BIOS date" value={hw.motherboard?.bios_release_date} />
          </div>
        </div>

        {/* Network adapters */}
        {(devices.network_adapters ?? []).length > 0 && (
          <div className="mt-4">
            <h4 className="mb-1 text-section-title">Network adapters</h4>
            <Table
              rows={devices.network_adapters}
              columns={[
                { key: "name", label: "Adapter" },
                { key: "manufacturer", label: "Vendor" },
                { key: "mac", label: "MAC" },
                { key: "speed_mbps", label: "Mbps" },
                { key: "connected", label: "Connected" },
              ]}
            />
          </div>
        )}

        {/* Problem devices first, if any */}
        {(devices.problem_devices ?? []).length > 0 && (
          <div className="mt-4">
            <h4 className="mb-1 text-xs font-semibold uppercase text-severity-warning">
              Devices reporting errors
            </h4>
            <Table
              rows={devices.problem_devices}
              columns={[
                { key: "name", label: "Device" },
                { key: "category", label: "Category" },
                { key: "status", label: "Status" },
                { key: "problem_code", label: "Problem" },
              ]}
            />
          </div>
        )}

        {/* All devices grouped by category */}
        <div className="mt-4">
          <h4 className="mb-1 text-section-title">
            All devices / components ({devices.total_count ?? 0})
          </h4>
          {deviceCategories.length === 0 ? (
            <p className="text-caption text-content-body">No device inventory available.</p>
          ) : (
            deviceCategories.map(([cat, list]) => (
              <div key={cat} className="mb-2">
                <p className="mt-2 text-label">
                  {cat} ({list.length})
                </p>
                <Table
                  rows={list}
                  columns={[
                    { key: "name", label: "Name" },
                    { key: "manufacturer", label: "Manufacturer" },
                    { key: "working", label: "Working" },
                  ]}
                />
              </div>
            ))
          )}
        </div>
      </CollapsibleSection>

      {/* ========================== EXTERNAL DEVICES ========================== */}
      {ext.available !== false && (
        <CollapsibleSection
          title="External Devices"
          subtitle={
            `${extSummary.total_external_devices ?? 0} connected` +
            (extSummary.issue_count ? ` · ${extSummary.issue_count} issue(s)` : "")
          }
        >
          {/* Detected issues first */}
          {(extSummary.issues ?? []).length > 0 && (
            <div className="mb-2">
              <h4 className="mb-1 text-xs font-semibold uppercase text-severity-warning">
                External hardware issues
              </h4>
              <ul className="space-y-1.5">
                {(extSummary.issues ?? []).map((issue: string, i: number) => (
                  <li
                    key={i}
                    className="flex items-start gap-2 text-caption text-content-secondary bg-white/30/10 border border-white/40/10 p-2.5 rounded-xl"
                  >
                    <span className="text-severity-warning text-sm leading-none font-bold select-none">•</span>
                    <span className="leading-relaxed">{issue}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Printers */}
          <div className="mt-2">
            <h4 className="mb-1 text-section-title">
              Printers ({(ext.printers?.printers ?? []).length})
              {ext.printers && ext.printers.spooler_running === false && (
                <span className="ml-2 text-severity-critical font-bold">· Spooler stopped</span>
              )}
            </h4>
            <Table
              rows={ext.printers?.printers ?? []}
              columns={[
                { key: "name", label: "Printer" },
                { key: "health", label: "Status" },
                { key: "connection", label: "Connection" },
                { key: "network_address", label: "Address" },
                { key: "is_default", label: "Default" },
                { key: "driver", label: "Driver" },
              ]}
            />
          </div>

          {/* Monitors */}
          {(ext.monitors?.monitors ?? []).length > 0 && (
            <div className="mt-4">
              <h4 className="mb-1 text-section-title">Monitors ({ext.monitors.count})</h4>
              <Table
                rows={ext.monitors.monitors}
                columns={[
                  { key: "model", label: "Model" },
                  { key: "manufacturer", label: "Manufacturer" },
                  { key: "connection_type", label: "Connection" },
                  { key: "resolution", label: "Resolution" },
                  { key: "refresh_rate_hz", label: "Hz" },
                  { key: "serial_number", label: "Serial" },
                ]}
              />
            </div>
          )}

          {/* USB devices */}
          {(ext.usb?.devices ?? []).length > 0 && (
            <div className="mt-4">
              <h4 className="mb-1 text-section-title">USB devices ({ext.usb.count})</h4>
              <Table
                rows={ext.usb.devices}
                columns={[
                  { key: "name", label: "Device" },
                  { key: "type", label: "Type" },
                  { key: "manufacturer", label: "Manufacturer" },
                  { key: "health", label: "Status" },
                  { key: "serial_number", label: "Serial" },
                ]}
              />
            </div>
          )}

          {/* Bluetooth */}
          {(ext.bluetooth?.devices ?? []).length > 0 && (
            <div className="mt-4">
              <h4 className="mb-1 text-section-title">
                Bluetooth
                {ext.bluetooth.connected_count
                  ? ` — ${ext.bluetooth.connected_count} connected`
                  : " — none connected"}
                {(ext.bluetooth.paired_count ?? 0) > (ext.bluetooth.connected_count ?? 0) && (
                  <span className="text-content-secondary font-normal">
                    {` (${ext.bluetooth.paired_count} paired)`}
                  </span>
                )}
              </h4>
              <Table
                rows={(ext.bluetooth.devices ?? []).filter((d: { connected?: boolean }) => d.connected)}
                columns={[
                  { key: "name", label: "Device" },
                  { key: "device_type", label: "Type" },
                  { key: "status", label: "Status" },
                ]}
              />
              {(ext.bluetooth.connected_count ?? 0) === 0 && (
                <p className="mt-2 text-caption text-content-secondary">
                  No Bluetooth device is active right now.
                  {(ext.bluetooth.paired_count ?? 0) > 0 &&
                    ` ${ext.bluetooth.paired_count} device(s) are paired but not connected.`}
                </p>
              )}
            </div>
          )}

          {/* External storage */}
          {(ext.external_storage?.devices ?? []).length > 0 && (
            <div className="mt-4">
              <h4 className="mb-1 text-section-title">External storage ({ext.external_storage.count})</h4>
              <Table
                rows={ext.external_storage.devices}
                columns={[
                  { key: "name", label: "Drive" },
                  { key: "bus_type", label: "Bus" },
                  { key: "capacity_gb", label: "Capacity GB" },
                  { key: "free_gb", label: "Free GB" },
                  { key: "smart_health", label: "Health" },
                  { key: "serial_number", label: "Serial" },
                ]}
              />
            </div>
          )}

          {/* Cameras + Scanners */}
          <div className="mt-4 grid gap-4 md:grid-cols-2">
            {(ext.cameras?.cameras ?? []).length > 0 && (
              <div>
                <h4 className="mb-1 text-section-title">Cameras ({ext.cameras.count})</h4>
                <Table
                  rows={ext.cameras.cameras}
                  columns={[
                    { key: "name", label: "Camera" },
                    { key: "health", label: "Status" },
                  ]}
                />
              </div>
            )}
            {(ext.scanners?.scanners ?? []).length > 0 && (
              <div>
                <h4 className="mb-1 text-section-title">Scanners ({ext.scanners.count})</h4>
                <Table
                  rows={ext.scanners.scanners}
                  columns={[
                    { key: "name", label: "Scanner" },
                    { key: "health", label: "Status" },
                  ]}
                />
              </div>
            )}
          </div>

          {/* Audio devices */}
          {((ext.audio?.input_devices ?? []).length > 0 ||
            (ext.audio?.output_devices ?? []).length > 0) && (
            <div className="mt-4 grid gap-4 md:grid-cols-2">
              <div>
                <h4 className="mb-1 text-section-title">Audio output ({ext.audio.output_count})</h4>
                <Table
                  rows={ext.audio.output_devices}
                  columns={[
                    { key: "name", label: "Device" },
                    { key: "health", label: "Status" },
                  ]}
                />
              </div>
              <div>
                <h4 className="mb-1 text-section-title">Audio input ({ext.audio.input_count})</h4>
                <Table
                  rows={ext.audio.input_devices}
                  columns={[
                    { key: "name", label: "Device" },
                    { key: "health", label: "Status" },
                  ]}
                />
              </div>
            </div>
          )}

          {/* Docking stations + Thunderbolt */}
          {((ext.docking_stations?.docking_stations ?? []).length > 0 ||
            (ext.docking_stations?.thunderbolt_devices ?? []).length > 0) && (
            <div className="mt-4">
              <h4 className="mb-1 text-section-title">Docking / Thunderbolt</h4>
              <Table
                rows={[
                  ...(ext.docking_stations?.docking_stations ?? []),
                  ...(ext.docking_stations?.thunderbolt_devices ?? []),
                ]}
                columns={[
                  { key: "name", label: "Device" },
                  { key: "manufacturer", label: "Manufacturer" },
                  { key: "health", label: "Status" },
                ]}
              />
            </div>
          )}

          {/* Network hardware (LAN) */}
          {(ext.network_devices?.lan_devices ?? []).length > 0 && (
            <div className="mt-4">
              <h4 className="mb-1 text-section-title">
                Network devices on LAN ({ext.network_devices.count})
                {ext.network_devices.gateway ? ` · gateway ${ext.network_devices.gateway}` : ""}
              </h4>
              <Table
                rows={ext.network_devices.lan_devices}
                columns={[
                  { key: "ip_address", label: "IP" },
                  { key: "mac_address", label: "MAC" },
                  { key: "manufacturer", label: "Vendor" },
                  { key: "is_gateway", label: "Gateway" },
                ]}
              />
            </div>
          )}

          {/* PCI / expansion */}
          {(ext.pci_devices?.devices ?? []).length > 0 && (
            <div className="mt-4">
              <h4 className="mb-1 text-section-title">PCI / expansion ({ext.pci_devices.count})</h4>
              <Table
                rows={ext.pci_devices.devices}
                columns={[
                  { key: "name", label: "Device" },
                  { key: "class", label: "Class" },
                  { key: "manufacturer", label: "Manufacturer" },
                  { key: "status", label: "Status" },
                ]}
              />
            </div>
          )}
        </CollapsibleSection>
      )}

      {/* ============================== SOFTWARE ============================== */}
      <CollapsibleSection
        title="Software"
        subtitle={`${win.edition ?? "Windows"} · ${sw.installed_count ?? apps.length ?? 0} apps`}
      >
        {/* Operating system */}
        <div className="grid gap-4 md:grid-cols-2">
          <div>
            <h4 className="mb-1 text-section-title">Operating system</h4>
            <KV label="Edition" value={win.edition} />
            <KV label="Version" value={win.version} />
            <KV label="Build" value={win.build_number} />
            <KV label="Architecture" value={win.architecture} />
            <KV label="Installed" value={win.install_date} />
            <KV label="Uptime" value={win.uptime_readable} />
          </div>
          <div>
            <h4 className="mb-1 text-section-title">Environment / Updates</h4>
            <KV label="Computer" value={os.environment?.computer_name} />
            <KV label="User" value={os.environment?.logged_in_user} />
            <KV label="Domain" value={os.environment?.domain} />
            <KV label="Time zone" value={os.environment?.time_zone} />
            <KV label="Updates installed" value={os.updates?.installed_count} />
            <KV label="Pending updates" value={os.updates?.pending_count} />
          </div>
        </div>

        {/* Activation / management state */}
        <div className="mt-4 grid gap-4 md:grid-cols-2">
          <div>
            <h4 className="mb-1 text-section-title">Licensing / state</h4>
            <KV label="Windows activated" value={os.activation?.activated} />
            <KV label="Activation status" value={os.activation?.status} />
            <KV label="Reboot pending" value={os.pending_reboot?.required} />
            <KV label="Power plan" value={os.power_plan?.active_plan} />
          </div>
          <div>
            <h4 className="mb-1 text-section-title">Enterprise join</h4>
            <KV label="Azure AD joined" value={os.join_status?.azure_ad_joined} />
            <KV label="Domain joined" value={os.join_status?.domain_joined} />
            <KV label="Domain" value={os.join_status?.domain_name} />
            <KV label="Azure tenant" value={os.join_status?.azure_tenant} />
          </div>
        </div>

        {/* Security */}
        <div className="mt-4 grid gap-4 md:grid-cols-2">
          <div>
            <h4 className="mb-1 text-section-title">
              Security {sec.protection_active ? "(Protected)" : "(At risk)"}
            </h4>
            <KV label="Real-time protection" value={sec.windows_defender?.realtime_protection} />
            <KV label="Antivirus enabled" value={sec.windows_defender?.antivirus_enabled} />
            <KV
              label="Signature age"
              value={sec.windows_defender?.signature_age_days != null ? `${sec.windows_defender.signature_age_days} day(s)` : null}
            />
            <KV
              label="Last quick scan"
              value={sec.windows_defender?.last_quick_scan_days_ago != null ? `${sec.windows_defender.last_quick_scan_days_ago} day(s) ago` : null}
            />
            <KV label="Firewall all on" value={sec.firewall?.all_enabled} />
            <KV label="System drive encrypted" value={sec.bitlocker?.system_drive_protected} />
            <KV label="UAC enabled" value={sec.uac?.enabled} />
            <KV label="Tamper protection" value={sec.windows_defender?.tamper_protection} />
          </div>
          <div>
            <h4 className="mb-1 text-section-title">Platform / access security</h4>
            <KV label="Secure Boot" value={sec.secure_boot?.enabled} />
            <KV label="TPM present" value={sec.tpm?.present} />
            <KV label="TPM ready" value={sec.tpm?.ready} />
            <KV label="TPM version" value={sec.tpm?.spec_version} />
            <KV label="RDP enabled" value={sec.remote_access?.rdp_enabled} />
            <KV label="SMBv1 enabled" value={sec.remote_access?.smb1_enabled} />
            <KV label="Local administrators" value={sec.local_accounts?.administrator_count} />
            <KV label="Guest account enabled" value={sec.local_accounts?.guest_account_enabled} />
          </div>
        </div>

        {/* Local administrators detail */}
        {(sec.local_accounts?.administrators ?? []).length > 0 && (
          <div className="mt-4">
            <h4 className="mb-1 text-section-title">Local administrators</h4>
            <Table
              rows={sec.local_accounts.administrators}
              columns={[
                { key: "name", label: "Account" },
                { key: "type", label: "Type" },
                { key: "source", label: "Source" },
              ]}
            />
          </div>
        )}

        {/* Networking */}
        <div className="mt-4 grid gap-4 md:grid-cols-2">
          <div>
            <h4 className="mb-1 text-section-title">Networking</h4>
            <KV label="IP address" value={net.ip_config?.ip_address} />
            <KV label="Gateway" value={net.ip_config?.gateway} />
            <KV label="DNS servers" value={net.ip_config?.dns_servers} />
            <KV label="Internet" value={conn.internet} />
            <KV label="Internet latency" value={conn.internet_latency_ms != null ? `${conn.internet_latency_ms} ms` : null} />
            <KV label="DNS resolution" value={conn.dns_resolution} />
            <KV label="Proxy enabled" value={net.proxy?.proxy_enabled} />
            <KV label="Proxy server" value={net.proxy?.proxy_server} />
          </div>
          <div>
            <h4 className="mb-1 text-section-title">Wi-Fi / exposure</h4>
            <KV label="Wi-Fi connected" value={net.wifi?.connected} />
            <KV label="SSID" value={net.wifi?.ssid} />
            <KV label="Signal" value={net.wifi?.signal_pct != null ? `${net.wifi.signal_pct}%` : null} />
            <KV label="Band / radio" value={net.wifi?.band ? `${net.wifi.band} · ${net.wifi.radio_type ?? ""}` : net.wifi?.radio_type} />
            <KV label="Listening ports" value={net.connections?.listening_port_count} />
            <KV label="Established connections" value={net.connections?.established_count} />
          </div>
        </div>

        {/* Notable open ports */}
        {(net.connections?.notable_listening ?? []).length > 0 && (
          <div className="mt-4">
            <h4 className="mb-1 text-xs font-semibold uppercase text-severity-warning">
              Notable listening ports
            </h4>
            <Table
              rows={net.connections.notable_listening}
              columns={[
                { key: "port", label: "Port" },
                { key: "service", label: "Service" },
                { key: "process", label: "Process" },
              ]}
            />
          </div>
        )}

        {/* Stability: crashes + services */}
        <div className="mt-4 grid gap-4 md:grid-cols-2">
          <div>
            <h4 className="mb-1 text-section-title">Stability</h4>
            <KV label="App crashes (7d)" value={crash.summary?.crash_count} />
            <KV label="App hangs (7d)" value={crash.summary?.hang_count} />
            <KV label="BSODs (30d)" value={crash.summary?.bsod_count} />
            <KV label="Minidumps" value={crash.summary?.minidump_count} />
          </div>
          <div>
            <h4 className="mb-1 text-section-title">
              Services ({svc.running_count ?? 0}/{svc.total_count ?? 0} running)
            </h4>
            {(svc.failed_critical ?? []).length > 0 ? (
              <p className="text-sm text-severity-warning">
                {svc.failed_critical.length} critical service(s) not running.
              </p>
            ) : (
              <p className="text-caption text-content-body">All monitored critical services running.</p>
            )}
            <KV label="Startup programs" value={startup.total_count} />
            <KV label="High-impact startup" value={startup.high_impact_count} />
            <KV label="Scheduled tasks (enabled)" value={startup.scheduled_tasks?.enabled_total} />
            <KV label="Logon/boot tasks" value={startup.scheduled_tasks?.logon_boot_count} />
          </div>
        </div>

        {/* Top processes */}
        <div className="mt-4">
          <h4 className="mb-1 text-section-title">
            Top processes by CPU ({proc.total_processes ?? 0} running)
          </h4>
          <Table
            rows={(proc.top_cpu ?? []).slice(0, 10)}
            columns={[
              { key: "name", label: "Name" },
              { key: "pid", label: "PID" },
              { key: "cpu_pct", label: "CPU %" },
              { key: "memory_mb", label: "Mem MB" },
            ]}
          />
        </div>

        {/* Event logs */}
        <div className="mt-4">
          <h4 className="mb-1 text-section-title">
            Recent errors / warnings
            {logs.summary ? ` (${logs.summary.errors} errors · ${logs.summary.warnings} warnings)` : ""}
          </h4>
          <Table
            rows={[...(logs.application ?? []), ...(logs.system ?? [])].slice(0, 15)}
            columns={[
              { key: "level", label: "Level" },
              { key: "source", label: "Source" },
              { key: "event_id", label: "ID" },
              { key: "timestamp", label: "Time" },
              { key: "description", label: "Message" },
            ]}
          />
        </div>

        {/* Recently installed */}
        {(sw.recently_installed_30d ?? []).length > 0 && (
          <div className="mt-4">
            <h4 className="mb-1 text-section-title">
              Installed in the last 30 days ({sw.recently_installed_30d.length})
            </h4>
            <Table
              rows={sw.recently_installed_30d}
              columns={[
                { key: "name", label: "Name" },
                { key: "version", label: "Version" },
                { key: "publisher", label: "Publisher" },
                { key: "install_date", label: "Installed" },
              ]}
            />
          </div>
        )}

        {/* Remote access tools - audit relevance */}
        {(sw.remote_access_tools ?? []).length > 0 && (
          <div className="mt-4">
            <h4 className="mb-1 text-xs font-semibold uppercase text-severity-warning">
              Remote-access tools detected
            </h4>
            <Table
              rows={sw.remote_access_tools}
              columns={[
                { key: "name", label: "Name" },
                { key: "version", label: "Version" },
                { key: "publisher", label: "Publisher" },
              ]}
            />
          </div>
        )}

        {/* All installed applications */}
        <div className="mt-4">
          <h4 className="mb-1 text-section-title">
            All installed applications ({apps.length})
          </h4>
          <Table
            rows={apps}
            columns={[
              { key: "name", label: "Name" },
              { key: "version", label: "Version" },
              { key: "publisher", label: "Publisher" },
              { key: "install_date", label: "Installed" },
            ]}
          />
        </div>
      </CollapsibleSection>
    </div>
  );
}

export function MachineScanView() {
  const report = useStore((s) => s.machineReport);
  const storageReport = useStore((s) => s.storageReport);
  const isScanning = useStore((s) => s.isMachineScanning);
  const runMachineScan = useStore((s) => s.runMachineScan);

  if (isScanning) {
    return (
      <div className="relative h-full min-h-0">
        <LoadingAnimation active={isScanning} mode="scan" />
      </div>
    );
  }

  if (!report) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-4 px-6 text-center">
        <h1 className="text-2xl font-semibold text-content-primary">Full System Scan</h1>
        <p className="max-w-lg text-body text-content-body">
          Scans all hardware and software, runs deep storage analysis in parallel, Windows
          troubleshooter checks, and computes an overall health score with prioritized fix actions.
        </p>
        <button onClick={runMachineScan} className="btn-primary">
          Run Full System Scan
        </button>
      </div>
    );
  }

  const health = report.health_report;

  return (
    <div className="relative h-full min-h-0">
      <LenisScroll className="h-full" contentClassName="p-6">
      <div className="mx-auto max-w-5xl">
        {/* Health header */}
        <div className="card flex flex-col gap-6 p-6 sm:flex-row sm:items-center glass-card shadow-lg border border-white/40/50 hover:border-white/40/70 transition-all duration-200">
          <ScoreRing score={health.overall_score} status={health.overall_status} />
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <h1 className="text-lg font-black text-content-primary tracking-tight uppercase">Machine Health Status</h1>
                <p className="text-caption text-content-muted mt-0.5">
                  Scanned on {formatDateTime(report.generated_at)} · Duration: {report.scan_duration_seconds}s
                </p>
              </div>
              <div className="flex flex-wrap gap-2">
                <button
                  onClick={runMachineScan}
                  className="btn-primary text-xs font-bold uppercase tracking-wider px-4 py-2.5 rounded-xl shadow-md shadow-accent/15 hover:shadow-accent/25 hover:-translate-y-px active:translate-y-0 transition-all duration-150"
                >
                  Re-scan System
                </button>
              </div>
            </div>
            <div className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6">
              {Object.entries(health.categories).map(([name, cat]) => (
                <div key={name} className="rounded-xl border border-white/40/60 bg-white/35/40 px-3 py-2.5 text-center shadow-sm">
                  <div className={`text-base font-extrabold ${statusColor(cat.status)}`}>{cat.score}</div>
                  <div className="text-label mt-1">{name}</div>
                </div>
              ))}
            </div>
          </div>
        </div>

        {health.recommended_actions.length > 0 && (
          <CollapsibleSection
            title="Recommended Actions"
            subtitle={`${health.recommended_actions.length} prioritized item${health.recommended_actions.length === 1 ? "" : "s"}`}
            accent="warning"
            className="mt-4"
          >
            <ul className="space-y-2.5">
              {health.recommended_actions.map((a, i) => (
                <li key={i} className="flex items-start gap-2.5 rounded-xl border border-white/40/10 bg-white/30/10 p-3 text-caption text-content-secondary">
                  <span className="select-none text-sm font-bold leading-none text-accent">•</span>
                  <span className="leading-relaxed">{a}</span>
                </li>
              ))}
            </ul>
          </CollapsibleSection>
        )}

        <MachineScanTroubleshooter report={report} />

        {/* Intelligence: executive scorecard, predictive risk, compliance, knowledge graph */}
        <div className="mt-4 space-y-3">
          <IntelligenceSections report={report} />
        </div>

        {storageReport && (
          <div className="mt-4">
            <StorageAnalysisSection report={storageReport} />
          </div>
        )}

        {/* Category details */}
        <div className="mt-4 space-y-3">
          <Body report={report} />
        </div>
      </div>
      </LenisScroll>
    </div>
  );
}
