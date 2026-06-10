import { useStore } from "@/store/useStore";

// Beautiful SVG Icons for TopBar Tabs
function ChatBubbleIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2" aria-hidden>
      <path strokeLinecap="round" strokeLinejoin="round" d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
    </svg>
  );
}

function GridIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2" aria-hidden>
      <path strokeLinecap="round" strokeLinejoin="round" d="M4 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2V6zM14 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V6zM4 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2v-2zM14 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2z" />
    </svg>
  );
}

function CpuIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2" aria-hidden>
      <rect x="4" y="4" width="16" height="16" rx="2" />
      <path d="M9 9h6v6H9z" />
      <path d="M9 1v3M15 1v3M9 20v3M15 20v3M20 9h3M20 15h3M1 9h3M1 15h3" />
    </svg>
  );
}

export function TopBar() {
  const view = useStore((s) => s.view);
  const setView = useStore((s) => s.setView);

  const tabs = [
    { id: "chat" as const, label: "AI Assistant", icon: ChatBubbleIcon },
    { id: "dashboard" as const, label: "Dashboard", icon: GridIcon },
    { id: "machine-scan" as const, label: "Full System Scan", icon: CpuIcon },
  ];

  return (
    <header className="flex h-14 shrink-0 items-center border-b border-base-700/60 bg-base-850 px-6 shadow-md backdrop-blur-md bg-opacity-95">
      <nav className="flex gap-2">
        {tabs.map((t) => {
          const Icon = t.icon;
          const active = view === t.id;
          return (
            <button
              key={t.id}
              onClick={() => setView(t.id)}
              className={`flex items-center gap-2 rounded-lg px-4 py-1.5 text-xs font-semibold tracking-wide uppercase transition-all duration-200 ${
                active
                  ? "bg-accent/15 text-accent shadow-inner border border-accent/20"
                  : "text-content-body border border-transparent hover:bg-base-700/50 hover:text-content-primary"
              }`}
            >
              <Icon className={`h-4 w-4 ${active ? "text-accent" : "text-content-muted"}`} />
              {t.label}
            </button>
          );
        })}
      </nav>
    </header>
  );
}
