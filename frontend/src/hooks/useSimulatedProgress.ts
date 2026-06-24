import { useEffect, useRef, useState } from "react";

export type LoadingMode = "diagnose" | "scan";

const STAGES: Record<LoadingMode, string[]> = {
  diagnose: [
    "Parsing your issue…",
    "Targeting the affected components…",
    "Running focused live checks…",
    "Probing related drivers & services…",
    "Reviewing recent system events…",
    "Correlating scan evidence…",
    "Building your diagnosis…",
  ],
  scan: [
    "Booting full system scan…",
    "Inventorying CPU & memory…",
    "Running storage analysis…",
    "Mapping drives & largest folders…",
    "Auditing running processes…",
    "Inspecting Windows services…",
    "Parsing event log streams…",
    "Running security probes…",
    "Scoring machine health…",
    "Packaging your report…",
  ],
};

const DURATION: Record<LoadingMode, number> = {
  diagnose: 35_000,
  scan: 120_000,
};

/** Progress eases quickly, then creeps toward 99% while waiting on the backend (never freezes at 94%). */
export function useSimulatedProgress(active: boolean, mode: LoadingMode) {
  const [progress, setProgress] = useState(0);
  const [stageIndex, setStageIndex] = useState(0);
  const [finishing, setFinishing] = useState(false);
  const rafRef = useRef(0);
  const creepRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const startRef = useRef(0);
  const stages = STAGES[mode];

  useEffect(() => {
    if (!active) {
      cancelAnimationFrame(rafRef.current);
      if (creepRef.current) clearInterval(creepRef.current);

      setProgress((p) => {
        if (p > 0) {
          setFinishing(true);
          return 100;
        }
        return 0;
      });

      return;
    }

    setFinishing(false);
    setProgress(0);
    setStageIndex(0);
    startRef.current = performance.now();
    const durationMs = DURATION[mode];

    const tick = (now: number) => {
      const elapsed = now - startRef.current;
      const t = Math.min(1, elapsed / durationMs);
      const eased = 1 - Math.pow(1 - t, 3);
      setProgress(Math.min(88, eased * 88));
      setStageIndex(Math.min(stages.length - 1, Math.floor(eased * stages.length)));
      if (t < 1) rafRef.current = requestAnimationFrame(tick);
    };

    rafRef.current = requestAnimationFrame(tick);

    creepRef.current = setInterval(() => {
      setProgress((p) => {
        if (p >= 99) return p;
        const bump = p < 88 ? 0.4 : p < 94 ? 0.15 : 0.05;
        return Math.min(99, p + bump);
      });
    }, 450);

    return () => {
      cancelAnimationFrame(rafRef.current);
      if (creepRef.current) clearInterval(creepRef.current);
    };
  }, [active, mode, stages.length]);

  useEffect(() => {
    if (!finishing) return;
    const t = setTimeout(() => {
      setFinishing(false);
      setProgress(0);
      setStageIndex(0);
    }, 650);
    return () => clearTimeout(t);
  }, [finishing]);

  return {
    progress: Math.round(progress),
    stage: stages[stageIndex] ?? stages[0],
    finishing,
    show: active || finishing,
  };
}
