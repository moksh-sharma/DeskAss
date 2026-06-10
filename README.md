# Cache AI Assistant

**Enterprise AI Desktop Troubleshooting Assistant** — an intelligent IT Support Engineer that
diagnoses and resolves Windows machine issues using voice, text, screenshots, live system
diagnostics, Windows Event Logs, a local RAG knowledge base, and a local Ollama LLM.

```
┌──────────────────────────────────────────────────────────────────┐
│                      Electron + React (UI)                          │
│   Sidebar · Chat · Toolbar (text/voice/screenshot/scan) · Metrics  │
└───────────────────────────────┬──────────────────────────────────┘
                                 │ HTTP (REST)
┌───────────────────────────────▼──────────────────────────────────┐
│                          FastAPI Backend                            │
│  ┌────────────┐ ┌────────────┐ ┌──────────┐ ┌──────────────────┐  │
│  │ Diagnostics│ │ Event Logs │ │   OCR    │ │  Vosk (STT proxy)│  │
│  └────────────┘ └────────────┘ └──────────┘ └──────────────────┘  │
│  ┌────────────┐ ┌────────────┐ ┌──────────────────────────────┐   │
│  │  RAG / KB  │ │   Ollama   │ │   Diagnosis Engine (fusion)  │   │
│  │ (ChromaDB) │ │  (LLM)     │ │ root-cause · confidence · fix│   │
│  └────────────┘ └────────────┘ └──────────────────────────────┘   │
│                         SQLite (session history)                    │
└────────────────────────────────────────────────────────────────────┘
        │                         │                         │
   ChromaDB store         Ollama @ :11434          Vosk @ :8001
```

## Features

- **Voice support** — record audio in the app, transcribed via the Vosk service.
- **Text support** — free-form problem descriptions.
- **Automatic diagnostics** — CPU, RAM, disk, network, OS, battery, processes, startup, software.
- **Windows Event Log analysis** — application/system errors & warnings (Outlook, Teams, drivers…).
- **Screenshot analysis** — Tesseract OCR extracts error codes / messages.
- **Local RAG knowledge base** — ChromaDB + Sentence Transformers, grounded answers.
- **AI diagnosis engine** — fuses all evidence into root cause, confidence, severity, fixes.
- **Confidence scoring & evidence-based reasoning** — every diagnosis is justified.
- **Full diagnostic scan** — generates a machine health report (Healthy / Warning / Critical).
- **Session history** — stored in SQLite, exportable to JSON / PDF.
- **Live dashboard** — auto-refreshing system metrics.

## Repository layout

```
cache-ai-assistant/
├── backend/            FastAPI service (Python)
│   └── app/
│       ├── api/        REST routes
│       ├── core/       config, logging, exceptions, DI container
│       ├── db/         SQLite engine + repositories
│       ├── models/     Pydantic schemas + ORM models
│       ├── services/   diagnostics, eventlog, ollama, vosk, ocr, rag, diagnosis
│       └── knowledge_base/  seed troubleshooting docs
├── frontend/           Electron + React + TypeScript + Tailwind + Zustand
└── docs/               API reference, installation guide
```

## Quick start

See [`docs/INSTALLATION.md`](docs/INSTALLATION.md) for full setup. In short:

```bash
# Backend
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1      # Windows PowerShell
pip install -r requirements.txt
copy .env.example .env
python -m app.scripts.seed_kb     # ingest knowledge base (optional, auto-runs on first query)
uvicorn app.main:app --reload --port 8000

# Frontend (new terminal)
cd frontend
npm install
npm run dev          # Vite + Electron in development
```

## Configuration

Copy `backend/.env.example` to `backend/.env` and adjust:

```
OLLAMA_BASE_URL=http://172.16.200.26:11434
DEFAULT_MODEL=qwen2.5:latest
VOSK_API_URL=http://172.16.200.26:8001
```

See [`docs/API.md`](docs/API.md) for the REST API reference.

## License

Internal enterprise tooling. All rights reserved.
