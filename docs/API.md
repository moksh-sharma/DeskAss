# API Reference

Base URL: `http://127.0.0.1:8000`

Interactive docs (Swagger UI): `GET /docs` · OpenAPI JSON: `GET /openapi.json`

All errors use a consistent envelope:

```json
{ "error": { "code": "external_service_error", "message": "..." } }
```

---

## Health

### `GET /`
Liveness probe.
```json
{ "status": "running" }
```

### `GET /api/status`
Aggregated service health.
```json
{
  "status": "running",
  "version": "1.0.0",
  "services": [
    { "name": "ollama", "healthy": true, "detail": "http://172.16.200.26:11434 (qwen2.5:latest)" },
    { "name": "vosk", "healthy": true, "detail": "http://172.16.200.26:8001" },
    { "name": "ocr", "healthy": false, "detail": "Tesseract not found" },
    { "name": "knowledge_base", "healthy": true, "detail": "16 documents indexed" }
  ]
}
```

### `GET /api/models`
```json
{ "default": "qwen2.5:latest", "models": ["qwen2.5:latest", "llama3.1:latest"] }
```

---

## Diagnostics

### `GET /api/diagnostics?top_n=10`
Collect a live system snapshot (CPU, RAM, disks, network, OS, battery, processes,
startup programs, installed software). Returns a `SystemDiagnostics` object.

### `GET /api/diagnostics/event-logs?hours_back=72&max_per_log=60`
Collect recent Windows Event Log errors and warnings. On non-Windows hosts
returns `{ "available": false, "note": "..." }`.

### `POST /api/diagnostics/scan`
Run a full diagnostic scan and return a graded `HealthReport`:
```json
{
  "overall_status": "Warning",
  "checks": [{ "name": "CPU", "status": "Healthy", "detail": "12% utilisation" }],
  "diagnostics": { "...": "SystemDiagnostics" },
  "event_logs": { "...": "EventLogSummary" },
  "recommendations": ["Disk C: is low on space — run Disk Cleanup."]
}
```

---

## Chat / Diagnosis

### `POST /api/chat/diagnose`
The core endpoint. Collects diagnostics + event logs, retrieves knowledge base
context, runs the LLM, and persists the exchange to the session.

Request:
```json
{
  "session_id": null,
  "message": "My Outlook crashes whenever I open it.",
  "include_diagnostics": true,
  "include_event_logs": true,
  "ocr_text": "0x80070005 Access Denied",
  "model": "qwen2.5:latest"
}
```

Response (`DiagnoseResponse`):
```json
{
  "session_id": 1,
  "diagnosis": {
    "issue_summary": "Outlook crashes on launch",
    "severity": "Warning",
    "confidence": 88,
    "confidence_reasons": ["RAM Usage: 91%", "Outlook Crash event detected"],
    "root_cause": "A faulty COM add-in is crashing Outlook on startup.",
    "reasoning": "Application Error events reference OUTLOOK.EXE ...",
    "evidence": [{ "label": "RAM Usage", "value": "91%", "severity": "Critical" }],
    "recommended_fixes": [
      { "title": "Start Outlook in Safe Mode", "description": "Run outlook.exe /safe ...",
        "safe_action": "Run outlook.exe /safe", "requires_confirmation": true }
    ],
    "resolution_steps": ["Open Run", "Type outlook.exe /safe", "..."],
    "prevention_tips": ["Keep add-ins minimal"],
    "knowledge_references": [
      { "doc_id": "ab12", "title": "Outlook Crashes or Hangs", "category": "outlook",
        "snippet": "...", "score": 0.71 }
    ],
    "model": "qwen2.5:latest"
  },
  "diagnostics": { "...": "SystemDiagnostics" },
  "event_logs": { "...": "EventLogSummary" }
}
```

---

## Voice

### `POST /api/voice/transcribe`  *(multipart/form-data)*
Field `file` = audio clip. Proxies to the Vosk service.
```json
{ "text": "my laptop is running slow" }
```

---

## Screenshot OCR

### `POST /api/screenshot/ocr`  *(multipart/form-data)*
Field `file` = image. Returns extracted text and detected error codes.
```json
{ "text": "Access Denied 0x80070005", "detected_error_codes": ["0x80070005"] }
```

---

## Knowledge Base

### `GET /api/knowledge/search?q=outlook+crash&top_k=4`
Returns a list of `KnowledgeReference` results.

### `GET /api/knowledge/count`
`{ "count": 16 }`

### `POST /api/knowledge/reseed`
Re-ingest all on-disk documents. `{ "indexed": 16 }`

---

## Sessions

| Method | Path | Description |
|--------|------|-------------|
| `GET`    | `/api/sessions` | List sessions (summaries) |
| `POST`   | `/api/sessions` | Create a session `{ "title": "optional" }` |
| `GET`    | `/api/sessions/{id}` | Session with all messages |
| `DELETE` | `/api/sessions/{id}` | Delete a session |
| `GET`    | `/api/sessions/{id}/export/json` | Download session as JSON |
| `GET`    | `/api/sessions/{id}/export/pdf`  | Download session as PDF |
