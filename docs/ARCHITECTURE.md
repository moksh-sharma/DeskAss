# Architecture

## Overview

Cache AI Assistant is split into a **FastAPI backend** (all intelligence,
diagnostics and integrations) and an **Electron + React frontend** (desktop UI).
The two communicate over a versioned REST API.

```
Electron (main + preload)
   └─ React renderer (Vite, Tailwind, Zustand)
         └─ REST ──► FastAPI
                       ├─ DI Container (composition root)
                       ├─ Services (clean architecture)
                       │    ├─ DiagnosticsService   (psutil / wmi / registry)
                       │    ├─ EventLogService       (pywin32)
                       │    ├─ OllamaService         (httpx -> LLM)
                       │    ├─ VoskService           (httpx -> STT)
                       │    ├─ OcrService            (pytesseract)
                       │    ├─ RagService            (ChromaDB + Sentence Transformers)
                       │    ├─ DiagnosisService      (fusion + prompt + parsing)
                       │    ├─ HealthService         (scan grading)
                       │    └─ SessionService        (SQLAlchemy + export)
                       └─ SQLite (sessions/messages)
```

## Design principles

- **Clean architecture / separation of concerns** — routes are thin; all logic
  lives in services. Schemas (`models/schemas.py`) define the contract; ORM
  models (`db/models.py`) define persistence.
- **Dependency injection** — a single `Container` (`core/container.py`)
  constructs and wires services as singletons. Routes receive it via the
  `container()` FastAPI dependency, making services easy to mock/replace.
- **Defensive collection** — every diagnostics probe is wrapped so one failing
  source (e.g. WMI unavailable) never breaks the whole report.
- **Lazy heavy deps** — ChromaDB / Sentence Transformers and Tesseract load on
  first use, keeping startup fast.
- **Graceful degradation** — non-Windows hosts skip event logs / registry;
  missing Tesseract disables OCR with a clear 503; unreachable Ollama/Vosk
  surface as `502` with actionable messages.
- **Grounded answers (RAG-first)** — the diagnosis engine always retrieves
  knowledge base context before prompting the LLM, and reconciles the model's
  output with deterministic, evidence-based severity & confidence.

## The diagnosis pipeline

1. **Persist** the user message to the session.
2. **Collect** live diagnostics + Windows event logs (toggleable).
3. **Retrieve** top-k knowledge base documents (ChromaDB cosine similarity).
4. **Compute** deterministic evidence + a heuristic severity floor from raw
   metrics (CPU/RAM/disk thresholds, error counts, crash events).
5. **Prompt** Ollama with a structured system+user prompt requesting strict JSON.
6. **Parse & reconcile** — merge LLM evidence with heuristic evidence, take the
   max severity, and adjust confidence based on corroborating evidence and KB hits.
7. **Persist** the assistant response (with the full diagnosis as metadata) and
   return everything to the UI.

## Confidence & severity model

- Severity per metric: `Healthy < Info < Warning < Critical`.
- Thresholds (configurable in `diagnostics_service.py`):
  CPU 75/90, RAM 80/92, Disk 85/95.
- Final severity = `max(LLM severity, heuristic severity)` so hard evidence
  cannot be downplayed.
- Confidence = LLM estimate, boosted by the count of warning/critical evidence
  items and high-scoring KB references, clamped to 1–99.

## Future expansion (designed-for)

The service-oriented layout supports incremental growth without rewrites:

- **Remote machine diagnostics** — add a `RemoteDiagnosticsService` implementing
  the same interface as `DiagnosticsService` (e.g. over WinRM/SSH), selected per
  request/agent.
- **Multi-user / Active Directory** — introduce an `auth` module + `user_id` on
  `Session`; the container already centralises construction for injecting an
  auth/identity service.
- **Microsoft 365 / Outlook / Teams log analysis** — new collector services feed
  additional context blocks into `DiagnosisService._build_prompt`.
- **Enterprise knowledge base** — swap the local ChromaDB store for a shared
  vector DB by changing only `RagService`.
- **Auto ticket creation (ServiceNow / Jira)** — add an `IntegrationService`
  consuming `DiagnosisResult`; trigger from the chat route after a diagnosis.
