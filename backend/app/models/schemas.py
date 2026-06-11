"""Pydantic schemas used across the API surface."""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


# --------------------------------------------------------------------------- #
#  Enums
# --------------------------------------------------------------------------- #
class Severity(str, Enum):
    healthy = "Healthy"
    info = "Info"
    warning = "Warning"
    critical = "Critical"


class MessageRole(str, Enum):
    user = "user"
    assistant = "assistant"
    system = "system"


# --------------------------------------------------------------------------- #
#  Diagnostics
# --------------------------------------------------------------------------- #
class CpuInfo(BaseModel):
    usage_percent: float = 0.0
    physical_cores: Optional[int] = None
    logical_cores: Optional[int] = None
    frequency_mhz: Optional[float] = None


class MemoryInfo(BaseModel):
    total_gb: float = 0.0
    used_gb: float = 0.0
    available_gb: float = 0.0
    usage_percent: float = 0.0


class DiskInfo(BaseModel):
    device: str
    mountpoint: str
    total_gb: float = 0.0
    free_gb: float = 0.0
    used_gb: float = 0.0
    usage_percent: float = 0.0


class NetworkAdapter(BaseModel):
    name: str
    ip_address: Optional[str] = None
    is_up: bool = False


class NetworkInfo(BaseModel):
    adapters: list[NetworkAdapter] = Field(default_factory=list)
    primary_ip: Optional[str] = None
    internet_connected: bool = False


class OsInfo(BaseModel):
    system: str = ""
    release: str = ""
    version: str = ""
    build: Optional[str] = None
    architecture: str = ""
    hostname: str = ""


class BatteryInfo(BaseModel):
    present: bool = False
    percent: Optional[float] = None
    charging: Optional[bool] = None
    secs_left: Optional[int] = None


class ProcessInfo(BaseModel):
    pid: int
    name: str
    cpu_percent: float = 0.0
    memory_mb: float = 0.0


class StartupProgram(BaseModel):
    name: str
    command: Optional[str] = None
    location: Optional[str] = None


class InstalledSoftware(BaseModel):
    name: str
    installed: bool
    version: Optional[str] = None


class SystemDiagnostics(BaseModel):
    collected_at: datetime = Field(default_factory=datetime.utcnow)
    uptime_hours: Optional[float] = None
    cpu: CpuInfo = Field(default_factory=CpuInfo)
    memory: MemoryInfo = Field(default_factory=MemoryInfo)
    disks: list[DiskInfo] = Field(default_factory=list)
    network: NetworkInfo = Field(default_factory=NetworkInfo)
    os: OsInfo = Field(default_factory=OsInfo)
    battery: BatteryInfo = Field(default_factory=BatteryInfo)
    top_cpu_processes: list[ProcessInfo] = Field(default_factory=list)
    top_memory_processes: list[ProcessInfo] = Field(default_factory=list)
    startup_programs: list[StartupProgram] = Field(default_factory=list)
    installed_software: list[InstalledSoftware] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
#  Event logs
# --------------------------------------------------------------------------- #
class EventLogEntry(BaseModel):
    source: str
    log_name: str
    level: str
    event_id: Optional[int] = None
    time_generated: Optional[datetime] = None
    message: str = ""
    category: Optional[str] = None


class EventLogSummary(BaseModel):
    collected_at: datetime = Field(default_factory=datetime.utcnow)
    available: bool = True
    error_count: int = 0
    warning_count: int = 0
    entries: list[EventLogEntry] = Field(default_factory=list)
    note: Optional[str] = None


# --------------------------------------------------------------------------- #
#  RAG
# --------------------------------------------------------------------------- #
class KnowledgeReference(BaseModel):
    doc_id: str
    title: str
    category: str
    snippet: str
    score: float = 0.0


# --------------------------------------------------------------------------- #
#  Diagnosis
# --------------------------------------------------------------------------- #
class Evidence(BaseModel):
    label: str
    value: str
    severity: Severity = Severity.info


class RecommendedFix(BaseModel):
    title: str
    description: str
    requires_confirmation: bool = True
    safe_action: Optional[str] = None


class DiagnosisResult(BaseModel):
    issue_summary: str = ""
    is_conversational: bool = False
    severity: Severity = Severity.info
    confidence: int = 0  # 0-100
    confidence_reasons: list[str] = Field(default_factory=list)
    root_cause: str = ""
    reasoning: str = ""
    evidence: list[Evidence] = Field(default_factory=list)
    recommended_fixes: list[RecommendedFix] = Field(default_factory=list)
    resolution_steps: list[str] = Field(default_factory=list)
    prevention_tips: list[str] = Field(default_factory=list)
    knowledge_references: list[KnowledgeReference] = Field(default_factory=list)
    model: str = ""
    raw_response: Optional[str] = None


# --------------------------------------------------------------------------- #
#  Chat / diagnosis requests
# --------------------------------------------------------------------------- #
class DiagnoseRequest(BaseModel):
    session_id: Optional[int] = None
    message: str = Field(..., min_length=1, description="User problem description")
    include_diagnostics: bool = True
    include_event_logs: bool = True
    ocr_text: Optional[str] = None


class DiagnoseResponse(BaseModel):
    session_id: int
    diagnosis: DiagnosisResult
    diagnostics: Optional[SystemDiagnostics] = None
    event_logs: Optional[EventLogSummary] = None
    investigation: Optional["InvestigationReport"] = None


class RaiseTicketRequest(BaseModel):
    session_id: Optional[int] = None
    user_issue: str = Field(..., min_length=1, description="The user's reported problem")
    diagnosis: Optional[DiagnosisResult] = None
    assistant_reply: Optional[str] = Field(
        None,
        description="Plain assistant reply when no structured diagnosis is available",
    )


class RaiseTicketResponse(BaseModel):
    sent: bool = True
    message: str = "Support ticket email sent."


# --------------------------------------------------------------------------- #
#  Voice / OCR
# --------------------------------------------------------------------------- #
class TranscriptionResponse(BaseModel):
    text: str


class OcrResponse(BaseModel):
    text: str
    detected_error_codes: list[str] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
#  Health report (full scan)
# --------------------------------------------------------------------------- #
class HealthCheck(BaseModel):
    name: str
    status: Severity
    detail: str


class TroubleshooterFinding(BaseModel):
    """A single detected issue with its cause and step-by-step resolution,
    presented like a Windows Troubleshooter result."""

    id: str
    title: str
    area: str = "System"  # Performance, Storage, Network, Power, Stability, Security, Startup, System
    severity: Severity = Severity.warning
    detected: str = ""  # what the scan observed (evidence)
    likely_cause: str = ""
    resolution_steps: list[str] = Field(default_factory=list)
    references: list[KnowledgeReference] = Field(default_factory=list)
    ask_ai_prompt: str = ""  # sent to the assistant for a deeper, tailored fix


class HealthReport(BaseModel):
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    overall_status: Severity
    checks: list[HealthCheck] = Field(default_factory=list)
    findings: list[TroubleshooterFinding] = Field(default_factory=list)
    checks_passed: int = 0
    checks_total: int = 0
    summary: str = ""
    diagnostics: SystemDiagnostics
    event_logs: EventLogSummary
    recommendations: list[str] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
#  Issue-scoped investigation (live, evidence-first)
# --------------------------------------------------------------------------- #
class IssueProfile(BaseModel):
    """Parsed understanding of the user's reported problem."""

    domains: list[str] = Field(default_factory=list)
    primary_domain: Optional[str] = None
    apps: list[str] = Field(default_factory=list)
    symptoms: list[str] = Field(default_factory=list)
    confidence: float = 0.0
    needs_clarification: bool = False
    clarification_question: Optional[str] = None


class ProbeCheck(BaseModel):
    """A single observed fact from a live probe."""

    label: str
    value: str
    status: Severity = Severity.info
    detail: Optional[str] = None


class ProbeResult(BaseModel):
    """Structured output of one domain probe pack."""

    domain: str
    title: str
    available: bool = True
    checks: list[ProbeCheck] = Field(default_factory=list)
    note: Optional[str] = None


class InvestigationReport(BaseModel):
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    issue: str = ""
    profile: IssueProfile = Field(default_factory=IssueProfile)
    probes: list[ProbeResult] = Field(default_factory=list)
    findings: list[TroubleshooterFinding] = Field(default_factory=list)
    overall_status: Severity = Severity.info
    summary: str = ""
    # Metadata from the comprehensive machine scan backing this investigation.
    scan_health_score: Optional[int] = None
    scan_duration_seconds: Optional[float] = None
    scan_facts: Optional[dict[str, Any]] = Field(default=None, exclude=True)


# --------------------------------------------------------------------------- #
#  Comprehensive machine scan
# --------------------------------------------------------------------------- #
class HealthCategory(BaseModel):
    score: int = 100  # 0-100
    status: Severity | str = "Healthy"
    notes: list[str] = Field(default_factory=list)


class MachineHealthReport(BaseModel):
    overall_score: int = 100
    overall_status: str = "Healthy"
    categories: dict[str, HealthCategory] = Field(default_factory=dict)
    recommended_actions: list[str] = Field(default_factory=list)


class MachineAiSummary(BaseModel):
    """Grounded, LLM-written narrative over the full machine scan."""

    summary: str = ""
    prioritized_actions: list[str] = Field(default_factory=list)
    generated_by_llm: bool = False
    model: str = ""


class MachineScanSummaryRequest(BaseModel):
    """Payload for on-demand LLM summary generation after a full scan."""

    scan_id: Optional[int] = None
    generated_at: str = ""
    scan_duration_seconds: float = 0.0
    hardware: dict[str, Any] = Field(default_factory=dict)
    software: dict[str, Any] = Field(default_factory=dict)
    health_report: MachineHealthReport = Field(default_factory=MachineHealthReport)


class MachineScanHistorySummary(BaseModel):
    id: int
    title: str
    health_score: int = 0
    health_status: str = "Unknown"
    scan_duration_seconds: float = 0.0
    has_ai_summary: bool = False
    scanned_at: datetime
    updated_at: datetime


class MachineScanReport(BaseModel):
    """Full structured snapshot of the machine, organised into two buckets:

    - ``hardware``: every physical component/device on the machine plus live
      performance (CPU, RAM, storage/SMART, GPU, battery, motherboard, all PnP
      devices, peripherals, network adapters).
    - ``software``: everything software (OS, all installed applications, running
      processes, services, startup, security, crashes, event logs, networking).

    Payloads are flexible dicts so each scanner can evolve without breaking the
    API contract.
    """

    scan_id: Optional[int] = None
    generated_at: str = ""
    scan_duration_seconds: float = 0.0
    hardware: dict[str, Any] = Field(default_factory=dict)
    software: dict[str, Any] = Field(default_factory=dict)
    ocr_results: dict[str, Any] = Field(default_factory=dict)
    rag_context: dict[str, Any] = Field(default_factory=dict)
    health_report: MachineHealthReport = Field(default_factory=MachineHealthReport)
    ai_summary: MachineAiSummary = Field(default_factory=MachineAiSummary)
    findings: list[TroubleshooterFinding] = Field(default_factory=list)
    event_logs: Optional[EventLogSummary] = None


# --------------------------------------------------------------------------- #
#  Sessions
# --------------------------------------------------------------------------- #
class SessionCreate(BaseModel):
    title: Optional[str] = None


class MessageOut(BaseModel):
    id: int
    role: MessageRole
    content: str
    created_at: datetime
    metadata: Optional[dict[str, Any]] = None


class SessionSummary(BaseModel):
    id: int
    title: str
    created_at: datetime
    updated_at: datetime
    message_count: int = 0


class SessionDetail(SessionSummary):
    messages: list[MessageOut] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
#  Service health
# --------------------------------------------------------------------------- #
class ServiceStatus(BaseModel):
    name: str
    healthy: bool
    detail: str = ""


class SystemStatus(BaseModel):
    status: str = "running"
    version: str
    services: list[ServiceStatus] = Field(default_factory=list)


# Resolve forward references (DiagnoseResponse -> InvestigationReport).
DiagnoseResponse.model_rebuild()
