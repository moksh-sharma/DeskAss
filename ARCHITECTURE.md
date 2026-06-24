# Enterprise Desktop Diagnostics Architecture

**Cache AI Assistant** is a 100% offline-capable, deterministic Windows diagnostics platform.
No LLM, no cloud APIs, no hallucinated answers — every response is built from live
machine data and rule-based templates.

## Stack

| Layer | Technology |
|-------|------------|
| Desktop shell | Electron |
| UI | React + TypeScript + Tailwind |
| API / engines | **Python FastAPI** (not Node — collectors use WMI/PowerShell natively) |
| Data collection | PowerShell, WMI/CIM, Registry, Event Logs, netstat, psutil |
| History | SQLite (`telemetry_samples`, `monitor_events`, scan history) |

## Pipeline

```
User question
  → Intent Parser (issue_parser + question_intent + scan_orchestrator)
  → Scan Orchestrator (minimal scanners + depth: quick/deep/forensic)
  → Data Collectors (scanners/*, probes/*, monitoring_service)
  → Correlation Engine (knowledge graph + cross-signal links)
  → Rules Engine (IF/THEN deterministic rules)
  → Timeline Engine (historical events + changes)
  → Response Generator (templates → DiagnosisResult)
  → React UI
```

## Modules

| Module | File |
|--------|------|
| Intent Parser | `app/services/issue_parser.py`, `question_intent.py`, `scan_orchestrator.py` |
| Scan Orchestrator | `app/services/scan_orchestrator.py`, `machine_scan_service.py` |
| Data Collectors | `app/services/scanners/`, `app/services/probes/` |
| Correlation Engine | `app/services/correlation_engine.py` |
| Rules Engine | `app/services/rules_engine.py` |
| Timeline Engine | `app/services/timeline_engine.py` |
| Response Generator | `app/services/response_generator.py` |
| Historical DB | `app/db/models.py`, `telemetry_analytics_service.py` |
| Investigation | `app/services/investigation_service.py` |

## Enterprise intents

All spec intents are supported (some as aliases):

`hardware_inventory`, `hardware_health`, `software_inventory`, `software_analysis`,
`performance_analysis`, `storage_analysis`, `network_analysis`, `network_discovery`,
`printer_discovery`, `device_analysis`, `driver_analysis`, `security_analysis`,
`battery_analysis`, `windows_health`, `event_log_analysis`, `crash_analysis`,
`change_analysis`, `incident_reconstruction`, `recommendation`, `reporting`,
`full_system_scan`.

## Scan levels

| Level | SLA target | Behavior |
|-------|------------|----------|
| `quick` | < 2s | Minimal scanners; excludes event logs, crash forensics, deep storage |
| `deep` | < 10s | Issue-scoped scanners + targeted event/crash layers |
| `forensic` | < 60s | Full correlation, incident reconstruction, deep storage when relevant |

Only **Full System Scan** / **Enterprise Audit** phrases run all collectors.

## Real-time telemetry

Background `MonitoringService` samples:

- CPU + RAM every **5s**
- Disk + network I/O every tick (10s tier metadata)
- Top processes every **15s**

Stored in SQLite for 24h / 7d / 30d / 90d analysis via `TelemetryAnalyticsService`.

## Determinism guarantee

- Chat `/api/chat/diagnose` uses `InvestigationService` only — **no OpenAI/Ollama/Gemini/Claude**.
- Answers use scan facts, rules, and string templates.
- STT (ElevenLabs/Deepgram) is optional for voice input only; it does not generate diagnoses.

## Running probes

```powershell
cd backend
.\.venv\Scripts\python.exe scripts\scan_coverage_probe.py
.\.venv\Scripts\python.exe scripts\scan_orchestration_probe.py
.\.venv\Scripts\python.exe scripts\enterprise_diagnostics_probe.py
```
