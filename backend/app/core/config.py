"""Application configuration loaded from environment variables / .env file."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parents[2]  # .../backend


class Settings(BaseSettings):
    """Strongly-typed application settings."""

    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    app_name: str = "HelpDesk Assistant"
    app_env: str = "development"
    log_level: str = "INFO"
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173,app://-"

    # Speech-to-Text provider: elevenlabs | deepgram
    stt_provider: str = "elevenlabs"

    # ElevenLabs Scribe (Speech-to-Text) - multilingual Hindi + English
    elevenlabs_api_key: str = ""
    # Batch uploads (/api/voice/transcribe)
    elevenlabs_stt_model: str = "scribe_v2"
    # Live mic WebSocket - Scribe v2 Realtime
    elevenlabs_stt_realtime_model: str = "scribe_v2_realtime"
    # vad = auto segment on pauses (recommended for Scribe v2 Realtime); manual = commit on stop
    elevenlabs_realtime_commit_strategy: str = "vad"
    # multi = auto language detect; also accepts en or hi
    elevenlabs_language: str = "multi"
    elevenlabs_timeout_seconds: float = 120.0

    # Deepgram (legacy fallback)
    deepgram_api_key: str = ""
    deepgram_model: str = "nova-3"
    deepgram_language: str = "multi"
    deepgram_timeout_seconds: float = 120.0

    # RAG / Knowledge base
    chroma_dir: str = "./chroma_store"
    embedding_model: str = "all-MiniLM-L6-v2"
    kb_collection: str = "troubleshooting_kb"
    rag_top_k: int = 4

    # Investigation engine (issue-scoped live probes) - fully deterministic.
    investigation_enabled: bool = True
    # Chat troubleshooter scan scope: "domain" runs only the scanners the issue
    # needs (fast); "full" runs the entire machine scan for every chat message.
    investigation_scan_mode: str = "domain"
    # Reuse a recent scoped investigation scan when the same domains are queried again.
    investigation_scan_cache_seconds: float = 45.0
    # Query-first fast path: answer resource/usage questions from cached telemetry
    # or a fast psutil-only read instead of a heavier scoped machine scan.
    investigation_fast_path: bool = True
    # Treat a cached telemetry snapshot as usable for instant answers up to this age.
    investigation_telemetry_max_age_seconds: float = 120.0

    # Deep storage scan (heavy filesystem tree walk + duplicate detection)
    storage_deep_enabled: bool = True
    # When true, Full System Scan runs the deep storage walk in parallel with other scanners.
    storage_deep_on_full_scan: bool = True
    storage_deep_tree_budget_seconds: float = 60.0
    storage_deep_duplicate_budget_seconds: float = 15.0
    # Shorter budgets used for the chat troubleshooter so storage answers are fast.
    investigation_storage_tree_budget_seconds: float = 30.0
    investigation_storage_duplicate_budget_seconds: float = 5.0

    # Continuous monitoring engine (enterprise telemetry tiers)
    monitoring_enabled: bool = True
    monitoring_cpu_ram_seconds: int = 5       # CPU + RAM sample cadence
    monitoring_disk_net_seconds: int = 10     # disk I/O + network throughput
    monitoring_process_seconds: int = 15      # top-process enrichment cadence
    monitoring_sample_seconds: int = 5        # master loop tick (min tier)
    monitoring_detailed_minutes: int = 5       # enrich with top processes / GPU / latency
    monitoring_deep_minutes: int = 30          # inventory snapshots + change detection
    monitoring_retention_fine_days: int = 7    # keep 30s samples this long
    monitoring_retention_detailed_days: int = 90  # keep 5-min samples this long
    # How often the background loop refreshes the instant-read summary JSON cache.
    cache_refresh_seconds: float = 60.0

    # OCR
    tesseract_cmd: str = ""

    # Database
    database_url: str = "sqlite:///./data/cache_assistant.sqlite3"

    # Storage
    upload_dir: str = "./uploads"

    # Support tickets (email)
    ticket_email_to: str = ""
    # auto | smtp | graph - auto uses Graph when Azure credentials are set.
    ticket_email_transport: str = "auto"
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    smtp_use_tls: bool = True
    # Microsoft Graph (works when M365 SMTP AUTH is disabled on the tenant)
    azure_tenant_id: str = ""
    azure_client_id: str = ""
    azure_client_secret: str = ""
    graph_send_as_user: str = ""

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    def resolve(self, relative: str) -> Path:
        """Resolve a possibly-relative path against the backend base directory."""
        p = Path(relative)
        return p if p.is_absolute() else (BASE_DIR / p)

    @property
    def chroma_path(self) -> Path:
        return self.resolve(self.chroma_dir)

    @property
    def upload_path(self) -> Path:
        return self.resolve(self.upload_dir)

    @property
    def sqlite_path(self) -> Path:
        # Extract file path from sqlite URL for directory creation.
        url = self.database_url
        if url.startswith("sqlite:///"):
            return self.resolve(url.replace("sqlite:///", "", 1))
        return BASE_DIR / "data" / "cache_assistant.sqlite3"


@lru_cache
def get_settings() -> Settings:
    """Cached settings singleton."""
    return Settings()
