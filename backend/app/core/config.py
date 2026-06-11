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

    # Ollama
    ollama_base_url: str = "http://172.16.200.26:11434"
    default_model: str = "qwen2.5:latest"
    # Faster model for scan summaries (falls back to default_model when blank).
    summary_model: str = "llama3.2:3b"
    ollama_timeout_seconds: float = 360.0
    ollama_temperature: float = 0.2

    # Deepgram (Speech-to-Text) — multilingual Hindi + English
    deepgram_api_key: str = ""
    deepgram_model: str = "nova-3"
    # multi = auto Hindi/English code-switching; also accepts en or hi
    deepgram_language: str = "multi"
    deepgram_timeout_seconds: float = 120.0

    # RAG / Knowledge base
    chroma_dir: str = "./chroma_store"
    embedding_model: str = "all-MiniLM-L6-v2"
    kb_collection: str = "troubleshooting_kb"
    rag_top_k: int = 4

    # Investigation engine (issue-scoped live probes)
    investigation_enabled: bool = True
    investigation_use_llm: bool = True   # LLM generates a grounded diagnosis over live facts
    machine_scan_use_llm: bool = True    # LLM writes a grounded health summary for the full scan
    use_kb_in_diagnosis: bool = False     # legacy KB-based diagnosis path

    # OCR
    tesseract_cmd: str = ""

    # Database
    database_url: str = "sqlite:///./data/cache_assistant.sqlite3"

    # Storage
    upload_dir: str = "./uploads"

    # Support tickets (email)
    ticket_email_to: str = ""
    # auto | smtp | graph — auto uses Graph when Azure credentials are set.
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
