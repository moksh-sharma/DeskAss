import { useState, type ReactNode } from "react";

export function CollapsibleSection({
  title,
  subtitle,
  children,
  defaultOpen = false,
  badge,
  accent = "default",
  className = "",
}: {
  title: string;
  subtitle?: string;
  children: ReactNode;
  defaultOpen?: boolean;
  badge?: ReactNode;
  accent?: "default" | "warning";
  className?: string;
}) {
  const [open, setOpen] = useState(defaultOpen);

  return (
    <div
      className={`card overflow-hidden border border-white/40 shadow-md glass-card transition-all duration-200 hover:border-white/60 ${className}`}
    >
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="relative flex w-full items-center justify-between gap-3 px-5 py-4 text-left transition-colors hover:bg-white/25"
      >
        <div
          className={`absolute left-0 top-0 h-full w-1.5 ${
            accent === "warning" ? "bg-severity-warning/60" : "bg-accent/40"
          }`}
        />
        <div className="min-w-0 flex-1">
          <span className="text-sm font-bold uppercase tracking-tight text-content-primary">{title}</span>
          {subtitle && (
            <span className="ml-3 whitespace-normal break-words text-caption text-content-muted">{subtitle}</span>
          )}
        </div>
        <div className="flex shrink-0 items-center gap-2">
          {badge}
          <span
            className={`text-[10px] font-extrabold text-content-faint transition-transform duration-200 ${
              open ? "rotate-180" : ""
            }`}
          >
            ▼
          </span>
        </div>
      </button>
      {open && <div className="space-y-4 border-t border-white/30 bg-white/10 px-5 py-4">{children}</div>}
    </div>
  );
}
