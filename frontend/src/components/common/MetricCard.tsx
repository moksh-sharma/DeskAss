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
    <div className="card p-5 hover:border-base-600 hover:-translate-y-px transition-all duration-200 bg-base-850 shadow-md">
      <div className="flex items-center justify-between">
        <span className="text-label">{label}</span>
        {icon}
      </div>
      <div className="mt-2 text-2xl font-black text-white tracking-tight">{value}</div>
      {percent !== undefined && (
        <div className="mt-4">
          <ProgressBar value={percent} />
        </div>
      )}
      {sub && <div className="mt-3.5 text-caption text-content-muted">{sub}</div>}
    </div>
  );
}
