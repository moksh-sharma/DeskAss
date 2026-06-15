import type {
  DiagnoseResponse,
  DiagnosisResult,
  BootHistory,
  EventLogSummary,
  HealthReport,
  IncidentReport,
  MachineAiSummary,
  MachineMemory,
  MachineScanHistorySummary,
  MachineScanReport,
  MonitorEvent,
  MonitorPredictions,
  MonitorReport,
  MonitorStatus,
  MonitorTrends,
  OcrResponse,
  SessionDetail,
  SessionSummary,
  StorageHistorySummary,
  StorageReport,
  SystemDiagnostics,
  SystemStatus,
  TranscriptionResponse,
} from "@/types";

/** Resolve API base: explicit env, dev proxy (same origin), or local backend default. */
function resolveApiBase(): string {
  const configured = (import.meta.env.VITE_API_BASE_URL as string | undefined)?.trim();
  if (configured) return configured.replace(/\/$/, "");
  if (import.meta.env.DEV && typeof window !== "undefined" && window.location.protocol.startsWith("http")) {
    return window.location.origin;
  }
  return "http://127.0.0.1:8003";
}

const BASE_URL = resolveApiBase();

/** Resolve a backend-relative asset path (e.g. `/api/visual-guides/...`). */
export function apiAssetUrl(path: string): string {
  if (path.startsWith("http://") || path.startsWith("https://")) return path;
  return `${BASE_URL}${path.startsWith("/") ? path : `/${path}`}`;
}

/** WebSocket URL for live voice transcription (proxied in Vite dev). */
export type VoiceLanguage = "multi" | "en" | "hi";

export function voiceStreamUrl(language: VoiceLanguage = "multi"): string {
  const url = new URL("/api/voice/stream", BASE_URL);
  url.searchParams.set("language", language);
  url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
  return url.href;
}

/** Diagnosis can take several minutes (diagnostics + event logs + remote Ollama). */
/** Full machine scan (~1 min) + remote Ollama diagnosis. */
const DIAGNOSE_TIMEOUT_MS = 480_000;
/** Scan summary uses a faster model but remote Ollama can still take a few minutes. */
const SUMMARY_TIMEOUT_MS = 480_000;

class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

function timeoutError(label: string, timeoutMs: number): Error {
  const mins = Math.round(timeoutMs / 60_000);
  return new Error(
    `${label} timed out (waited over ${mins} minutes). The AI server may still be processing - try again in a moment.`,
  );
}

function networkError(cause: unknown, label = "Request", timeoutMs = 30_000): Error {
  const detail = cause instanceof Error ? cause.message : String(cause);
  if (detail.includes("abort")) {
    return timeoutError(label, timeoutMs);
  }
  return new Error(
    `Cannot reach backend at ${BASE_URL}. Start it with: cd backend && .\\run.ps1 (${detail})`,
  );
}

async function fetchWithTimeout(
  url: string,
  init: RequestInit,
  timeoutMs: number,
  label = "Request",
): Promise<Response> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(url, { ...init, signal: controller.signal });
  } catch (e) {
    throw networkError(e, label, timeoutMs);
  } finally {
    clearTimeout(timer);
  }
}

async function request<T>(
  path: string,
  init?: RequestInit,
  timeoutMs = 30_000,
  label = "Request",
): Promise<T> {
  let resp: Response;
  try {
    resp = await fetchWithTimeout(
      `${BASE_URL}${path}`,
      {
        headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
        ...init,
      },
      timeoutMs,
      label,
    );
  } catch (e) {
    throw e instanceof Error ? e : networkError(e, label, timeoutMs);
  }
  if (!resp.ok) {
    let message = `Request failed (${resp.status})`;
    try {
      const body = await resp.json();
      message = body?.error?.message ?? message;
    } catch {
      /* ignore */
    }
    throw new ApiError(message, resp.status);
  }
  return (await resp.json()) as T;
}

export interface DiagnosePayload {
  session_id?: number | null;
  message: string;
  include_diagnostics?: boolean;
  include_event_logs?: boolean;
  ocr_text?: string | null;
}

export interface RaiseTicketPayload {
  session_id?: number | null;
  user_issue: string;
  diagnosis?: DiagnosisResult;
  assistant_reply?: string;
}

export interface RaiseTicketResponse {
  sent: boolean;
  message: string;
}

/** Strip bulky lists before sending a scan to the summary endpoint. */
function slimScanForSummary(report: MachineScanReport) {
  const hw = report.hardware ?? {};
  const sw = report.software ?? {};
  return {
    scan_id: report.scan_id ?? null,
    generated_at: report.generated_at,
    scan_duration_seconds: report.scan_duration_seconds,
    health_report: report.health_report,
    hardware: {
      cpu: hw.cpu,
      ram: hw.ram,
      performance: hw.performance,
      storage: hw.storage,
      disk_health: hw.disk_health,
      devices: {
        total_count: hw.devices?.total_count,
        problem_count: hw.devices?.problem_count,
        problem_devices: hw.devices?.problem_devices,
      },
    },
    software: {
      operating_system: sw.operating_system,
      installed_count: sw.installed_count,
      running_processes: {
        top_cpu: sw.running_processes?.top_cpu?.slice(0, 8),
      },
      services: {
        failed_critical: sw.services?.failed_critical,
      },
      startup_programs: {
        high_impact_count: sw.startup_programs?.high_impact_count,
      },
      security: sw.security,
      network: sw.network,
      crash_analysis: sw.crash_analysis,
      event_logs: { summary: sw.event_logs?.summary },
      storage_intelligence: sw.storage_intelligence
        ? {
            health: sw.storage_intelligence.health,
            recoverable_gb: sw.storage_intelligence.cleanup?.total_potential_gb,
            quick_wins: sw.storage_intelligence.cleanup?.quick_wins?.slice(0, 4),
          }
        : undefined,
    },
  };
}

export const api = {
  baseUrl: BASE_URL,

  status: () => request<SystemStatus>("/api/status"),

  diagnostics: () => request<SystemDiagnostics>("/api/diagnostics"),

  eventLogs: () => request<EventLogSummary>("/api/diagnostics/event-logs"),

  fullScan: () => request<HealthReport>("/api/diagnostics/scan", { method: "POST" }),

  /** Comprehensive machine scan - hardware + software + deep storage (parallel). */
  machineScan: () =>
    request<MachineScanReport>("/api/diagnostics/full-scan", { method: "POST" }, 480_000),

  listMachineScans: () => request<MachineScanHistorySummary[]>("/api/machine-scans"),

  /** Advanced Storage Intelligence — deep scan (heavy; up to several minutes). */
  storageScan: () =>
    request<StorageReport>("/api/storage/scan", { method: "POST" }, 720_000, "Storage scan"),

  listStorageScans: () => request<StorageHistorySummary[]>("/api/storage"),

  getStorageScan: (id: number) => request<StorageReport>(`/api/storage/${id}`),

  deleteStorageScan: (id: number) =>
    request<{ deleted: boolean }>(`/api/storage/${id}`, { method: "DELETE" }),

  // ----- Continuous monitoring ----------------------------------------- //
  monitorStatus: () => request<MonitorStatus>("/api/monitoring/status"),

  monitorTrends: (days = 7) => request<MonitorTrends>(`/api/monitoring/trends?days=${days}`),

  monitorEvents: (days = 30, category?: string) =>
    request<MonitorEvent[]>(
      `/api/monitoring/events?days=${days}${category ? `&category=${category}` : ""}`,
    ),

  monitorAlerts: (hours = 48) => request<MonitorEvent[]>(`/api/monitoring/alerts?hours=${hours}`),

  monitorChanges: (days = 30) => request<MonitorEvent[]>(`/api/monitoring/changes?days=${days}`),

  monitorBootHistory: () => request<BootHistory>("/api/monitoring/boot-history"),

  monitorPredictions: () => request<MonitorPredictions>("/api/monitoring/predictions"),

  monitorMachineMemory: () => request<MachineMemory>("/api/monitoring/machine-memory"),

  monitorDigitalTwin: () => request<Record<string, any>>("/api/monitoring/digital-twin"),

  monitorReport: (period: "daily" | "weekly" | "monthly" = "daily") =>
    request<MonitorReport>(`/api/monitoring/report?period=${period}`),

  monitorIncident: (text: string, windowMinutes = 30) =>
    request<IncidentReport>(
      `/api/monitoring/incident?text=${encodeURIComponent(text)}&window_minutes=${windowMinutes}`,
      undefined,
      120_000,
      "Incident analysis",
    ),

  getMachineScan: (id: number) => request<MachineScanReport>(`/api/machine-scans/${id}`),

  deleteMachineScan: (id: number) =>
    request<{ deleted: boolean }>(`/api/machine-scans/${id}`, { method: "DELETE" }),

  /** LLM summary of a completed machine scan (on demand). */
  machineScanSummary: (report: MachineScanReport) =>
    request<MachineAiSummary>(
      "/api/diagnostics/full-scan/summary",
      {
        method: "POST",
        body: JSON.stringify(slimScanForSummary(report)),
      },
      SUMMARY_TIMEOUT_MS,
      "Summary",
    ),

  diagnose: (payload: DiagnosePayload) =>
    request<DiagnoseResponse>(
      "/api/chat/diagnose",
      {
        method: "POST",
        body: JSON.stringify(payload),
      },
      DIAGNOSE_TIMEOUT_MS,
      "Diagnosis",
    ),

  raiseTicket: (payload: RaiseTicketPayload) =>
    request<RaiseTicketResponse>("/api/chat/raise-ticket", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  listSessions: () => request<SessionSummary[]>("/api/sessions"),

  createSession: (title?: string) =>
    request<SessionSummary>("/api/sessions", {
      method: "POST",
      body: JSON.stringify({ title: title ?? null }),
    }),

  getSession: (id: number) => request<SessionDetail>(`/api/sessions/${id}`),

  deleteSession: (id: number) =>
    request<{ deleted: boolean }>(`/api/sessions/${id}`, { method: "DELETE" }),

  exportSessionUrl: (id: number, format: "json" | "pdf") =>
    `${BASE_URL}/api/sessions/${id}/export/${format}`,

  transcribe: async (audio: Blob): Promise<TranscriptionResponse> => {
    const form = new FormData();
    const name = audio.type.includes("wav") ? "recording.wav" : "recording.webm";
    form.append("file", audio, name);
    const resp = await fetch(`${BASE_URL}/api/voice/transcribe`, {
      method: "POST",
      body: form,
    });
    if (!resp.ok) {
      let message = "Transcription failed";
      try {
        message = (await resp.json())?.error?.message ?? message;
      } catch {
        /* ignore */
      }
      throw new ApiError(message, resp.status);
    }
    return (await resp.json()) as TranscriptionResponse;
  },

  ocr: async (image: File): Promise<OcrResponse> => {
    const form = new FormData();
    form.append("file", image, image.name);
    const resp = await fetch(`${BASE_URL}/api/screenshot/ocr`, {
      method: "POST",
      body: form,
    });
    if (!resp.ok) {
      let message = "OCR failed";
      try {
        message = (await resp.json())?.error?.message ?? message;
      } catch {
        /* ignore */
      }
      throw new ApiError(message, resp.status);
    }
    return (await resp.json()) as OcrResponse;
  },
};

export { ApiError };
