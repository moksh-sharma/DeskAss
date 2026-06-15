import type { ReactNode } from "react";
import { ProgressBar } from "./ProgressBar";

interface MetricCardProps {
  label: string;
  value: string;
  percent?: number;
  sub?: string;
  icon?: ReactNode;
}

export function MetricCard({ label, value, percent, sub, icon }: MetricCardProps) {
  return (
    <div className="glass-card p-5 transition-all duration-300 hover:-translate-y-0.5 hover:shadow-glass">
      <div className="flex items-center justify-between">
        <span className="text-label">{label}</span>
        {icon}
      </div>
      <div className="mt-2 text-2xl font-extrabold tracking-tight text-content-primary">{value}</div>
      {percent !== undefined && (
        <div className="mt-4">
          <ProgressBar value={percent} />
        </div>
      )}
      {sub && <div className="mt-3.5 text-caption text-content-muted">{sub}</div>}
    </div>
  );
}
