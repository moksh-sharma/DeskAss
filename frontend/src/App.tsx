import { useCallback, useEffect, useState } from "react";
import { useStore } from "@/store/useStore";
import { AppBackground } from "@/components/AppBackground";
import { Sidebar } from "@/components/Sidebar";
import { IssueScanSidebar } from "@/components/IssueScanSidebar";
import { Toolbar } from "@/components/Toolbar";
import { ChatView } from "@/components/ChatView";
import { Dashboard } from "@/components/Dashboard";
import { MachineScanView } from "@/components/MachineScanView";
import { Toast } from "@/components/Toast";
import { SplashScreen } from "@/components/SplashScreen";

export default function App() {
  const [splashDone, setSplashDone] = useState(false);
  const handleSplashComplete = useCallback(() => setSplashDone(true), []);

  const view = useStore((s) => s.view);
  const refreshStatus = useStore((s) => s.refreshStatus);
  const refreshSessions = useStore((s) => s.refreshSessions);
  const refreshMachineScanHistory = useStore((s) => s.refreshMachineScanHistory);

  useEffect(() => {
    if (!splashDone) return;
    refreshStatus();
    refreshSessions();
    refreshMachineScanHistory();
  }, [splashDone, refreshStatus, refreshSessions, refreshMachineScanHistory]);

  return (
    <>
      {!splashDone && <SplashScreen onComplete={handleSplashComplete} />}

      <div
        className={`relative flex h-screen w-screen overflow-hidden text-content-body transition-opacity duration-500 ${
          splashDone ? "opacity-100" : "opacity-0"
        }`}
      >
        <AppBackground />

        <Sidebar />

        <div className="flex min-w-0 flex-1 flex-col">
          <main className="flex min-h-0 flex-1 flex-col">
            {view === "chat" && (
              <>
                <div className="min-h-0 flex-1">
                  <ChatView />
                </div>
                <Toolbar />
              </>
            )}
            {view === "dashboard" && <Dashboard />}
            {view === "machine-scan" && <MachineScanView />}
          </main>
        </div>

        <IssueScanSidebar />

        <Toast />
      </div>
    </>
  );
}
