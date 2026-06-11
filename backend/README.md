# HelpDesk Assistant — Backend

FastAPI service providing diagnostics, event-log analysis, OCR, RAG and the AI
diagnosis engine. See the top-level [`README.md`](../README.md),
[`docs/INSTALLATION.md`](../docs/INSTALLATION.md), [`docs/API.md`](../docs/API.md)
and [`docs/ARCHITECTURE.md`](../docs/ARCHITECTURE.md) for full detail.

## Run

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
uvicorn app.main:app --reload --port 8000
```

Docs: http://127.0.0.1:8000/docs

## Layout

```
app/
├── main.py              FastAPI app factory + lifespan
├── core/                config · logging · exceptions · DI container
├── api/
│   ├── router.py        aggregates routers
│   ├── deps.py          DI provider
│   └── routes/          health · diagnostics · chat · voice · screenshot · knowledge · sessions
├── db/                  SQLAlchemy engine + ORM models
├── models/schemas.py    Pydantic contracts
├── services/            diagnostics · eventlog · ollama · vosk · ocr · rag · diagnosis · health · session
├── knowledge_base/      seed troubleshooting docs (markdown)
└── scripts/seed_kb.py   knowledge base ingestion CLI
```

## Notes

- **Windows-first**: event logs (`pywin32`), startup programs & installed software
  (registry) require Windows. Other platforms degrade gracefully.
- **OCR** requires Tesseract installed and `TESSERACT_CMD` configured.
- **RAG** (ChromaDB + Sentence Transformers) auto-seeds from `app/knowledge_base`
  on first query; heavy deps load lazily so startup stays fast.
- The diagnosis engine reconciles the LLM output with deterministic, evidence-
  based severity and confidence so hard metrics are never downplayed.
