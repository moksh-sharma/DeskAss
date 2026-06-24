import type { ChatMessage } from "@/types";
import { DiagnosisCard } from "@/components/DiagnosisCard";
import { RaiseTicketButton } from "@/components/RaiseTicketButton";
import { formatTime } from "@/lib/format";

function SparkleBotIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
      <path strokeLinecap="round" strokeLinejoin="round" d="M9.663 17h4.673M12 3v1m6.364.364l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
    </svg>
  );
}

function UserAvatarIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
      <path strokeLinecap="round" strokeLinejoin="round" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
    </svg>
  );
}

export function MessageBubble({
  message,
  userIssue,
}: {
  message: ChatMessage;
  userIssue?: string;
}) {
  const isUser = message.role === "user";
  const isSystem = message.role === "system";

  if (isSystem) {
    return (
      <div className="my-3 flex justify-center">
        <div className="rounded-full border border-red-200/70 bg-red-50/70 px-4 py-1 text-[11px] font-bold uppercase tracking-wider text-severity-critical backdrop-blur-md shadow-glass-sm">
          {message.content}
        </div>
      </div>
    );
  }

  return (
    <div className={`group flex w-full items-start gap-3 ${isUser ? "justify-end" : "justify-start"}`}>
      {!isUser && (
        <div className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-accent-shine text-white shadow-glow-sm select-none">
          <SparkleBotIcon className="h-4 w-4" />
        </div>
      )}

      <div className={`flex max-w-[85%] flex-col ${isUser ? "items-end" : "items-start"}`}>
        {message.diagnosis ? (
          <div className="w-full max-w-3xl space-y-3">
            <DiagnosisCard d={message.diagnosis} investigation={message.investigation} />
            {userIssue && !message.pending && (
              <RaiseTicketButton userIssue={userIssue} message={message} />
            )}
          </div>
        ) : (
          <>
            <div
              className={`rounded-2xl px-5 py-3 text-sm leading-relaxed ${
                isUser
                  ? "rounded-tr-md bg-user-bubble font-medium text-white shadow-glow-sm"
                  : message.pending
                    ? "glass-card animate-pulse text-content-muted"
                    : "glass-card rounded-tl-md font-medium text-content-primary"
              }`}
            >
              {message.content}
            </div>
            {!isUser && userIssue && !message.pending && (
              <RaiseTicketButton userIssue={userIssue} message={message} />
            )}
          </>
        )}
        <span className="mt-1.5 px-1.5 text-[9px] font-semibold uppercase tracking-wider text-content-faint select-none">
          {formatTime(message.createdAt)}
        </span>
      </div>

      {isUser && (
        <div className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-xl border border-white/70 bg-white/55 text-content-muted shadow-glass-sm backdrop-blur-md select-none">
          <UserAvatarIcon className="h-4 w-4" />
        </div>
      )}
    </div>
  );
}
