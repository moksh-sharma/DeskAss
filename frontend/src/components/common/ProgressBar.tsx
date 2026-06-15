import { clamp } from "@/lib/format";

function usageColorGradient(percent: number): string {
  if (percent >= 90) return "from-red-400 to-rose-500 shadow-rose-400/25";
  if (percent >= 75) return "from-amber-400 to-orange-400 shadow-orange-400/20";
  return "from-emerald-400 to-teal-400 shadow-emerald-400/20";
}

export function ProgressBar({ value }: { value: number }) {
  const pct = clamp(value);
  return (
    <div className="h-2 w-full overflow-hidden rounded-full border border-white/50 bg-white/40 p-px shadow-inner backdrop-blur-sm">
      <div
        className={`h-full rounded-full bg-gradient-to-r ${usageColorGradient(pct)} transition-all duration-500 ease-out shadow-sm`}
        style={{ width: `${pct}%` }}
      />
    </div>
  );
}
