import { useState } from "react";
import { useStore } from "@/store/useStore";
import { LoadingAnimation } from "@/components/LoadingAnimation";
import { LenisScroll } from "@/components/LenisScroll";
import { MachineScanTroubleshooter } from "@/components/MachineScanTroubleshooter";
import { formatDateTime } from "@/lib/format";
import type { MachineScanReport } from "@/types";

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

function Section({
  title,
  subtitle,
  children,
  defaultOpen = false,
}: {
  title: string;
  subtitle?: string;
  children: React.ReactNode;
  defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="card overflow-hidden border border-white/40/40 shadow-md glass-card hover:border-white/40/60 transition-all duration-200">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between px-5 py-4 text-left hover:bg-white/35/25 transition-colors relative"
      >
        <div className="absolute top-0 left-0 h-full w-1.5 bg-accent/40" />
        <div className="min-w-0">
          <span className="text-sm font-bold text-content-primary tracking-tight uppercase">{title}</span>
          {subtitle && <span className="ml-3 text-caption text-content-muted truncate">{subtitle}</span>}
        </div>
        <span className={`text-[10px] text-content-faint font-extrabold transition-transform duration-200 transform ${open ? "rotate-180" : ""}`}>
          ▼
        </span>
      </button>
      {open && <div className="border-t border-white/40/30 px-5 py-4 bg-white/30/10 space-y-4">{children}</div>}
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

function Body({ report }: { report: MachineScanReport }) {
  const hw = report.hardware ?? {};
  const sw = report.software ?? {};

  const cpu = hw.cpu ?? {};
  const ram = hw.ram ?? {};
  const perf = hw.performance ?? {};
  const devices = hw.devices ?? {};

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
      <Section
        title="Hardware"
        subtitle={`${cpu.processor_name ?? "System"} · ${devices.total_count ?? 0} devices`}
        defaultOpen
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
      </Section>

      {/* ============================== SOFTWARE ============================== */}
      <Section
        title="Software"
        subtitle={`${win.edition ?? "Windows"} · ${sw.installed_count ?? apps.length ?? 0} apps`}
        defaultOpen
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
      </Section>
    </div>
  );
}

export function MachineScanView() {
  const report = useStore((s) => s.machineReport);
  const isScanning = useStore((s) => s.isMachineScanning);
  const isGeneratingSummary = useStore((s) => s.isGeneratingMachineSummary);
  const runMachineScan = useStore((s) => s.runMachineScan);
  const generateMachineSummary = useStore((s) => s.generateMachineSummary);
  const resolveIssue = useStore((s) => s.resolveIssue);

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
          Scans all hardware and software, runs the Windows troubleshooter for actionable fixes, and
          computes an overall health score. Generate an AI summary afterward for a full narrative.
        </p>
        <button onClick={runMachineScan} className="btn-primary">
          Run Full System Scan
        </button>
      </div>
    );
  }

  const health = report.health_report;
  const ai = report.ai_summary;
  const hasAiSummary = Boolean(ai?.summary?.trim());

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
                  onClick={generateMachineSummary}
                  disabled={isGeneratingSummary}
                  className="btn-primary text-xs font-bold uppercase tracking-wider px-4 py-2.5 rounded-xl shadow-md shadow-accent/15 hover:shadow-accent/25 hover:-translate-y-px active:translate-y-0 transition-all duration-150 disabled:opacity-60 disabled:pointer-events-none"
                >
                  {isGeneratingSummary
                    ? "Generating Summary…"
                    : hasAiSummary
                      ? "Regenerate AI Summary"
                      : "Generate AI Summary"}
                </button>
                <button
                  onClick={runMachineScan}
                  className="btn-ghost text-xs font-bold uppercase tracking-wider px-4 py-2.5 rounded-xl transition-all active:scale-95 duration-100"
                  disabled={isGeneratingSummary}
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

        {/* AI summary (on demand) */}
        {hasAiSummary && !isGeneratingSummary && (
          <div className="card mt-4 border border-accent/20 bg-gradient-to-br from-accent/5 to-transparent p-6 shadow-lg relative overflow-hidden">
            <div className="absolute top-0 left-0 h-1 w-full bg-gradient-to-r from-accent to-blue-400" />
            <div className="mb-3 flex items-center gap-2">
              <span className="rounded-full bg-accent/15 border border-accent/20 px-2.5 py-0.5 text-[9px] font-extrabold uppercase tracking-widest text-accent flex items-center gap-1">
                <span className="h-1.5 w-1.5 rounded-full bg-accent animate-pulse" />
                AI Summary{ai.model ? ` · ${ai.model}` : ""}
              </span>
            </div>
            <p className="text-body text-content-primary">{ai.summary}</p>
            {(ai.prioritized_actions?.length ?? 0) > 0 && (
              <ol className="mt-4 space-y-2 text-caption text-content-secondary">
                {(ai.prioritized_actions ?? []).map((a, i) => (
                  <li key={i} className="flex gap-3 items-start bg-white/30/10 border border-white/40/10 p-2.5 rounded-xl">
                    <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-lg bg-accent text-[10px] font-black text-content-primary shadow-sm shadow-accent/10 select-none">
                      {i + 1}
                    </span>
                    <span className="pt-0.5 leading-relaxed font-semibold">{a}</span>
                  </li>
                ))}
              </ol>
            )}
          </div>
        )}

        {/* Recommended actions (deterministic) - hidden when the AI summary already covers them */}
        {!hasAiSummary && health.recommended_actions.length > 0 && (
          <div className="card mt-4 p-5 glass-card border-l-4 border-severity-warning/45 shadow-md">
            <h2 className="mb-3 text-section-title flex items-center gap-2">
              <span className="h-2 w-2 rounded-full bg-severity-warning animate-pulse" />
              Recommended Actions
            </h2>
            <ul className="space-y-2.5">
              {health.recommended_actions.map((a, i) => (
                <li key={i} className="flex items-start gap-2.5 text-caption text-content-secondary bg-white/30/10 border border-white/40/10 p-3 rounded-xl">
                  <span className="text-accent text-sm leading-none font-bold select-none">•</span>
                  <span className="leading-relaxed">{a}</span>
                </li>
              ))}
            </ul>
            <button
              onClick={() =>
                resolveIssue(
                  `Here is my machine health report (score ${health.overall_score}/100, ${health.overall_status}). ` +
                  `Key issues: ${health.recommended_actions.join("; ")}. ` +
                  `What should I prioritise and how do I fix these?`,
                )
              }
              className="mt-4 rounded-xl bg-accent px-4 py-2 text-xs font-bold uppercase tracking-wider text-content-primary shadow-md shadow-accent/10 hover:shadow-accent/20 transition-all hover:-translate-y-px duration-100 flex items-center gap-1.5"
            >
              <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2.5">
                <path strokeLinecap="round" strokeLinejoin="round" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
              </svg>
              Ask AI to help fix these
            </button>
          </div>
        )}

        <MachineScanTroubleshooter report={report} />

        {/* Category details */}
        <div className="mt-4 space-y-3">
          <Body report={report} />
        </div>
      </div>
      </LenisScroll>

      <LoadingAnimation active={isGeneratingSummary} mode="summary" />
    </div>
  );
}
