import { useEffect } from "react";
import { useStore } from "@/store/useStore";
import { Sidebar } from "@/components/Sidebar";
import { IssueScanSidebar } from "@/components/IssueScanSidebar";
import { Toolbar } from "@/components/Toolbar";
import { ChatView } from "@/components/ChatView";
import { Dashboard } from "@/components/Dashboard";
import { MachineScanView } from "@/components/MachineScanView";
import { Toast } from "@/components/Toast";
import { TopBar } from "@/components/TopBar";

export default function App() {
  const view = useStore((s) => s.view);
  const refreshStatus = useStore((s) => s.refreshStatus);
  const refreshSessions = useStore((s) => s.refreshSessions);
  const refreshMachineScanHistory = useStore((s) => s.refreshMachineScanHistory);

  useEffect(() => {
    refreshStatus();
    refreshSessions();
    refreshMachineScanHistory();
  }, [refreshStatus, refreshSessions, refreshMachineScanHistory]);

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-base-900 text-gray-100">
      <Sidebar />

      <div className="flex min-w-0 flex-1 flex-col">
        <TopBar />
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
  );
}
