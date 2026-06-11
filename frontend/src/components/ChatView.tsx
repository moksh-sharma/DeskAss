import { useEffect, useRef } from "react";
import { useStore } from "@/store/useStore";
import { MessageBubble } from "@/components/MessageBubble";
import { LenisScroll, type LenisScrollHandle } from "@/components/LenisScroll";

export function ChatView() {
  const messages = useStore((s) => s.messages);
  const bottomRef = useRef<HTMLDivElement>(null);
  const scrollRef = useRef<LenisScrollHandle>(null);

  useEffect(() => {
    if (bottomRef.current) {
      scrollRef.current?.scrollTo(bottomRef.current);
    }
  }, [messages]);

  if (messages.length === 0) {
    return (
      <div className="flex h-full flex-col items-center justify-center px-6 text-center select-none bg-base-900 bg-opacity-10">
        {/* Glow effect backdrops */}
        <div className="absolute top-1/3 left-1/2 -translate-x-1/2 -translate-y-1/2 h-72 w-72 rounded-full bg-accent/5 blur-[120px] pointer-events-none" />
        
        <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-gradient-to-tr from-accent to-blue-400 text-3xl font-black text-white shadow-2xl shadow-accent/20 transition-transform hover:scale-105 duration-300">
          C
        </div>
        
        <h1 className="mt-6 text-2xl font-black tracking-tight text-content-primary uppercase">
          How can I help troubleshoot?
        </h1>
        
        <p className="mt-2 max-w-lg text-caption text-content-body">
          Describe your system issue by text or voice, drop an error screenshot, or run a full scan.
          I check live drivers, event logs, services, and local KB articles before diagnosing.
        </p>
      </div>
    );
  }

  return (
    <LenisScroll
      ref={scrollRef}
      className="h-full bg-base-900 bg-opacity-20"
      contentClassName="px-6 py-6"
    >
      <div className="mx-auto flex max-w-4xl flex-col gap-6">
        {messages.map((m, i) => {
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
  );
}
