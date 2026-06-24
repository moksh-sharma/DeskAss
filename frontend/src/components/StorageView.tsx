import { type ReactNode } from "react";
import { formatDateTime } from "@/lib/format";
import { CollapsibleSection } from "@/components/common/CollapsibleSection";
import type { StorageReport } from "@/types";

// ────────────────────────────────────────────────────────────── helpers ──
function usageColor(pct: number): string {
  if (pct >= 95) return "bg-severity-critical";
  if (pct >= 85) return "bg-severity-warning";
  if (pct >= 70) return "bg-amber-400";
  return "bg-emerald-400";
}

function fmtGB(gb: number | null | undefined): string {
  if (gb === null || gb === undefined) return "-";
  if (gb >= 1) return `${gb.toFixed(gb >= 100 ? 0 : 1)} GB`;
  if (gb > 0) return `${Math.round(gb * 1024)} MB`;
  return "0";
}

function Section({
  title, subtitle, children, defaultOpen = false, badge, collapsible = true,
}: {
  title: string; subtitle?: string; children: ReactNode; defaultOpen?: boolean; badge?: ReactNode;
  collapsible?: boolean;
}) {
  if (!collapsible) {
    return (
      <ReportBlock title={title} subtitle={subtitle} badge={badge}>
        {children}
      </ReportBlock>
    );
  }
  return (
    <CollapsibleSection title={title} subtitle={subtitle} defaultOpen={defaultOpen} badge={badge}>
      {children}
    </CollapsibleSection>
  );
}

function ReportBlock({
  title,
  subtitle,
  badge,
  children,
}: {
  title: string;
  subtitle?: string;
  badge?: ReactNode;
  children: ReactNode;
}) {
  return (
    <div className="rounded-xl border border-white/40 bg-white/25 p-4 shadow-sm">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2 border-b border-white/30 pb-2">
        <div className="min-w-0">
          <h4 className="text-section-title">{title}</h4>
          {subtitle && (
            <p className="mt-0.5 whitespace-normal break-words text-caption text-content-muted">{subtitle}</p>
          )}
        </div>
        {badge}
      </div>
      {children}
    </div>
  );
}

function Table({ rows, columns, empty = "No records found." }: {
  rows: any[]; columns: { key: string; label: string; render?: (r: any) => ReactNode }[]; empty?: string;
}) {
  if (!rows || rows.length === 0) return <p className="text-empty text-xs italic text-content-muted">{empty}</p>;
  return (
    <div className="overflow-hidden rounded-xl border border-white/30 shadow-inner">
      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs">
          <thead>
            <tr className="border-b border-white/30 bg-white/30 text-[9px] font-bold uppercase tracking-wider text-content-muted">
              {columns.map((c) => <th key={c.key} className="px-3.5 py-2.5 font-extrabold">{c.label}</th>)}
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={i} className="border-t border-white/20 transition-colors hover:bg-white/20">
                {columns.map((c) => (
                  <td key={c.key} className="px-3.5 py-2 font-medium text-content-secondary">
                    {c.render ? c.render(r) : r[c.key] === null || r[c.key] === undefined || r[c.key] === "" ? "-" : String(r[c.key])}
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

/** Horizontal bar list used for cleanup, file types, top folders, etc. */
function BarList({ items, color = "bg-accent", unit = "GB" }: {
  items: { label: string; value: number | null | undefined; sub?: string }[];
  color?: string; unit?: string;
}) {
  const vals = items.map((i) => i.value ?? 0);
  const max = Math.max(1, ...vals);
  if (items.length === 0) return <p className="text-xs italic text-content-muted">Nothing detected.</p>;
  return (
    <div className="space-y-2">
      {items.map((it, i) => {
        const v = it.value ?? 0;
        const pct = Math.max(2, Math.round((v / max) * 100));
        return (
          <div key={i} className="text-xs">
            <div className="mb-0.5 flex items-baseline justify-between gap-3">
              <span className="min-w-0 truncate font-medium text-content-secondary" title={it.label}>{it.label}</span>
              <span className="shrink-0 font-bold text-content-primary">
                {unit === "GB" ? fmtGB(v) : `${v} ${unit}`}
                {it.sub && <span className="ml-1 font-normal text-content-muted">{it.sub}</span>}
              </span>
            </div>
            <div className="h-2 overflow-hidden rounded-full bg-white/40">
              <div className={`h-full rounded-full ${color} transition-all duration-700`} style={{ width: `${pct}%` }} />
            </div>
          </div>
        );
      })}
    </div>
  );
}

function Stat({ label, value, tone = "default" }: { label: string; value: ReactNode; tone?: "default" | "warn" | "crit" | "good" }) {
  const toneClass =
    tone === "crit" ? "text-severity-critical" : tone === "warn" ? "text-severity-warning"
    : tone === "good" ? "text-severity-healthy" : "text-content-primary";
  return (
    <div className="rounded-xl border border-white/30 bg-white/30 px-4 py-3">
      <div className="text-[10px] font-bold uppercase tracking-wider text-content-muted">{label}</div>
      <div className={`mt-1 text-xl font-black tracking-tight ${toneClass}`}>{value}</div>
    </div>
  );
}

function shortPath(p: string, max = 60): string {
  if (!p) return "-";
  if (p.length <= max) return p;
  return "…" + p.slice(-(max - 1));
}

// ─────────────────────────────────────────────────────────── timeline ──
function Timeline({ points }: { points: NonNullable<StorageReport["timeline"]> }) {
  if (!points || points.length < 2) {
    return <p className="text-xs italic text-content-muted">Run more scans over time to chart storage growth.</p>;
  }
  const free = points.map((p) => p.primary_free_gb ?? 0);
  const max = Math.max(1, ...free);
  const min = Math.min(...free);
  const range = Math.max(1, max - min);
  const w = 100, h = 36;
  const coords = points.map((p, i) => {
    const x = (i / (points.length - 1)) * w;
    const y = h - ((p.primary_free_gb - min) / range) * (h - 6) - 3;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  });
  return (
    <div>
      <svg viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" className="h-20 w-full">
        <polyline points={coords.join(" ")} fill="none" stroke="#6366f1" strokeWidth="1.2" />
      </svg>
      <div className="mt-1 flex justify-between text-[10px] text-content-muted">
        <span>{formatDateTime(points[0].scanned_at)} · {fmtGB(points[0].primary_free_gb)} free</span>
        <span>{formatDateTime(points[points.length - 1].scanned_at)} · {fmtGB(points[points.length - 1].primary_free_gb)} free</span>
      </div>
    </div>
  );
}

// ───────────────────────────────────────────────────────────── body ──
/** Deep storage analysis sections - embedded in Full System Scan. */
export function StorageReportSections({
  report,
  collapsible = false,
}: {
  report: StorageReport;
  /** When false (default), section content is always visible inside Storage Analysis. */
  collapsible?: boolean;
}) {
  const drives = report.drives ?? [];
  const cleanup = report.cleanup ?? { quick_wins: [], safe_cleanup: [], advanced_cleanup: [], total_potential_gb: 0 };
  const tree = report.tree ?? {};
  const fileTypes = report.file_type_distribution ?? tree.file_type_distribution ?? [];
  const footprint = report.application_footprint ?? {};
  const dev = report.developer_storage ?? {};
  const mlModels = report.ai_models ?? {};
  const downloads = report.downloads ?? {};
  const media = report.media ?? {};
  const archives = report.archives ?? {};
  const cloud = report.cloud_storage ?? [];
  const win = report.windows_storage ?? {};
  const recovery = report.recovery ?? {};
  const vm = report.vm_storage ?? {};
  const dupes = report.duplicates ?? {};
  const growth = report.growth ?? {};
  const changes = report.change_tracking ?? {};

  const topFolders = (tree.top_folders ?? []) as any[];
  const topFiles = (tree.top_files ?? []) as any[];

  return (
    <div className="space-y-4">
      {/* DRIVE USAGE */}
      <Section title="Drive Usage" subtitle={`${drives.length} drive(s)`} collapsible={collapsible}>
        {drives.length === 0 ? (
          <p className="text-xs italic text-content-muted">No drives detected. Re-run the full system scan.</p>
        ) : (
          <div className="space-y-3">
            {drives.map((d) => (
              <div key={d.drive} className="text-xs">
                <div className="mb-1 flex flex-wrap items-baseline justify-between gap-2">
                  <span className="font-bold text-content-primary">
                    {d.drive} {d.file_system ? `· ${d.file_system}` : ""}
                  </span>
                  <span className="whitespace-normal break-words font-semibold text-content-secondary">
                    {fmtGB(d.used_gb)} used · {fmtGB(d.free_gb)} free of {fmtGB(d.total_gb)} ({d.used_pct}%)
                  </span>
                </div>
                <div className="h-3 overflow-hidden rounded-full bg-white/40">
                  <div
                    className={`h-full rounded-full ${usageColor(d.used_pct)} transition-all duration-700`}
                    style={{ width: `${Math.min(100, d.used_pct)}%` }}
                  />
                </div>
              </div>
            ))}
          </div>
        )}
      </Section>

      {/* CLEANUP RECOMMENDATIONS */}
      <Section
        title="Cleanup Recommendations"
        subtitle={`~${fmtGB(cleanup.total_potential_gb)} recoverable`}
        collapsible={collapsible}
        badge={
          <span className="rounded-full border border-emerald-300/50 bg-emerald-100/60 px-2 py-0.5 text-[10px] font-bold text-emerald-700">
            {fmtGB(cleanup.total_potential_gb)}
          </span>
        }
      >
        <div className="grid gap-5 md:grid-cols-3">
          <div>
            <h4 className="mb-2 text-section-title text-emerald-600">Quick Wins</h4>
            <BarList color="bg-emerald-400" items={(cleanup.quick_wins ?? []).map((c) => ({ label: c.label, value: c.recover_gb }))} />
          </div>
          <div>
            <h4 className="mb-2 text-section-title text-sky-600">Safe Cleanup</h4>
            <BarList color="bg-sky-400" items={(cleanup.safe_cleanup ?? []).map((c) => ({ label: c.label, value: c.recover_gb }))} />
          </div>
          <div>
            <h4 className="mb-2 text-section-title text-amber-600">Advanced Cleanup</h4>
            <BarList color="bg-amber-400" items={(cleanup.advanced_cleanup ?? []).map((c) => ({ label: c.label, value: c.recover_gb }))} />
          </div>
        </div>
      </Section>

      {/* FILE TYPE DISTRIBUTION */}
      <Section title="File Type Distribution" subtitle={`${tree.total_files_scanned?.toLocaleString?.() ?? "?"} files scanned`} collapsible={collapsible}>
        <BarList color="bg-violet-400" items={(fileTypes as any[]).slice(0, 14).map((t) => ({ label: t.category, value: t.size_gb, sub: `${t.pct ?? ""}%` }))} />
        {tree.truncated && <p className="mt-2 text-[10px] italic text-content-muted">Scan was time-bounded; very deep folders may be partially counted.</p>}
      </Section>

      {/* LARGEST FOLDERS */}
      <Section title="Largest Folders" subtitle={`top ${Math.min(topFolders.length, 1000)}`} collapsible={collapsible}>
        <Table
          rows={topFolders.slice(0, 100)}
          columns={[
            { key: "path", label: "Folder", render: (r) => <span title={r.path}>{shortPath(r.path)}</span> },
            { key: "size_gb", label: "Size", render: (r) => fmtGB(r.size_gb) },
            { key: "file_count", label: "Files" },
            { key: "pct_of_scanned", label: "% scan", render: (r) => `${r.pct_of_scanned ?? 0}%` },
          ]}
        />
      </Section>

      {/* LARGEST FILES */}
      <Section title="Largest Files" subtitle={`top ${Math.min(topFiles.length, 1000)}`} collapsible={collapsible}>
        <Table
          rows={topFiles.slice(0, 100)}
          columns={[
            { key: "path", label: "File", render: (r) => <span title={r.path}>{shortPath(r.path)}</span> },
            { key: "size_gb", label: "Size", render: (r) => fmtGB(r.size_gb) },
          ]}
        />
      </Section>

      {/* APPLICATION FOOTPRINT */}
      <Section title="Application Footprint" subtitle={`${footprint.total_apps ?? 0} apps`} collapsible={collapsible}>
        <BarList items={((footprint.top ?? []) as any[]).map((a) => ({ label: a.name, value: a.total_gb ?? a.install_size_gb }))} />
        {footprint.docker?.breakdown && (
          <div className="mt-4">
            <h4 className="mb-1 text-section-title">Docker</h4>
            <Table
              rows={footprint.docker.breakdown}
              columns={[
                { key: "type", label: "Type" },
                { key: "size", label: "Size" },
                { key: "reclaimable", label: "Reclaimable" },
              ]}
            />
          </div>
        )}
      </Section>

      {/* DEVELOPER STORAGE */}
      <Section title="Developer Storage" subtitle="node_modules · caches · git" collapsible={collapsible}>
        <div className="grid gap-4 md:grid-cols-2">
          <Stat label="node_modules total" value={fmtGB(dev.node_modules?.total_gb)} />
          <Stat label="node_modules projects" value={dev.node_modules?.project_count ?? 0} />
          <Stat label="Git repositories" value={dev.git_repositories?.repo_count ?? 0} />
          <Stat label="Git repos total" value={fmtGB(dev.git_repositories?.total_gb)} />
        </div>
        <div className="mt-4">
          <h4 className="mb-2 text-section-title">Package caches</h4>
          <BarList items={[
            { label: "pip cache", value: dev.python?.pip_cache?.size_gb },
            { label: "Conda packages", value: dev.python?.conda_pkgs?.size_gb },
            { label: "Maven (.m2)", value: dev.java?.maven_cache?.size_gb },
            { label: "Gradle (.gradle)", value: dev.java?.gradle_cache?.size_gb },
            { label: "npm cache", value: dev.node?.npm_cache?.size_gb },
            { label: "NuGet packages", value: dev.dotnet?.nuget_cache?.size_gb },
            { label: "VS Code extensions", value: dev.vs_code?.extensions?.size_gb },
            { label: "Cursor extensions", value: dev.cursor?.extensions?.size_gb },
            { label: "Android SDK", value: dev.android?.sdk?.size_gb },
          ].filter((i) => (i.value ?? 0) > 0)} />
        </div>
        {(dev.node_modules?.projects ?? []).length > 0 && (
          <div className="mt-4">
            <h4 className="mb-1 text-section-title">Biggest node_modules</h4>
            <Table
              rows={dev.node_modules.projects.slice(0, 20)}
              columns={[
                { key: "path", label: "Project", render: (r) => <span title={r.path}>{shortPath(r.path)}</span> },
                { key: "size_gb", label: "Size", render: (r) => fmtGB(r.size_gb) },
              ]}
            />
          </div>
        )}
      </Section>

      {/* LOCAL ML MODEL CACHES */}
      <Section title="Local ML Model Caches" subtitle={`~${fmtGB(mlModels.total_gb)} total`} collapsible={collapsible}>
        <div className="grid gap-4 md:grid-cols-2">
          <Stat label="Ollama" value={fmtGB(mlModels.ollama?.total_gb)} />
          <Stat label="LM Studio" value={fmtGB(mlModels.lm_studio?.size_gb)} />
          <Stat label="HuggingFace" value={fmtGB(mlModels.huggingface?.size_gb)} />
          <Stat label="PyTorch cache" value={fmtGB(mlModels.torch?.size_gb)} />
        </div>
        {(mlModels.ollama?.models ?? []).length > 0 && (
          <div className="mt-4">
            <h4 className="mb-1 text-section-title">Ollama models ({mlModels.ollama.model_count})</h4>
            <div className="flex flex-wrap gap-1.5">
              {mlModels.ollama.models.map((m: any, i: number) => (
                <span key={i} className="rounded-lg border border-white/40 bg-white/40 px-2 py-1 text-[11px] font-medium text-content-secondary">{m.name}</span>
              ))}
            </div>
          </div>
        )}
      </Section>

      {/* DOWNLOADS / ARCHIVES / MEDIA */}
      <Section title="Downloads, Archives & Media" subtitle={downloads.available ? `Downloads ~${fmtGB(downloads.total_gb)}` : undefined} collapsible={collapsible}>
        {downloads.available && (
          <div className="mb-4">
            <h4 className="mb-2 text-section-title">Downloads by category</h4>
            <BarList items={Object.entries(downloads.categories ?? {}).map(([k, v]: [string, any]) => ({ label: k, value: v.size_gb, sub: `${v.count} files` }))} />
            <div className="mt-2 grid gap-3 md:grid-cols-2">
              <Stat label="Older than 90 days" value={fmtGB(downloads.old_downloads_gb)} tone="warn" />
              <Stat label="Total downloads" value={fmtGB(downloads.total_gb)} />
            </div>
          </div>
        )}
        <div className="grid gap-4 md:grid-cols-3">
          <Stat label="Archives > 90d" value={fmtGB(archives.older_than_90d_gb)} />
          <Stat label="Archives > 180d" value={fmtGB(archives.older_than_180d_gb)} />
          <Stat label="Archives > 365d" value={fmtGB(archives.older_than_365d_gb)} />
        </div>
        {(media.largest_videos ?? []).length > 0 && (
          <div className="mt-4">
            <h4 className="mb-1 text-section-title">Largest videos</h4>
            <Table
              rows={media.largest_videos.slice(0, 10)}
              columns={[
                { key: "path", label: "File", render: (r) => <span title={r.path}>{shortPath(r.path)}</span> },
                { key: "size_gb", label: "Size", render: (r) => fmtGB(r.size_gb) },
              ]}
            />
          </div>
        )}
      </Section>

      {/* DUPLICATES */}
      <Section title="Duplicate Files" subtitle={`${dupes.group_count ?? 0} groups · ~${fmtGB(dupes.recoverable_gb)} recoverable`} collapsible={collapsible}>
        <Table
          rows={(dupes.duplicate_groups ?? []).slice(0, 40)}
          empty="No duplicates detected in the scanned set."
          columns={[
            { key: "original", label: "Original", render: (r) => <span title={r.original}>{shortPath(r.original, 48)}</span> },
            { key: "copies", label: "Copies" },
            { key: "size_gb", label: "Each", render: (r) => fmtGB(r.size_gb) },
            { key: "recoverable_gb", label: "Recoverable", render: (r) => fmtGB(r.recoverable_gb) },
          ]}
        />
      </Section>

      {/* CLOUD */}
      <Section title="Cloud Storage" subtitle={`${cloud.length} provider(s)`} collapsible={collapsible}>
        <Table
          rows={cloud}
          empty="No cloud sync folders detected."
          columns={[
            { key: "provider", label: "Provider" },
            { key: "path", label: "Path", render: (r) => <span title={r.path}>{shortPath(r.path)}</span> },
            { key: "local_size_gb", label: "Local size", render: (r) => fmtGB(r.local_size_gb) },
            { key: "file_count", label: "Files" },
          ]}
        />
      </Section>

      {/* WINDOWS + RECOVERY */}
      <Section title="Windows & Recovery" subtitle="system components" collapsible={collapsible}>
        <div className="grid gap-3 md:grid-cols-3">
          <Stat label="WinSxS (component store)" value={win.winsxs?.actual_size ?? "-"} />
          <Stat label="Windows Update cache" value={fmtGB(win.windows_update_cache_gb)} />
          <Stat label="Windows Temp" value={fmtGB(win.temp_gb)} />
          <Stat label="Installer cache" value={fmtGB(win.installer_cache_gb)} />
          <Stat label="Memory dump" value={fmtGB(win.memory_dump_gb)} />
          <Stat label="Prefetch" value={fmtGB(win.prefetch_gb)} />
        </div>
        {win.winsxs?.cleanup_recommended && (
          <p className="mt-3 text-xs font-semibold text-severity-warning">
            Windows recommends a component store cleanup - run <code>Dism /Online /Cleanup-Image /StartComponentCleanup</code>.
          </p>
        )}
        <div className="mt-4 grid gap-3 md:grid-cols-3">
          <Stat label="Restore points" value={recovery.restore_point_count ?? 0} />
          <Stat label="Shadow copy used" value={recovery.shadow_copy_used ?? "-"} />
          <Stat label="Shadow copy allocated" value={recovery.shadow_copy_allocated ?? "-"} />
        </div>
      </Section>

      {/* VIRTUAL MACHINES */}
      {(vm.virtualbox || vm.vmware || vm.hyperv || vm.wsl) && (
        <Section title="Virtual Machines & WSL" subtitle="enterprise storage" collapsible={collapsible}>
          <div className="grid gap-3 md:grid-cols-2">
            {vm.virtualbox && <Stat label="VirtualBox VMs" value={fmtGB(vm.virtualbox.size_gb)} />}
            {vm.vmware && <Stat label="VMware VMs" value={fmtGB(vm.vmware.size_gb)} />}
            {vm.hyperv && <Stat label="Hyper-V" value={fmtGB(vm.hyperv.size_gb)} />}
            {vm.wsl && <Stat label={`WSL distros (${vm.wsl.count})`} value={fmtGB((vm.wsl.distros ?? []).reduce((s: number, d: any) => s + (d.size_gb ?? 0), 0))} />}
          </div>
        </Section>
      )}

      {/* GROWTH + CHANGE TIMELINE */}
      <Section title="Growth & Change Timeline" subtitle={growth.days_until_full != null ? `~${growth.days_until_full} days until full` : "trend"} collapsible={collapsible}>
        <div className="mb-4 grid gap-3 md:grid-cols-3">
          <Stat
            label="Days until disk full"
            value={growth.days_until_full != null ? `${growth.days_until_full}` : "-"}
            tone={growth.days_until_full != null && growth.days_until_full < 30 ? "crit" : "default"}
          />
          <Stat label="Growth rate" value={growth.growth_gb_per_day != null ? `${growth.growth_gb_per_day} GB/day` : "-"} />
          <Stat label="History samples" value={growth.samples ?? 0} />
        </div>
        <Timeline points={report.timeline ?? []} />
        {changes.available && (
          <div className="mt-4 grid gap-4 md:grid-cols-2">
            <div>
              <h4 className="mb-1 text-section-title text-emerald-600">New applications</h4>
              {(changes.new_applications ?? []).length === 0
                ? <p className="text-xs italic text-content-muted">None since last scan.</p>
                : <ul className="space-y-0.5 text-xs text-content-secondary">{changes.new_applications.map((a: string, i: number) => <li key={i}>+ {a}</li>)}</ul>}
            </div>
            <div>
              <h4 className="mb-1 text-section-title text-rose-600">Removed applications</h4>
              {(changes.removed_applications ?? []).length === 0
                ? <p className="text-xs italic text-content-muted">None since last scan.</p>
                : <ul className="space-y-0.5 text-xs text-content-secondary">{changes.removed_applications.map((a: string, i: number) => <li key={i}>- {a}</li>)}</ul>}
            </div>
          </div>
        )}
      </Section>
    </div>
  );
}

