export type Severity = "Healthy" | "Info" | "Warning" | "Critical";
export type MessageRole = "user" | "assistant" | "system";

export interface CpuInfo {
  usage_percent: number;
  physical_cores: number | null;
  logical_cores: number | null;
  frequency_mhz: number | null;
}

export interface MemoryInfo {
  total_gb: number;
  used_gb: number;
  available_gb: number;
  usage_percent: number;
}

export interface DiskInfo {
  device: string;
  mountpoint: string;
  total_gb: number;
  free_gb: number;
  used_gb: number;
  usage_percent: number;
}

export interface NetworkAdapter {
  name: string;
  ip_address: string | null;
  is_up: boolean;
}

export interface NetworkInfo {
  adapters: NetworkAdapter[];
  primary_ip: string | null;
  internet_connected: boolean;
}

export interface OsInfo {
  system: string;
  release: string;
  version: string;
  build: string | null;
  architecture: string;
  hostname: string;
}

export interface BatteryInfo {
  present: boolean;
  percent: number | null;
  charging: boolean | null;
  secs_left: number | null;
}

export interface ProcessInfo {
  pid: number;
  name: string;
  cpu_percent: number;
  memory_mb: number;
}

export interface StartupProgram {
  name: string;
  command: string | null;
  location: string | null;
}

export interface InstalledSoftware {
  name: string;
  installed: boolean;
  version: string | null;
}

export interface SystemDiagnostics {
  collected_at: string;
  uptime_hours?: number | null;
  cpu: CpuInfo;
  memory: MemoryInfo;
  disks: DiskInfo[];
  network: NetworkInfo;
  os: OsInfo;
  battery: BatteryInfo;
  top_cpu_processes: ProcessInfo[];
  top_memory_processes: ProcessInfo[];
  startup_programs: StartupProgram[];
  installed_software: InstalledSoftware[];
  warnings: string[];
}

export interface EventLogEntry {
  source: string;
  log_name: string;
  level: string;
  event_id: number | null;
  time_generated: string | null;
  message: string;
  category: string | null;
}

export interface EventLogSummary {
  collected_at: string;
  available: boolean;
  error_count: number;
  warning_count: number;
  entries: EventLogEntry[];
  note: string | null;
}

export interface KnowledgeReference {
  doc_id: string;
  title: string;
  category: string;
  snippet: string;
  score: number;
}

export interface Evidence {
  label: string;
  value: string;
  severity: Severity;
}

export interface RecommendedFix {
  title: string;
  description: string;
  requires_confirmation: boolean;
  safe_action: string | null;
}

export interface DiagnosisResult {
  issue_summary: string;
  is_conversational?: boolean;
  severity: Severity;
  confidence: number;
  confidence_reasons: string[];
  root_cause: string;
  reasoning: string;
  evidence: Evidence[];
  recommended_fixes: RecommendedFix[];
  resolution_steps: string[];
  prevention_tips: string[];
  knowledge_references: KnowledgeReference[];
  model: string;
  raw_response: string | null;
}

export interface IssueProfile {
  domains: string[];
  primary_domain: string | null;
  apps: string[];
  symptoms: string[];
  confidence: number;
  needs_clarification: boolean;
  clarification_question: string | null;
}

export interface ProbeCheck {
  label: string;
  value: string;
  status: Severity;
  detail: string | null;
}

export interface ProbeResult {
  domain: string;
  title: string;
  available: boolean;
  checks: ProbeCheck[];
  note: string | null;
}

export interface InvestigationReport {
  generated_at: string;
  issue: string;
  profile: IssueProfile;
  probes: ProbeResult[];
  findings: TroubleshooterFinding[];
  overall_status: Severity;
  summary: string;
  scan_health_score?: number | null;
  scan_duration_seconds?: number | null;
}

export interface DiagnoseResponse {
  session_id: number;
  diagnosis: DiagnosisResult;
  diagnostics: SystemDiagnostics | null;
  event_logs: EventLogSummary | null;
  investigation?: InvestigationReport | null;
}

export interface HealthCheck {
  name: string;
  status: Severity;
  detail: string;
}

export interface TroubleshooterFinding {
  id: string;
  title: string;
  area: string;
  severity: Severity;
  detected: string;
  likely_cause: string;
  resolution_steps: string[];
  references: KnowledgeReference[];
  ask_ai_prompt: string;
}

export interface HealthReport {
  generated_at: string;
  overall_status: Severity;
  checks: HealthCheck[];
  findings: TroubleshooterFinding[];
  checks_passed: number;
  checks_total: number;
  summary: string;
  diagnostics: SystemDiagnostics;
  event_logs: EventLogSummary;
  recommendations: string[];
}

// --- Comprehensive machine scan ---------------------------------------- //
export interface HealthCategory {
  score: number;
  status: string;
  notes: string[];
}

export interface MachineHealthReport {
  overall_score: number;
  overall_status: string;
  categories: Record<string, HealthCategory>;
  recommended_actions: string[];
}

export interface MachineAiSummary {
  summary: string;
  prioritized_actions: string[];
  generated_by_llm: boolean;
  model: string;
}

export interface MachineScanReport {
  scan_id?: number | null;
  generated_at: string;
  scan_duration_seconds: number;
  hardware: Record<string, any>;
  software: Record<string, any>;
  ocr_results: Record<string, any>;
  rag_context: Record<string, any>;
  health_report: MachineHealthReport;
  ai_summary: MachineAiSummary;
  findings?: TroubleshooterFinding[];
  event_logs?: EventLogSummary | null;
}

export interface MachineScanHistorySummary {
  id: number;
  title: string;
  health_score: number;
  health_status: string;
  scan_duration_seconds: number;
  has_ai_summary: boolean;
  scanned_at: string;
  updated_at: string;
}

export interface SessionSummary {
  id: number;
  title: string;
  created_at: string;
  updated_at: string;
  message_count: number;
}

export interface MessageOut {
  id: number;
  role: MessageRole;
  content: string;
  created_at: string;
  metadata: { diagnosis?: DiagnosisResult; investigation?: InvestigationReport } | null;
}

export interface SessionDetail extends SessionSummary {
  messages: MessageOut[];
}

export interface ServiceStatus {
  name: string;
  healthy: boolean;
  detail: string;
}

export interface SystemStatus {
  status: string;
  version: string;
  services: ServiceStatus[];
}

export interface TranscriptionResponse {
  text: string;
}

export interface OcrResponse {
  text: string;
  detected_error_codes: string[];
}

// A chat message rendered in the UI (may carry a diagnosis payload).
export interface ChatMessage {
  id: string;
  role: MessageRole;
  content: string;
  createdAt: string;
  diagnosis?: DiagnosisResult;
  investigation?: InvestigationReport;
  pending?: boolean;
}
