import { clamp } from "@/lib/format";

function usageColorGradient(percent: number): string {
  if (percent >= 90) return "from-red-500 to-rose-600 shadow-rose-500/20";
  if (percent >= 75) return "from-amber-400 to-orange-500 shadow-orange-400/20";
  return "from-green-400 to-emerald-500 shadow-green-400/20";
}

export function ProgressBar({ value }: { value: number }) {
  const pct = clamp(value);
  return (
    <div className="h-1.5 w-full overflow-hidden rounded-full bg-base-900/60 p-0.5 border border-base-800/10 shadow-inner">
      <div
        className={`h-full rounded-full bg-gradient-to-r ${usageColorGradient(pct)} transition-all duration-500 ease-out shadow-sm`}
        style={{ width: `${pct}%` }}
      />
    </div>
  );
}
