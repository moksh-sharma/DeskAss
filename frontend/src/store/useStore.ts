import { create } from "zustand";
import { api, type DiagnosePayload } from "@/api/client";
import { normalizeDiagnosis } from "@/lib/diagnosis";
import type {
  BootHistory,
  ChatMessage,
  DiagnosisResult,
  IncidentReport,
  InvestigationReport,
  MachineMemory,
  MachineScanHistorySummary,
  MachineScanReport,
  MonitorEvent,
  MonitorPredictions,
  MonitorStatus,
  MonitorTrends,
  SessionSummary,
  StorageReport,
  SystemDiagnostics,
  SystemStatus,
} from "@/types";

/** Extract embedded storage report from a machine scan (deep preferred, merged with quick). */
function storageFromMachineReport(report: MachineScanReport): StorageReport | null {
  const deep = report.software?.storage_deep;
  const quick = report.software?.storage_intelligence;
  const deepOk = deep && !deep.error;
  const quickOk = quick && !quick.error;
  if (!deepOk && !quickOk) return null;

  const merged = {
    ...(quickOk ? quick : {}),
    ...(deepOk ? deep : {}),
    mode: deepOk ? ("deep" as const) : ("quick" as const),
    drives:
      (deepOk && deep.drives?.length ? deep.drives : null) ??
      (quickOk && quick.drives?.length ? quick.drives : null) ??
      [],
    primary_drive:
      (deepOk ? deep.primary_drive : null) ??
      (quickOk ? quick.primary_drive : null) ??
      null,
    cleanup:
      (deepOk && deep.cleanup ? deep.cleanup : null) ??
      (quickOk && quick.cleanup ? quick.cleanup : null) ??
      { quick_wins: [], safe_cleanup: [], advanced_cleanup: [], total_potential_gb: 0 },
    health:
      (deepOk && deep.health ? deep.health : null) ??
      (quickOk && quick.health ? quick.health : null) ??
      { overall_score: 0, overall_status: "Unknown", categories: {}, notes: [] },
    scan_duration_seconds:
      (deepOk ? deep.scan_duration_seconds : null) ??
      (quickOk ? quick.scan_duration_seconds : null) ??
      0,
  };

  return merged as StorageReport;
}

function storageNeedsDedicatedScan(report: StorageReport | null): boolean {
  if (!report) return true;
  // Full system scan should always include deep storage (largest files/folders, duplicates).
  if (report.mode !== "deep") return true;
  const tree = report.tree ?? {};
  const hasTree =
    (tree.top_files?.length ?? 0) > 0 ||
    (tree.top_folders?.length ?? 0) > 0 ||
    (tree.total_files_scanned ?? 0) > 0;
  const hasDrives = (report.drives?.length ?? 0) > 0;
  return !hasDrives || !hasTree;
}

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
  raiseTicket: (userIssue: string, message: ChatMessage) => Promise<void>;
  resolveIssue: (text: string) => Promise<void>;

  // Comprehensive machine scan (includes troubleshooter findings)
  machineReport: MachineScanReport | null;
  currentMachineScanId: number | null;
  machineScanHistory: MachineScanHistorySummary[];
  isMachineScanning: boolean;
  runMachineScan: () => Promise<void>;
  refreshMachineScanHistory: () => Promise<void>;
  loadMachineScan: (id: number) => Promise<void>;
  removeMachineScan: (id: number) => Promise<void>;

  // Storage analysis (runs with full system scan; shown on machine-scan page only)
  storageReport: StorageReport | null;

  // Continuous monitoring (System Dashboard)
  monitorStatus: MonitorStatus | null;
  monitorTrends: MonitorTrends | null;
  monitorAlerts: MonitorEvent[];
  monitorChanges: MonitorEvent[];
  monitorPredictions: MonitorPredictions | null;
  monitorMemory: MachineMemory | null;
  monitorBoot: BootHistory | null;
  incidentResult: IncidentReport | null;
  isReconstructing: boolean;
  refreshMonitoring: () => Promise<void>;
  reconstructIncident: (text: string, windowMinutes?: number) => Promise<void>;

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
      const messages: ChatMessage[] = detail.messages.map((m) => {
        const rawDiagnosis = m.metadata?.diagnosis;
        const investigation = m.metadata?.investigation as InvestigationReport | undefined;
        const conversational = rawDiagnosis?.is_conversational === true;
        let diagnosis: DiagnosisResult | undefined;
        if (rawDiagnosis && !conversational) {
          diagnosis = normalizeDiagnosis(rawDiagnosis, investigation);
        }
        return {
          id: String(m.id),
          role: m.role,
          content: m.content,
          createdAt: m.created_at,
          diagnosis,
          investigation: conversational ? undefined : investigation,
        };
      });
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
        : "Running live checks on your PC, then diagnosing your issue…",
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
      const investigation = conversational ? undefined : resp.investigation ?? undefined;
      const diagnosis = conversational
        ? undefined
        : normalizeDiagnosis(resp.diagnosis, investigation);
      const assistantMsg: ChatMessage = {
        id: uid(),
        role: "assistant",
        content: diagnosis?.issue_summary || resp.diagnosis.issue_summary || resp.diagnosis.root_cause || "Diagnosis complete.",
        createdAt: new Date().toISOString(),
        diagnosis,
        investigation,
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

  raiseTicket: async (userIssue, message) => {
    const trimmed = userIssue.trim();
    if (!trimmed) {
      get().notify("error", "No user issue found for this message.");
      return;
    }
    try {
      await api.raiseTicket({
        session_id: get().currentSessionId,
        user_issue: trimmed,
        diagnosis: message.diagnosis,
        assistant_reply: message.diagnosis ? undefined : message.content,
      });
      get().notify("success", "Support ticket sent. IT will follow up by email.");
    } catch (e) {
      get().notify("error", (e as Error).message);
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
  refreshMachineScanHistory: async () => {
    try {
      set({ machineScanHistory: await api.listMachineScans() });
    } catch {
      /* ignore */
    }
  },
  runMachineScan: async () => {
    set({ isMachineScanning: true, view: "machine-scan", currentMachineScanId: null, storageReport: null, machineReport: null });
    try {
      const machineReport = await api.machineScan();
      let storageReport = storageFromMachineReport(machineReport);
      if (storageNeedsDedicatedScan(storageReport)) {
        try {
          storageReport = await api.storageScan();
        } catch (e) {
          if (!storageReport) {
            throw e;
          }
          get().notify(
            "error",
            `Storage deep analysis incomplete: ${(e as Error)?.message ?? "unknown error"}`,
          );
        }
      }
      set({
        machineReport,
        storageReport,
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
        storageReport: storageFromMachineReport(machineReport),
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

  storageReport: null,

  monitorStatus: null,
  monitorTrends: null,
  monitorAlerts: [],
  monitorChanges: [],
  monitorPredictions: null,
  monitorMemory: null,
  monitorBoot: null,
  incidentResult: null,
  isReconstructing: false,
  refreshMonitoring: async () => {
    try {
      const [status, trends, alerts, changes, predictions, memory, boot] = await Promise.all([
        api.monitorStatus(),
        api.monitorTrends(7),
        api.monitorAlerts(72),
        api.monitorChanges(30),
        api.monitorPredictions(),
        api.monitorMachineMemory(),
        api.monitorBootHistory(),
      ]);
      set({
        monitorStatus: status,
        monitorTrends: trends,
        monitorAlerts: alerts,
        monitorChanges: changes,
        monitorPredictions: predictions,
        monitorMemory: memory,
        monitorBoot: boot,
      });
    } catch {
      /* keep last known monitoring data */
    }
  },
  reconstructIncident: async (text, windowMinutes = 30) => {
    set({ isReconstructing: true });
    try {
      const incidentResult = await api.monitorIncident(text, windowMinutes);
      set({ incidentResult });
    } catch (e) {
      get().notify("error", `Incident analysis failed: ${(e as Error).message}`);
    } finally {
      set({ isReconstructing: false });
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
