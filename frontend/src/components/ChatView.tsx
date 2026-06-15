import { useEffect, useRef } from "react";
import { useStore } from "@/store/useStore";
import { MessageBubble } from "@/components/MessageBubble";
import { LoadingAnimation } from "@/components/LoadingAnimation";
import { LenisScroll, type LenisScrollHandle } from "@/components/LenisScroll";

function SparkleIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="1.5">
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09zM18.259 8.715L18 9.75l-.259-1.035a3.375 3.375 0 00-2.455-2.456L14.25 6l1.036-.259a3.375 3.375 0 002.455-2.456L18 2.25l.259 1.035a3.375 3.375 0 002.456 2.456L21.75 6l-1.035.259a3.375 3.375 0 00-2.456 2.456z"
      />
    </svg>
  );
}

export function ChatView() {
  const messages = useStore((s) => s.messages);
  const isDiagnosing = useStore((s) => s.isDiagnosing);
  const bottomRef = useRef<HTMLDivElement>(null);
  const scrollRef = useRef<LenisScrollHandle>(null);

  useEffect(() => {
    if (bottomRef.current) {
      scrollRef.current?.scrollTo(bottomRef.current);
    }
  }, [messages]);

  return (
    <div className="relative h-full min-h-0">
      {messages.length === 0 ? (
        <div className="flex h-full flex-col items-center justify-center px-6 text-center select-none">
          <div className="glass-card max-w-lg p-10">
            <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-2xl bg-accent-shine text-white shadow-glow transition-transform duration-500 hover:scale-105">
              <SparkleIcon className="h-8 w-8" />
            </div>

            <h1 className="mt-6 text-2xl font-extrabold tracking-tight text-content-primary">
              How can I help troubleshoot?
            </h1>

            <p className="mt-3 text-sm leading-relaxed text-content-muted">
              Describe your system issue by text or voice, drop an error screenshot, or run a full scan. I check live
              drivers, event logs, services, and local KB articles before diagnosing.
            </p>

            <div className="mt-8 grid grid-cols-3 gap-3 text-left">
              {[
                { label: "Voice & Text", desc: "English or Hindi" },
                { label: "Screenshot OCR", desc: "Error code capture" },
                { label: "Full Scan", desc: "Hardware + software" },
              ].map((item) => (
                <div
                  key={item.label}
                  className="rounded-xl border border-white/60 bg-white/40 px-3 py-2.5 backdrop-blur-sm"
                >
                  <div className="text-[11px] font-bold text-content-primary">{item.label}</div>
                  <div className="mt-0.5 text-[10px] text-content-muted">{item.desc}</div>
                </div>
              ))}
            </div>
          </div>
        </div>
      ) : (
        <LenisScroll ref={scrollRef} className="h-full" contentClassName="px-6 py-6">
          <div className="mx-auto flex max-w-4xl flex-col gap-6">
            {messages.map((m, i) => {
              if (m.pending && isDiagnosing) return null;
              let userIssue: string | undefined;
              if (m.role === "assistant" && !m.pending) {
                for (let j = i - 1; j >= 0; j--) {
                  if (messages[j].role === "user") {
                    userIssue = messages[j].content;
                    break;
                  }
                }
              }
              return <MessageBubble key={m.id} message={m} userIssue={userIssue} />;
            })}
            <div ref={bottomRef} />
          </div>
        </LenisScroll>
      )}

      <LoadingAnimation active={isDiagnosing} mode="diagnose" />
    </div>
  );
}
