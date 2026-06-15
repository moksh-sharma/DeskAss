import { useEffect, useState, type ReactNode } from "react";
import { useStore } from "@/store/useStore";
import { MetricCard } from "@/components/common/MetricCard";
import { LenisScroll } from "@/components/LenisScroll";
import { formatDateTime } from "@/lib/format";
import type { MonitorEvent, MonitorTrendPoint } from "@/types";

function CpuIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2.5">
      <rect x="4" y="4" width="16" height="16" rx="2" />
      <path d="M9 9h6v6H9z" />
      <path d="M9 1v3M15 1v3M9 20v3M15 20v3M20 9h3M20 15h3M1 9h3M1 15h3" />
    </svg>
  );
}

function RamIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2.5">
      <path strokeLinecap="round" strokeLinejoin="round" d="M9 3v2m6-2v2M9 19v2m6-2v2M5 9H3m2 6H3m18-6h-2m2 6h-2M7 5h10a2 2 0 012 2v10a2 2 0 01-2 2H7a2 2 0 01-2-2V7a2 2 0 012-2z" />
    </svg>
  );
}

function DiskIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2.5">
      <path strokeLinecap="round" strokeLinejoin="round" d="M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4m0 5c0 2.21-3.582 4-8 4s-8-1.79-8-4" />
    </svg>
  );
}

function WifiIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2.5">
      <path strokeLinecap="round" strokeLinejoin="round" d="M12 18h.01M8 14a5 5 0 018 0M5 10a9 9 0 0114 0M2 6a13 13 0 0120 0" />
    </svg>
  );
}

function BatteryIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2.5">
      <rect x="1" y="6" width="18" height="12" rx="2" />
      <path d="M23 11v2" />
    </svg>
  );
}

function OsIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2.5">
      <rect x="2" y="3" width="20" height="14" rx="2" />
      <path d="M8 21h8M12 17v4" />
    </svg>
  );
}

function PulseIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2.5">
      <path strokeLinecap="round" strokeLinejoin="round" d="M3 12h4l2 6 4-14 2 8h6" />
    </svg>
  );
}

function CollapsibleSection({
  title, subtitle, children, defaultOpen = false,
}: { title: string; subtitle?: string; children: ReactNode; defaultOpen?: boolean }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="glass-card overflow-hidden">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between px-5 py-4 text-left hover:bg-white/20"
      >
        <div>
          <span className="text-sm font-bold uppercase tracking-tight text-content-primary">{title}</span>
          {subtitle && <span className="ml-2 text-caption text-content-muted">{subtitle}</span>}
        </div>
        <span className={`text-[10px] font-extrabold text-content-faint transition-transform ${open ? "rotate-180" : ""}`}>▼</span>
      </button>
      {open && <div className="border-t border-white/30 px-5 py-4">{children}</div>}
    </div>
  );
}

function MiniStat({ label, value, sub }: { label: string; value: ReactNode; sub?: string }) {
  return (
    <div className="rounded-xl border border-white/30 bg-white/30 px-3 py-2">
      <div className="text-[10px] font-bold uppercase tracking-wider text-content-muted">{label}</div>
      <div className="mt-0.5 text-sm font-bold text-content-primary">{value}</div>
      {sub && <div className="text-[10px] text-content-muted">{sub}</div>}
    </div>
  );
}

function eventRows(events: MonitorEvent[]) {
  return events.map((e) => (
    <div key={`${e.ts}-${e.title}`} className="border-b border-white/20 py-2 text-xs last:border-0">
      <div className="flex justify-between gap-2">
        <span className={`font-semibold ${sevClass(e.severity)}`}>{e.title}</span>
        <span className="shrink-0 text-[10px] text-content-muted">{formatDateTime(e.ts)}</span>
      </div>
      {e.detail && <div className="mt-0.5 text-content-muted">{e.detail}</div>}
    </div>
  ));
}

function TrendSparkline({ points }: { points: MonitorTrendPoint[] }) {
  if (!points || points.length < 2) {
    return <p className="text-xs italic text-content-muted">Trend chart appears after a few minutes of background monitoring.</p>;
  }
  const w = 100, h = 36;
  const line = (key: "cpu" | "mem") =>
    points.map((p, i) => {
      const x = (i / (points.length - 1)) * w;
      const y = h - ((p[key] ?? 0) / 100) * (h - 4) - 2;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    }).join(" ");
  return (
    <div>
      <svg viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" className="h-24 w-full">
        <polyline points={line("cpu")} fill="none" stroke="#8b5cf6" strokeWidth="1.2" vectorEffect="non-scaling-stroke" />
        <polyline points={line("mem")} fill="none" stroke="#0ea5e9" strokeWidth="1.2" vectorEffect="non-scaling-stroke" />
      </svg>
      <div className="mt-1 flex gap-4 text-[10px] font-semibold text-content-muted">
        <span className="flex items-center gap-1"><span className="inline-block h-2 w-3 rounded-sm bg-violet-500" /> CPU</span>
        <span className="flex items-center gap-1"><span className="inline-block h-2 w-3 rounded-sm bg-sky-500" /> RAM</span>
      </div>
    </div>
  );
}

function sevClass(sev: string): string {
  const s = (sev || "").toLowerCase();
  if (s === "critical" || s === "error") return "text-severity-critical";
  if (s === "warning") return "text-severity-warning";
  return "text-content-secondary";
}

const REFRESH_MS = 30_000;

export function Dashboard() {
  const metrics = useStore((s) => s.metrics);
  const refreshMetrics = useStore((s) => s.refreshMetrics);
  const metricsLoading = useStore((s) => s.metricsLoading);
  const monitorStatus = useStore((s) => s.monitorStatus);
  const monitorTrends = useStore((s) => s.monitorTrends);
  const monitorAlerts = useStore((s) => s.monitorAlerts);
  const monitorChanges = useStore((s) => s.monitorChanges);
  const monitorMemory = useStore((s) => s.monitorMemory);
  const monitorBoot = useStore((s) => s.monitorBoot);
  const monitorPredictions = useStore((s) => s.monitorPredictions);
  const incident = useStore((s) => s.incidentResult);
  const isReconstructing = useStore((s) => s.isReconstructing);
  const reconstructIncident = useStore((s) => s.reconstructIncident);
  const refreshMonitoring = useStore((s) => s.refreshMonitoring);

  const [incidentText, setIncidentText] = useState("My PC froze 20 minutes ago");
  const [windowMin, setWindowMin] = useState(30);

  useEffect(() => {
    refreshMetrics();
    refreshMonitoring();
    const timer = setInterval(() => {
      refreshMetrics();
      refreshMonitoring();
    }, REFRESH_MS);
    return () => clearInterval(timer);
  }, [refreshMetrics, refreshMonitoring]);

  if (!metrics) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-3">
        <div className="h-9 w-9 animate-spin rounded-full border-2 border-accent/20 border-t-accent" />
        <p className="text-sm font-medium text-content-primary">Loading system metrics…</p>
      </div>
    );
  }

  const live = monitorStatus?.current;
  const cpuPct = live?.cpu_pct ?? metrics.cpu.usage_percent;
  const memPct = live?.mem_used_pct ?? metrics.memory.usage_percent;
  const diskPct = live?.disk_used_pct ?? metrics.disks[0]?.usage_percent ?? 0;
  const diskFree = live?.disk_free_gb ?? metrics.disks[0]?.free_gb;
  const diskTotal = metrics.disks[0]?.total_gb;
  const diskDevice = metrics.disks[0]?.device ?? "C:";
  const avg = monitorTrends?.averages ?? {};
  const diskPred = monitorPredictions?.disk ?? {};
  const perf = monitorPredictions?.performance ?? {};
  const loading = metricsLoading;

  return (
    <LenisScroll className="h-full" contentClassName="p-6">
      <div className="mx-auto max-w-5xl space-y-6">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-white/40 pb-4">
          <div>
            <h1 className="flex items-center gap-2 text-lg font-extrabold tracking-tight text-content-primary">
              System Health Dashboard
              {monitorStatus?.active && (
                <span className="relative flex h-2 w-2">
                  <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-70" />
                  <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-500" />
                </span>
              )}
            </h1>
            <p className="mt-0.5 text-caption text-content-muted">
              Live telemetry from continuous monitoring
              {live?.ts && <> · updated {formatDateTime(live.ts)}</>}
              {monitorStatus?.samples ? <> · {monitorStatus.samples.toLocaleString()} samples</> : null}
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <button
              onClick={() => { refreshMetrics(); refreshMonitoring(); }}
              disabled={loading}
              className="btn-ghost flex items-center gap-2 px-4 py-2 text-xs font-semibold normal-case tracking-normal"
            >
              {loading ? (
                <div className="h-3 w-3 animate-spin rounded-full border-2 border-accent/30 border-t-accent" />
              ) : (
                <PulseIcon className="h-3.5 w-3.5" />
              )}
              {loading ? "Refreshing…" : "Refresh"}
            </button>
          </div>
        </div>

        {/* Monitoring summary strip */}
        {monitorStatus && (
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <div className="rounded-xl border border-white/30 bg-white/30 px-4 py-3">
              <div className="text-[10px] font-bold uppercase tracking-wider text-content-muted">Monitor</div>
              <div className="mt-1 text-sm font-bold text-severity-healthy">
                {monitorStatus.active ? "Active" : "Starting"}
              </div>
              <div className="text-[10px] text-content-muted">
                {monitorStatus.alerts_24h ? `${monitorStatus.alerts_24h} alerts / 24h` : "No alerts / 24h"}
              </div>
            </div>
            <div className="rounded-xl border border-white/30 bg-white/30 px-4 py-3">
              <div className="text-[10px] font-bold uppercase tracking-wider text-content-muted">Uptime</div>
              <div className="mt-1 text-sm font-bold text-content-primary">
                {monitorBoot?.uptime_hours != null ? `${monitorBoot.uptime_hours} h` : "-"}
              </div>
              <div className="text-[10px] text-content-muted">
                {monitorBoot?.boot_count ? `${monitorBoot.boot_count} boot(s) recorded` : "Boot history"}
              </div>
            </div>
            <div className="rounded-xl border border-white/30 bg-white/30 px-4 py-3">
              <div className="text-[10px] font-bold uppercase tracking-wider text-content-muted">7d avg CPU</div>
              <div className="mt-1 text-sm font-bold text-content-primary">{avg.cpu != null ? `${avg.cpu}%` : "-"}</div>
              <div className="text-[10px] text-content-muted">peak {avg.cpu_max ?? "-"}%</div>
            </div>
            <div className="rounded-xl border border-white/30 bg-white/30 px-4 py-3">
              <div className="text-[10px] font-bold uppercase tracking-wider text-content-muted">Disk forecast</div>
              <div className="mt-1 text-sm font-bold text-content-primary">
                {diskPred.days_until_full != null ? `Full in ~${diskPred.days_until_full}d` : "Stable"}
              </div>
              <div className="text-[10px] text-content-muted">
                {diskPred.change_gb_per_day != null ? `${diskPred.change_gb_per_day} GB/day` : "Collecting trend"}
              </div>
            </div>
          </div>
        )}

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <MetricCard
            label="CPU Utilization"
            value={`${cpuPct}%`}
            percent={cpuPct}
            sub={`${metrics.cpu.physical_cores ?? "?"} cores · ${live ? "live monitor" : metrics.cpu.frequency_mhz ?? "?"} ${live ? "" : "MHz"}`}
            icon={<CpuIcon className="h-5 w-5 text-accent/80" />}
          />
          <MetricCard
            label="RAM Memory"
            value={`${memPct}%`}
            percent={memPct}
            sub={`${metrics.memory.used_gb} / ${metrics.memory.total_gb} GB (${live?.mem_available_gb ?? metrics.memory.available_gb} GB free)`}
            icon={<RamIcon className="h-5 w-5 text-accent/80" />}
          />
          <MetricCard
            label={`Drive ${diskDevice}`}
            value={`${diskPct}%`}
            percent={diskPct}
            sub={`${diskFree} GB free of ${diskTotal} GB`}
            icon={<DiskIcon className="h-5 w-5 text-accent/80" />}
          />
          <MetricCard
            label="Network"
            value={metrics.network.internet_connected ? "Online" : "Offline"}
            sub={
              live?.net_down_mb_s != null
                ? `↓ ${live.net_down_mb_s} MB/s · ↑ ${live.net_up_mb_s ?? 0} MB/s`
                : `${metrics.network.primary_ip ?? "No IP"} · ${metrics.network.adapters.filter((a) => a.is_up).length} adapters`
            }
            icon={<WifiIcon className={`h-5 w-5 ${metrics.network.internet_connected ? "text-severity-healthy/80" : "text-severity-critical/80"}`} />}
          />
          <MetricCard
            label="Battery"
            value={live?.battery_pct != null ? `${live.battery_pct}%` : metrics.battery.present ? `${metrics.battery.percent}%` : "N/A"}
            percent={live?.battery_pct ?? (metrics.battery.present ? metrics.battery.percent ?? 0 : undefined)}
            sub={metrics.battery.present ? (metrics.battery.charging ? "AC Power - Charging" : "On Battery") : "Desktop / No Battery"}
            icon={<BatteryIcon className="h-5 w-5 text-accent/80" />}
          />
          <MetricCard
            label="Operating System"
            value={`${metrics.os.system} ${metrics.os.release}`}
            sub={`Build ${metrics.os.build ?? "?"} · ${metrics.os.architecture}`}
            icon={<OsIcon className="h-5 w-5 text-accent/80" />}
          />
        </div>

        <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
          <div className="glass-card p-5">
            <h3 className="mb-3 border-b border-white/40 pb-2 text-section-title">7-Day Resource Trend</h3>
            <TrendSparkline points={monitorTrends?.points ?? []} />
            <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
              <MiniStat label="Avg CPU" value={`${avg.cpu ?? "-"}%`} sub={`max ${avg.cpu_max ?? "-"}%`} />
              <MiniStat label="Avg RAM" value={`${avg.mem ?? "-"}%`} sub={`max ${avg.mem_max ?? "-"}%`} />
              <MiniStat label="Perf trend" value={perf.regression_detected ? "Regressed" : "Stable"} />
              <MiniStat label="Battery" value={monitorPredictions?.battery?.available ? `${monitorPredictions.battery.current_pct}%` : "N/A"} />
            </div>
          </div>
          <div className="glass-card p-5">
            <h3 className="mb-3 flex items-center justify-between border-b border-white/40 pb-2 text-section-title">
              <span>Recent Alerts</span>
              {(monitorAlerts?.length ?? 0) > 0 && (
                <span className="rounded-full bg-severity-warning/20 px-2 py-0.5 text-[10px] font-bold text-severity-warning">
                  {monitorAlerts.length}
                </span>
              )}
            </h3>
            {monitorAlerts.length === 0 ? (
              <p className="text-xs italic text-content-muted">No alerts or anomalies in the last 72 hours.</p>
            ) : (
              <ul className="max-h-48 space-y-2 overflow-y-auto text-xs">
                {monitorAlerts.slice(0, 8).map((a, i) => (
                  <li key={i} className="border-b border-white/20 pb-2 last:border-0">
                    <div className="flex justify-between gap-2">
                      <span className={`font-semibold ${sevClass(a.severity)}`}>{a.title}</span>
                      <span className="shrink-0 text-[10px] text-content-muted">{formatDateTime(a.ts)}</span>
                    </div>
                    {a.detail && <div className="mt-0.5 text-content-muted">{a.detail}</div>}
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>

        <CollapsibleSection title="Incident Reconstruction" subtitle="What happened & when" defaultOpen>
          <div className="flex flex-wrap items-end gap-2">
            <div className="min-w-0 flex-1">
              <label className="mb-1 block text-[10px] font-bold uppercase tracking-wider text-content-muted">When did it happen?</label>
              <input
                value={incidentText}
                onChange={(e) => setIncidentText(e.target.value)}
                placeholder="e.g. froze 20 minutes ago"
                className="w-full rounded-xl border border-white/40 bg-white/50 px-3 py-2 text-sm outline-none focus:border-accent/60"
              />
            </div>
            <div>
              <label className="mb-1 block text-[10px] font-bold uppercase tracking-wider text-content-muted">± min</label>
              <select value={windowMin} onChange={(e) => setWindowMin(Number(e.target.value))}
                      className="rounded-xl border border-white/40 bg-white/50 px-3 py-2 text-sm outline-none">
                {[15, 30, 60, 120].map((m) => <option key={m} value={m}>{m}</option>)}
              </select>
            </div>
            <button
              type="button"
              onClick={() => reconstructIncident(incidentText, windowMin)}
              disabled={isReconstructing || !incidentText.trim()}
              className="btn-primary px-4 py-2 text-sm font-semibold normal-case tracking-normal"
            >
              {isReconstructing ? "Analyzing…" : "Reconstruct"}
            </button>
          </div>
          {incident && (
            <div className="mt-4 space-y-3">
              <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
                <MiniStat label="Probable cause" value={<span className="text-xs leading-snug">{incident.probable_cause}</span>} />
                <MiniStat label="Confidence" value={`${incident.confidence}%`} />
                <MiniStat label="Peak CPU" value={`${incident.peak_cpu_pct}%`} />
                <MiniStat label="Peak RAM" value={`${incident.peak_mem_pct}%`} />
              </div>
              {incident.timeline.length > 0 && (
                <ol className="max-h-40 space-y-1 overflow-y-auto text-xs">
                  {incident.timeline.slice(0, 12).map((t, i) => (
                    <li key={i} className="flex gap-2">
                      <span className="w-28 shrink-0 font-mono text-[10px] text-content-muted">{(t.ts || "").slice(0, 19).replace("T", " ")}</span>
                      <span className={sevClass(t.severity || "info")}>{t.text}</span>
                    </li>
                  ))}
                </ol>
              )}
            </div>
          )}
        </CollapsibleSection>

        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <CollapsibleSection title="Machine Memory" subtitle="Long-term patterns">
            {monitorMemory && monitorMemory.facts.length > 0 ? (
              <ul className="space-y-2 text-sm text-content-secondary">
                {monitorMemory.facts.map((f, i) => (
                  <li key={i} className="flex gap-2">
                    <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-accent" />
                    {f}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-xs italic text-content-muted">Insights build up as monitoring history accumulates.</p>
            )}
          </CollapsibleSection>
          <CollapsibleSection title="Change Timeline" subtitle="Software, security, boots">
            {monitorChanges.length === 0 ? (
              <p className="text-xs italic text-content-muted">No changes detected yet.</p>
            ) : (
              <div className="max-h-48 overflow-y-auto">{eventRows(monitorChanges.slice(0, 10))}</div>
            )}
          </CollapsibleSection>
        </div>

        <CollapsibleSection title="Boot History" subtitle={monitorBoot?.uptime_hours != null ? `up ${monitorBoot.uptime_hours}h` : undefined}>
          {monitorBoot?.boots?.length ? (
            <div className="max-h-40 overflow-y-auto">{eventRows(monitorBoot.boots)}</div>
          ) : (
            <p className="text-xs italic text-content-muted">No boot events recorded yet.</p>
          )}
        </CollapsibleSection>

        <div className="grid grid-cols-1 gap-5 pt-2 lg:grid-cols-2">
          <ProcessTable title="Highest CPU Consumers" rows={metrics.top_cpu_processes} unit="%" field="cpu_percent" />
          <ProcessTable title="Highest Memory Consumers" rows={metrics.top_memory_processes} unit=" MB" field="memory_mb" />
        </div>
      </div>
    </LenisScroll>
  );
}

function ProcessTable({
  title,
  rows,
  unit,
  field,
}: {
  title: string;
  rows: { pid: number; name: string; cpu_percent: number; memory_mb: number }[];
  unit: string;
  field: "cpu_percent" | "memory_mb";
}) {
  return (
    <div className="glass-card p-5">
      <h3 className="mb-4 flex items-center justify-between border-b border-white/40 pb-2 text-section-title">
        <span>{title}</span>
        <span className="text-[10px] font-bold lowercase tracking-normal text-content-muted">
          ({rows.slice(0, 10).length} active)
        </span>
      </h3>
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-white/35 text-left text-[9px] font-extrabold uppercase tracking-wider text-content-muted">
              <th className="pb-1.5 font-bold">Process Name</th>
              <th className="pb-1.5 text-right font-bold">{field === "cpu_percent" ? "CPU Load" : "Memory Workset"}</th>
            </tr>
          </thead>
          <tbody>
            {rows.slice(0, 10).map((p, idx) => (
              <tr key={`${p.pid}-${idx}`} className="border-b border-white/30 transition-colors duration-100 last:border-0 hover:bg-white/30">
                <td className="flex items-center gap-2 py-2 font-semibold text-content-secondary">
                  <span className="select-none font-mono text-content-muted">{idx + 1}</span>
                  <span className="max-w-[200px] truncate">{p.name}</span>
                  <span className="font-mono text-[9px] font-bold text-content-muted">PID {p.pid}</span>
                </td>
                <td className="py-2 text-right font-bold text-content-secondary">
                  {p[field]}
                  <span className="text-[10px] font-medium text-content-muted">{unit}</span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
