import type { ChatMessage } from "@/types";
import { DiagnosisCard } from "@/components/DiagnosisCard";
import { InvestigationPanel } from "@/components/InvestigationPanel";
import { RaiseTicketButton } from "@/components/RaiseTicketButton";
import { formatTime } from "@/lib/format";

// Icons for Avatars
function SparkleBotIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2.5">
      <path strokeLinecap="round" strokeLinejoin="round" d="M9.663 17h4.673M12 3v1m6.364.364l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
    </svg>
  );
}

function UserAvatarIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2.5">
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
        <div className="rounded-full border border-severity-critical/20 bg-severity-critical/5 px-4 py-1 text-[11px] font-bold uppercase tracking-wider text-severity-critical shadow-sm">
          {message.content}
        </div>
      </div>
    );
  }

  return (
    <div className={`flex w-full gap-3 ${isUser ? "justify-end" : "justify-start"} items-start group`}>
      {/* Assistant Avatar */}
      {!isUser && (
        <div className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-gradient-to-tr from-accent to-blue-400 text-white shadow-md shadow-accent/10 select-none">
          <SparkleBotIcon className="h-4.5 w-4.5 text-white" />
        </div>
      )}

      {/* Message Body Container */}
      <div className={`flex max-w-[85%] flex-col ${isUser ? "items-end" : "items-start"}`}>
        {message.diagnosis ? (
          <div className="space-y-3 w-full">
            <DiagnosisCard d={message.diagnosis} />
            {message.investigation && <InvestigationPanel report={message.investigation} />}
            {userIssue && !message.pending && (
              <RaiseTicketButton userIssue={userIssue} message={message} />
            )}
          </div>
        ) : (
          <>
            <div
              className={`rounded-2xl px-5 py-3 text-sm leading-relaxed shadow-md ${isUser
                  ? "bg-gradient-to-br from-accent to-accent-hover text-white rounded-tr-none font-medium"
                  : message.pending
                    ? "animate-pulse bg-base-850 text-content-muted border border-base-700/30"
                    : "bg-base-850 text-content-primary border border-base-700/40 rounded-tl-none font-medium"
                }`}
            >
              {message.content}
            </div>
            {!isUser && userIssue && !message.pending && (
              <RaiseTicketButton userIssue={userIssue} message={message} />
            )}
          </>
        )}
        <span className="mt-1 px-1.5 text-[9px] font-bold text-content-muted uppercase tracking-wider select-none">
          {formatTime(message.createdAt)}
        </span>
      </div>

      {/* User Avatar */}
      {isUser && (
        <div className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-base-800 text-gray-300 border border-base-700/50 shadow-sm select-none">
          <UserAvatarIcon className="h-4.5 w-4.5 text-gray-400" />
        </div>
      )}
    </div>
  );
}
