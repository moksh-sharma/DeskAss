import { useEffect, useState } from "react";

const MIN_DISPLAY_MS = 3200;
const FADE_OUT_MS = 700;

export function SplashScreen({ onComplete }: { onComplete: () => void }) {
  const [phase, setPhase] = useState(0);
  const [exiting, setExiting] = useState(false);

  useEffect(() => {
    const t1 = setTimeout(() => setPhase(1), 400);
    const t2 = setTimeout(() => setPhase(2), 900);
    const t3 = setTimeout(() => setPhase(3), 1400);
    const t4 = setTimeout(() => setExiting(true), MIN_DISPLAY_MS);
    const t5 = setTimeout(() => onComplete(), MIN_DISPLAY_MS + FADE_OUT_MS);
    return () => {
      clearTimeout(t1);
      clearTimeout(t2);
      clearTimeout(t3);
      clearTimeout(t4);
      clearTimeout(t5);
    };
  }, [onComplete]);

  return (
    <div
      className={`splash-screen fixed inset-0 z-[200] flex items-center justify-center overflow-hidden transition-opacity duration-700 ${
        exiting ? "pointer-events-none opacity-0" : "opacity-100"
      }`}
      role="status"
      aria-label="Loading Desktop Assistant"
    >
      <div className="moving-gradient-bg absolute inset-0" />

      <div className="splash-grid absolute inset-0 opacity-[0.04]" />

      <div
        className={`relative flex flex-col items-center px-8 text-center transition-all duration-700 ${
          exiting ? "scale-95 opacity-0" : "scale-100 opacity-100"
        }`}
      >
        {/* Logo ring */}
        <div className={`splash-logo-wrap ${phase >= 1 ? "splash-logo-wrap--active" : ""}`}>
          <div className="splash-ring splash-ring-outer" />
          <div className="splash-ring splash-ring-inner" />
          <div className="splash-logo-core">
            <svg className="h-10 w-10 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="1.5">
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09z"
              />
            </svg>
          </div>
          {[0, 1, 2, 3].map((i) => (
            <span key={i} className="splash-orbit-dot" style={{ animationDelay: `${i * 0.5}s` }} />
          ))}
        </div>

        {/* Title */}
        <h1
          className={`splash-title mt-10 text-3xl font-extrabold tracking-tight text-content-primary sm:text-4xl ${
            phase >= 2 ? "splash-title--visible" : ""
          }`}
        >
          Desktop Assistant
        </h1>

        {/* Powered by + logo - single centered row below title */}
        <div
          className={`splash-powered mt-3 flex flex-row items-center justify-center gap-2.5 ${
            phase >= 3 ? "splash-powered--visible" : ""
          }`}
        >
          <span className="text-[9px] font-bold uppercase tracking-[0.28em] text-content-muted whitespace-nowrap">
            Powered by
          </span>
          <div className={`splash-brand-logo ${phase >= 3 ? "splash-brand-logo--visible" : "opacity-0"}`}>
            <img
              src="/branding/cache-digitech-logo.png"
              alt="Cache Digitech"
              className="h-5 w-auto object-contain"
              draggable={false}
            />
          </div>
        </div>

        {/* Loading bar */}
        <div className={`splash-bar-track mt-10 ${phase >= 1 ? "splash-bar-track--visible" : ""}`}>
          <div className="splash-bar-fill" />
        </div>

        <p className={`splash-status mt-4 text-xs text-content-faint ${phase >= 2 ? "opacity-100" : "opacity-0"} transition-opacity duration-500`}>
          Initializing workspace…
        </p>
      </div>
    </div>
  );
}
