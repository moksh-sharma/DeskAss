import { apiAssetUrl } from "@/api/client";
import type { VisualGuide } from "@/types";

export function VisualGuideSection({ guide }: { guide: VisualGuide }) {
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-base-700/30 bg-base-900/20 px-4 py-3">
        <div>
          <p className="text-sm font-bold text-white">{guide.title}</p>
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

      <ol className="space-y-5">
        {guide.steps.map((step) => (
          <li
            key={step.step}
            className="overflow-hidden rounded-xl border border-base-700/25 bg-base-900/15"
          >
            <div className="flex gap-3 p-4">
              <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-lg bg-gradient-to-tr from-accent to-blue-400 text-[11px] font-black text-white shadow-md shadow-accent/10">
                {step.step}
              </span>
              <p className="pt-0.5 text-sm font-medium leading-relaxed text-gray-100">{step.text}</p>
            </div>

            {step.image_url && (
              <figure className="border-t border-base-700/20 bg-base-950/40 px-4 pb-4 pt-3">
                <img
                  src={apiAssetUrl(step.image_url)}
                  alt={step.caption || `Step ${step.step} screenshot`}
                  className="mx-auto max-h-80 w-full max-w-xl rounded-lg border border-base-700/40 object-contain shadow-lg"
                  loading="lazy"
                />
                {step.caption && (
                  <figcaption className="mt-2 text-center text-xs text-content-muted">
                    {step.caption}
                  </figcaption>
                )}
              </figure>
            )}
          </li>
        ))}
      </ol>
    </div>
  );
}
