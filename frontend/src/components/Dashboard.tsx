import { useEffect } from "react";
import { useStore } from "@/store/useStore";
import { MetricCard } from "@/components/common/MetricCard";
import { LenisScroll } from "@/components/LenisScroll";

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

export function Dashboard() {
  const metrics = useStore((s) => s.metrics);
  const refreshMetrics = useStore((s) => s.refreshMetrics);
  const metricsLoading = useStore((s) => s.metricsLoading);

  useEffect(() => {
    refreshMetrics();
  }, [refreshMetrics]);

  if (!metrics) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-3">
        <div className="h-9 w-9 animate-spin rounded-full border-2 border-accent/20 border-t-accent" />
        <p className="text-sm font-medium text-content-primary">Loading system metrics…</p>
      </div>
    );
  }

  return (
    <LenisScroll className="h-full" contentClassName="p-6">
      <div className="mx-auto max-w-5xl space-y-6">
        <div className="flex items-center justify-between border-b border-white/40 pb-4">
          <div>
            <h1 className="text-lg font-extrabold tracking-tight text-content-primary">System Health Dashboard</h1>
            <p className="mt-0.5 text-caption text-content-muted">Live real-time telemetry from this PC</p>
          </div>
          <button
            onClick={refreshMetrics}
            disabled={metricsLoading}
            className="btn-ghost flex items-center gap-2 px-4 py-2 text-xs font-semibold normal-case tracking-normal"
          >
            {metricsLoading && (
              <div className="h-3 w-3 animate-spin rounded-full border-2 border-accent/30 border-t-accent" />
            )}
            {metricsLoading ? "Refreshing…" : "Refresh Telemetry"}
          </button>
        </div>

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <MetricCard
            label="CPU Utilization"
            value={`${metrics.cpu.usage_percent}%`}
            percent={metrics.cpu.usage_percent}
            sub={`${metrics.cpu.physical_cores ?? "?"} Cores · ${metrics.cpu.frequency_mhz ?? "?"} MHz`}
            icon={<CpuIcon className="h-5 w-5 text-accent/80" />}
          />
          <MetricCard
            label="RAM Memory"
            value={`${metrics.memory.usage_percent}%`}
            percent={metrics.memory.usage_percent}
            sub={`${metrics.memory.used_gb} / ${metrics.memory.total_gb} GB (${metrics.memory.available_gb} GB Free)`}
            icon={<RamIcon className="h-5 w-5 text-accent/80" />}
          />
          {metrics.disks.slice(0, 1).map((d) => (
            <MetricCard
              key={d.device}
              label={`Logical Drive ${d.device}`}
              value={`${d.usage_percent}%`}
              percent={d.usage_percent}
              sub={`${d.free_gb} GB Free of ${d.total_gb} GB`}
              icon={<DiskIcon className="h-5 w-5 text-accent/80" />}
            />
          ))}
          <MetricCard
            label="Network Connectivity"
            value={metrics.network.internet_connected ? "Online" : "Offline"}
            sub={`${metrics.network.primary_ip ?? "No IP"} · ${metrics.network.adapters.filter((a) => a.is_up).length} Active Adapters`}
            icon={<WifiIcon className={`h-5 w-5 ${metrics.network.internet_connected ? "text-severity-healthy/80" : "text-severity-critical/80"}`} />}
          />
          <MetricCard
            label="Battery Status"
            value={metrics.battery.present ? `${metrics.battery.percent}%` : "N/A"}
            percent={metrics.battery.present ? metrics.battery.percent ?? 0 : undefined}
            sub={metrics.battery.present ? (metrics.battery.charging ? "AC Power - Charging" : "On Battery") : "Desktop/No Battery"}
            icon={<BatteryIcon className="h-5 w-5 text-accent/80" />}
          />
          <MetricCard
            label="Operating System"
            value={`${metrics.os.system} ${metrics.os.release}`}
            sub={`Build ${metrics.os.build ?? "?"} · ${metrics.os.architecture}`}
            icon={<OsIcon className="h-5 w-5 text-accent/80" />}
          />
        </div>

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
