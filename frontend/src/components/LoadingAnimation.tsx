import { useId } from "react";
import { useSimulatedProgress, type LoadingMode } from "@/hooks/useSimulatedProgress";

function Orb({ delay, radius, size, color }: { delay: number; radius: number; size: number; color: string }) {
  return (
    <div
      className="absolute left-1/2 top-1/2"
      style={{
        width: radius * 2,
        height: radius * 2,
        marginLeft: -radius,
        marginTop: -radius,
        animation: `load-orbit ${4 + delay}s linear infinite`,
        animationDelay: `${delay}s`,
      }}
    >
      <div
        className="rounded-full"
        style={{
          width: size,
          height: size,
          background: color,
          boxShadow: `0 0 ${size * 2}px ${color}`,
          animation: `load-pulse-glow ${1.2 + delay * 0.3}s ease-in-out infinite alternate`,
          animationDelay: `${delay}s`,
        }}
      />
    </div>
  );
}

function ProgressRing({ progress, gradId, glowId }: { progress: number; gradId: string; glowId: string }) {
  const r = 68;
  const circ = 2 * Math.PI * r;
  const offset = circ * (1 - progress / 100);

  return (
    <svg className="h-40 w-40 -rotate-90" viewBox="0 0 160 160">
      <defs>
        <linearGradient id={gradId} x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="#6366f1" />
          <stop offset="50%" stopColor="#818cf8" />
          <stop offset="100%" stopColor="#a5b4fc" />
        </linearGradient>
        <filter id={glowId}>
          <feGaussianBlur stdDeviation="2" result="blur" />
          <feMerge>
            <feMergeNode in="blur" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
      </defs>
      <circle cx="80" cy="80" r={r} fill="none" stroke="rgba(255,255,255,0.4)" strokeWidth="5" />
      <circle
        cx="80"
        cy="80"
        r={r}
        fill="none"
        stroke={`url(#${gradId})`}
        strokeWidth="5"
        strokeLinecap="round"
        strokeDasharray={circ}
        strokeDashoffset={offset}
        filter={`url(#${glowId})`}
        className="transition-[stroke-dashoffset] duration-300 ease-out"
      />
    </svg>
  );
}

const MODE_LABEL: Record<LoadingMode, string> = {
  diagnose: "AI Diagnosis",
  scan: "Full System Scan",
  summary: "AI Summary",
};

const MODE_HINT: Record<LoadingMode, string> = {
  diagnose: "Live probes + AI reasoning in progress…",
  scan: "Deep-scanning every subsystem — hang tight.",
  summary: "Synthesizing insights from your scan…",
};

/** In-panel loading animation — place inside a `relative h-full` container. */
export function LoadingAnimation({ active, mode }: { active: boolean; mode: LoadingMode }) {
  const uid = useId();
  const gradId = `loadGrad${uid.replace(/:/g, "")}`;
  const glowId = `loadGlow${uid.replace(/:/g, "")}`;
  const { progress, stage, finishing, show } = useSimulatedProgress(active, mode);

  if (!show) return null;

  return (
    <div
      className={`absolute inset-0 z-10 flex items-center justify-center overflow-hidden transition-opacity duration-500 ${
        finishing && !active ? "pointer-events-none opacity-0" : "opacity-100"
      }`}
      role="status"
      aria-live="polite"
      aria-label={`${MODE_LABEL[mode]} in progress, ${progress} percent`}
    >
      <div className="moving-gradient-bg absolute inset-0 opacity-90 backdrop-blur-sm" />

      <div className="pointer-events-none absolute inset-0 opacity-[0.05]">
        <div className="load-scan-lines h-full w-full" />
      </div>

      <div className="glass-card relative mx-4 w-full max-w-sm overflow-hidden p-8 text-center shadow-glass-lg">
        <div className="pointer-events-none absolute inset-0 load-shimmer-sweep bg-gradient-to-r from-transparent via-white/45 to-transparent" />

        <p className="text-label text-accent">{MODE_LABEL[mode]}</p>

        <div className="relative mx-auto my-5 h-40 w-40">
          <Orb delay={0} radius={76} size={8} color="#6366f1" />
          <Orb delay={0.8} radius={58} size={6} color="#818cf8" />
          <Orb delay={1.6} radius={40} size={5} color="#a5b4fc" />
          <Orb delay={2.4} radius={24} size={4} color="#c7d2fe" />

          <div className="absolute inset-0 flex items-center justify-center">
            <ProgressRing progress={progress} gradId={gradId} glowId={glowId} />
          </div>

          <div className="absolute inset-0 flex items-center justify-center">
            <span className="load-number-pop font-mono text-4xl font-black tabular-nums tracking-tighter text-content-primary">
              {progress}
              <span className="text-xl text-accent">%</span>
            </span>
          </div>
        </div>

        <p className="load-stage-fade min-h-[1.25rem] text-sm font-semibold text-content-secondary" key={stage}>
          {stage}
        </p>

        <div className="mx-auto mt-4 h-1.5 max-w-[220px] overflow-hidden rounded-full border border-white/60 bg-white/40">
          <div
            className="h-full rounded-full bg-gradient-to-r from-indigo-500 via-indigo-400 to-indigo-300 transition-all duration-300 ease-out"
            style={{ width: `${progress}%` }}
          />
        </div>

        <p className="mt-3 text-[11px] text-content-faint">{MODE_HINT[mode]}</p>
      </div>
    </div>
  );
}
