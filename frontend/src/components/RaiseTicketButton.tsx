import { useState } from "react";
import type { ChatMessage } from "@/types";
import { useStore } from "@/store/useStore";

function TicketIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M15 5v2m0 4v2m0 4v2M5 5a2 2 0 00-2 2v3a2 2 0 110 4v3a2 2 0 002 2h14a2 2 0 002-2v-3a2 2 0 110-4V7a2 2 0 00-2-2H5z"
      />
    </svg>
  );
}

export function RaiseTicketButton({
  userIssue,
  message,
}: {
  userIssue: string;
  message: ChatMessage;
}) {
  const raiseTicket = useStore((s) => s.raiseTicket);
  const [loading, setLoading] = useState(false);

  const handleClick = async () => {
    if (loading) return;
    setLoading(true);
    try {
      await raiseTicket(userIssue, message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <button
      type="button"
      onClick={handleClick}
      disabled={loading}
      className="mt-2 inline-flex items-center gap-1.5 rounded-lg border border-base-700/50 bg-base-900/40 px-3 py-1.5 text-[11px] font-bold uppercase tracking-wider text-content-secondary transition-all hover:border-accent/40 hover:bg-accent/10 hover:text-accent disabled:cursor-not-allowed disabled:opacity-50"
    >
      <TicketIcon className="h-3.5 w-3.5" />
      {loading ? "Sending…" : "Raise a ticket"}
    </button>
  );
}
