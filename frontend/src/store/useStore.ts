import { create } from "zustand";
import { api, type DiagnosePayload } from "@/api/client";
import type {
  ChatMessage,
  MachineScanHistorySummary,
  MachineScanReport,
  SessionSummary,
  SystemDiagnostics,
  SystemStatus,
} from "@/types";

type View = "chat" | "dashboard" | "machine-scan";

interface AppState {
  // Navigation
  view: View;
  setView: (view: View) => void;

  // Service status
  status: SystemStatus | null;
  refreshStatus: () => Promise<void>;

  // Live metrics (dashboard + right panel)
  metrics: SystemDiagnostics | null;
  metricsLoading: boolean;
  refreshMetrics: () => Promise<void>;

  // Sessions
  sessions: SessionSummary[];
  currentSessionId: number | null;
  refreshSessions: () => Promise<void>;
  newSession: () => void;
  loadSession: (id: number) => Promise<void>;
  removeSession: (id: number) => Promise<void>;

  // Chat
  messages: ChatMessage[];
  isDiagnosing: boolean;
  pendingOcrText: string | null;
  setPendingOcrText: (text: string | null) => void;
  sendMessage: (text: string, opts?: Partial<DiagnosePayload>) => Promise<void>;
  resolveIssue: (text: string) => Promise<void>;

  // Comprehensive machine scan (includes troubleshooter findings)
  machineReport: MachineScanReport | null;
  currentMachineScanId: number | null;
  machineScanHistory: MachineScanHistorySummary[];
  isMachineScanning: boolean;
  isGeneratingMachineSummary: boolean;
  runMachineScan: () => Promise<void>;
  generateMachineSummary: () => Promise<void>;
  refreshMachineScanHistory: () => Promise<void>;
  loadMachineScan: (id: number) => Promise<void>;
  removeMachineScan: (id: number) => Promise<void>;

  // Toasts
  toast: { kind: "error" | "info" | "success"; message: string } | null;
  notify: (kind: "error" | "info" | "success", message: string) => void;
  clearToast: () => void;
}

function uid(): string {
  return Math.random().toString(36).slice(2) + Date.now().toString(36);
}

export const useStore = create<AppState>((set, get) => ({
  view: "chat",
  setView: (view) => set({ view }),

  status: null,
  refreshStatus: async () => {
    try {
      set({ status: await api.status() });
    } catch (e) {
      get().notify("error", `Backend unreachable: ${(e as Error).message}`);
    }
  },

  metrics: null,
  metricsLoading: false,
  refreshMetrics: async () => {
    set({ metricsLoading: true });
    try {
      const metrics = await api.diagnostics();
      set({ metrics });
    } catch {
      /* keep last known metrics */
    } finally {
      set({ metricsLoading: false });
    }
  },

  sessions: [],
  currentSessionId: null,
  refreshSessions: async () => {
    try {
      set({ sessions: await api.listSessions() });
    } catch {
      /* ignore */
    }
  },
  newSession: () => set({ currentSessionId: null, messages: [], view: "chat" }),
  loadSession: async (id) => {
    try {
      const detail = await api.getSession(id);
      const messages: ChatMessage[] = detail.messages.map((m) => ({
        id: String(m.id),
        role: m.role,
        content: m.content,
        createdAt: m.created_at,
        diagnosis: m.metadata?.diagnosis?.is_conversational ? undefined : m.metadata?.diagnosis,
        investigation: m.metadata?.diagnosis?.is_conversational ? undefined : m.metadata?.investigation,
      }));
      set({ currentSessionId: id, messages, view: "chat" });
    } catch (e) {
      get().notify("error", (e as Error).message);
    }
  },
  removeSession: async (id) => {
    try {
      await api.deleteSession(id);
      if (get().currentSessionId === id) get().newSession();
      await get().refreshSessions();
    } catch (e) {
      get().notify("error", (e as Error).message);
    }
  },

  messages: [],
  isDiagnosing: false,
  pendingOcrText: null,
  setPendingOcrText: (text) => set({ pendingOcrText: text }),
  sendMessage: async (text, opts) => {
    const trimmed = text.trim();
    if (!trimmed || get().isDiagnosing) return;

    const userMsg: ChatMessage = {
      id: uid(),
      role: "user",
      content: trimmed,
      createdAt: new Date().toISOString(),
    };
    const isLikelyChat = /^(hi|hello|hey|thanks?|thank you|help)\b/i.test(trimmed);
    const pendingMsg: ChatMessage = {
      id: uid(),
      role: "assistant",
      content: isLikelyChat
        ? "One moment…"
        : "Running a full hardware & software scan on your PC, then diagnosing your issue…",
      createdAt: new Date().toISOString(),
      pending: true,
    };
    set({ messages: [...get().messages, userMsg, pendingMsg], isDiagnosing: true });

    const runDiagnose = () =>
      api.diagnose({
        session_id: get().currentSessionId,
        message: trimmed,
        include_diagnostics: true,
        include_event_logs: true,
        ocr_text: get().pendingOcrText,
        ...opts,
      });

    try {
      let resp;
      try {
        resp = await runDiagnose();
      } catch (e) {
        const msg = (e as Error).message ?? "";
        // Retry once when the backend was restarting or briefly unreachable.
        if (msg.includes("Cannot reach backend") || msg === "Failed to fetch") {
          await new Promise((r) => setTimeout(r, 2000));
          resp = await runDiagnose();
        } else {
          throw e;
        }
      }
      const conversational = resp.diagnosis.is_conversational === true;
      const assistantMsg: ChatMessage = {
        id: uid(),
        role: "assistant",
        content: resp.diagnosis.issue_summary || resp.diagnosis.root_cause || "Diagnosis complete.",
        createdAt: new Date().toISOString(),
        diagnosis: conversational ? undefined : resp.diagnosis,
        investigation: conversational ? undefined : resp.investigation ?? undefined,
      };
      const msgs = get().messages.filter((m) => m.id !== pendingMsg.id);
      set({
        messages: [...msgs, assistantMsg],
        currentSessionId: resp.session_id,
        pendingOcrText: null,
        metrics: resp.diagnostics ?? get().metrics,
      });
      await get().refreshSessions();
    } catch (e) {
      const msgs = get().messages.filter((m) => m.id !== pendingMsg.id);
      set({
        messages: [
          ...msgs,
          {
            id: uid(),
            role: "system",
            content: `Diagnosis failed: ${(e as Error).message}`,
            createdAt: new Date().toISOString(),
          },
        ],
      });
      get().notify("error", (e as Error).message);
    } finally {
      set({ isDiagnosing: false });
    }
  },

  resolveIssue: async (text) => {
    // Start a fresh chat session, switch to the assistant view, and diagnose.
    set({ view: "chat", currentSessionId: null, messages: [] });
    await get().sendMessage(text);
  },

  machineReport: null,
  currentMachineScanId: null,
  machineScanHistory: [],
  isMachineScanning: false,
  isGeneratingMachineSummary: false,
  refreshMachineScanHistory: async () => {
    try {
      set({ machineScanHistory: await api.listMachineScans() });
    } catch {
      /* ignore */
    }
  },
  runMachineScan: async () => {
    set({ isMachineScanning: true, view: "machine-scan", currentMachineScanId: null });
    try {
      const machineReport = await api.machineScan();
      set({
        machineReport,
        currentMachineScanId: machineReport.scan_id ?? null,
      });
      await get().refreshMetrics();
      await get().refreshMachineScanHistory();
    } catch (e) {
      get().notify("error", `Full scan failed: ${(e as Error).message}`);
    } finally {
      set({ isMachineScanning: false });
    }
  },
  loadMachineScan: async (id) => {
    try {
      const machineReport = await api.getMachineScan(id);
      set({
        machineReport,
        currentMachineScanId: id,
        view: "machine-scan",
      });
    } catch (e) {
      get().notify("error", (e as Error).message);
    }
  },
  removeMachineScan: async (id) => {
    try {
      await api.deleteMachineScan(id);
      if (get().currentMachineScanId === id) {
        set({ machineReport: null, currentMachineScanId: null });
      }
      await get().refreshMachineScanHistory();
    } catch (e) {
      get().notify("error", (e as Error).message);
    }
  },
  generateMachineSummary: async () => {
    const report = get().machineReport;
    if (!report) return;
    set({ isGeneratingMachineSummary: true });
    try {
      const ai_summary = await api.machineScanSummary(report);
      const scanId = report.scan_id ?? get().currentMachineScanId;
      if (scanId != null) {
        const machineReport = await api.getMachineScan(scanId);
        set({ machineReport, currentMachineScanId: scanId });
      } else {
        set({ machineReport: { ...report, ai_summary } });
      }
      await get().refreshMachineScanHistory();
      get().notify("success", "AI summary ready.");
    } catch (e) {
      get().notify("error", `Summary failed: ${(e as Error).message}`);
    } finally {
      set({ isGeneratingMachineSummary: false });
    }
  },

  toast: null,
  notify: (kind, message) => {
    set({ toast: { kind, message } });
    setTimeout(() => {
      if (get().toast?.message === message) set({ toast: null });
    }, 5000);
  },
  clearToast: () => set({ toast: null }),
}));
