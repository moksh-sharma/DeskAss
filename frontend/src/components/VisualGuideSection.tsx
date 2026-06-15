import type { VisualGuide } from "@/types";

/** Text-only guide steps (screenshots removed). */
export function VisualGuideSection({ guide }: { guide: VisualGuide }) {
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-white/55 bg-white/40 px-4 py-3 backdrop-blur-sm">
        <div>
          <p className="text-sm font-bold text-content-primary">{guide.title}</p>
          {guide.section_title && (
            <p className="mt-0.5 text-xs text-content-muted">{guide.section_title}</p>
          )}
        </div>
        <a
          href={guide.source_url}
          target="_blank"
          rel="noopener noreferrer"
          className="text-[11px] font-semibold text-accent hover:underline"
        >
          {guide.attribution} ↗
        </a>
      </div>

      <p className="text-xs text-content-muted">
        Follow these steps in order — each one is short and easy to try.
      </p>

      <ol className="space-y-3">
        {guide.steps.map((step) => (
          <li
            key={step.step}
            className="flex gap-3 rounded-xl border border-white/50 bg-white/35 p-4 backdrop-blur-sm"
          >
            <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-lg bg-accent-shine text-[11px] font-black text-white shadow-glow-sm">
              {step.step}
            </span>
            <p className="pt-0.5 text-sm font-medium leading-relaxed text-content-secondary">{step.text}</p>
          </li>
        ))}
      </ol>
    </div>
  );
}
