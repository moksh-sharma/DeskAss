# Installation Guide

This guide covers a development setup on **Windows 10/11** (the primary target),
with notes for other platforms.

## 1. Prerequisites

| Component | Version | Notes |
|-----------|---------|-------|
| Python    | 3.11+   | 3.12 recommended |
| Node.js   | 18+     | 20/22 recommended (Electron/Vite) |
| Ollama    | latest  | Running and reachable at `OLLAMA_BASE_URL` |
| Tesseract OCR | 5.x | Required only for screenshot OCR |
| Vosk service | — | Already deployed at `http://172.16.200.26:8001` |

### Ollama

Install Ollama and pull the default model on the host that serves it:

```bash
ollama pull qwen2.5:latest
```

The backend talks to Ollama over HTTP, so it can be local
(`http://localhost:11434`) or remote (`http://172.16.200.26:11434`).

### Tesseract OCR (Windows)

Download the installer from the UB-Mannheim build and install to the default
location. Then set `TESSERACT_CMD` in `backend/.env`:

```
TESSERACT_CMD=C:\Program Files\Tesseract-OCR\tesseract.exe
```

If Tesseract is on your `PATH`, you may leave it blank. OCR is optional — the
rest of the app works without it.

## 2. Backend

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1          # PowerShell
# source .venv/bin/activate            # macOS/Linux

pip install -r requirements.txt
copy .env.example .env                  # then edit values
```

> The first install pulls `sentence-transformers` / `torch`, which is large.
> Allow several minutes and ~2 GB of disk.

### Configure

Edit `backend/.env`:

```
OLLAMA_BASE_URL=http://172.16.200.26:11434
DEFAULT_MODEL=qwen2.5:latest
VOSK_API_URL=http://172.16.200.26:8001
```

### Seed the knowledge base (optional)

The knowledge base auto-seeds on first query, but you can pre-build it:

```powershell
python -m app.scripts.seed_kb
```

### Run

```powershell
uvicorn app.main:app --reload --port 8000
# or:  python -m app.main
```

Open http://127.0.0.1:8000/docs for the interactive API documentation.

## 3. Frontend

```powershell
cd frontend
npm install
copy .env.example .env                  # optional; defaults to 127.0.0.1:8000
npm run dev
```

`npm run dev` starts Vite **and** launches the Electron desktop window
automatically. The renderer hot-reloads on changes.

### Build a distributable

```powershell
npm run build      # type-check + bundle renderer + main
npm run dist       # package a Windows installer (electron-builder)
```

The installer is written to `frontend/release/`.

## 4. Verifying the setup

1. Backend health: open http://127.0.0.1:8000/ → `{"status":"running"}`.
2. Service status: http://127.0.0.1:8000/api/status shows Ollama / Vosk / OCR / KB health.
3. In the app, the top bar shows green dots for healthy services.
4. Type a problem (e.g. *"My laptop is slow"*) and press **Send**.

## 5. Troubleshooting the installer

| Problem | Fix |
|---------|-----|
| `Ollama request timed out` | Ensure the model is pulled and `OLLAMA_BASE_URL` is reachable. |
| OCR returns 503 | Install Tesseract and set `TESSERACT_CMD`. |
| Event logs "unavailable" | Expected on non-Windows; on Windows ensure `pywin32` is installed. |
| Frontend can't reach backend | Confirm backend is on port 8000 and CORS origins include the Vite URL. |
| `torch` install fails | Install a CPU wheel: `pip install torch --index-url https://download.pytorch.org/whl/cpu`. |
