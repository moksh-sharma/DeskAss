"""Lightweight dependency-injection container.

Holds singleton service instances and wires their dependencies. Created once at
application startup and exposed to routes via FastAPI dependencies (see
``app.api.deps``).
"""
from __future__ import annotations

from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.services.audio_service import AudioService
from app.services.diagnosis_service import DiagnosisService
from app.services.diagnostics_service import DiagnosticsService
from app.services.eventlog_service import EventLogService
from app.services.health_service import HealthService
from app.services.investigation_service import InvestigationService
from app.services.machine_cache_service import MachineCacheService
from app.services.machine_scan_history_service import MachineScanHistoryService
from app.services.machine_scan_service import MachineScanService
from app.services.monitoring_service import MonitoringService
from app.services.telemetry_analytics_service import TelemetryAnalyticsService
from app.services.ocr_service import OcrService
from app.services.system_inventory import SystemInventory
from app.services.rag_service import RagService
from app.services.session_service import SessionService
from app.services.ticket_service import TicketService
from app.services.troubleshooter_service import TroubleshooterService
from app.services.speech_service import SpeechService
from app.services.storage_intelligence_service import StorageIntelligenceService
from app.services.storage_scan_history_service import StorageScanHistoryService
from app.services.visual_guide_service import VisualGuideService

logger = get_logger(__name__)


class Container:
    """Composition root - constructs and holds all service singletons."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

        # Stateless / cheap services.
        self.diagnostics = DiagnosticsService()
        self.event_logs = EventLogService()
        self.health = HealthService()
        self.sessions = SessionService()
        self.tickets = TicketService(self.settings)
        self.machine_scan_history = MachineScanHistoryService()
        self.storage_history = StorageScanHistoryService()
        self.storage = StorageIntelligenceService()
        self.inventory = SystemInventory()
        self.visual_guides = VisualGuideService()

        # Continuous monitoring (background sampler) + read-side analytics.
        self.telemetry = TelemetryAnalyticsService()
        # Instant-read summary cache (Layer: Local Cache Engine), refreshed by the
        # monitoring loop so chat/UI can answer common questions in milliseconds.
        self.machine_cache = MachineCacheService(
            cache_dir=self.settings.sqlite_path.parent / "cache",
            telemetry=self.telemetry,
        )
        self.monitoring = MonitoringService(self.settings, cache=self.machine_cache)

        # External clients.
        self.audio = AudioService()
        self.speech = SpeechService(self.settings)
        self.ocr = OcrService(self.settings)

        # Heavy / lazy services.
        self.rag = RagService(self.settings)

        # Composite services (fully deterministic - no AI model in the answer path).
        self.diagnosis = DiagnosisService()
        self.troubleshooter = TroubleshooterService(self.rag)
        self.machine_scan = MachineScanService(
            inventory=self.inventory,
            storage=self.storage,
        )
        self.investigation = InvestigationService(
            inventory=self.inventory,
            machine_scan=self.machine_scan,
            visual_guides=self.visual_guides,
            telemetry=self.telemetry,
        )

        logger.info("Service container initialised.")


_container: Container | None = None


def init_container() -> Container:
    global _container
    if _container is None:
        _container = Container()
    return _container


def get_container() -> Container:
    if _container is None:
        return init_container()
    return _container
