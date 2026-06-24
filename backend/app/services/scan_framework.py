"""Enterprise scan framework registry.

Single source of truth mapping enterprise scan categories to scanner modules.
Scan *selection* for chat investigations is driven by ``scan_orchestrator`` so
only the telemetry required to answer the question is collected.
"""
from __future__ import annotations

from app.services.scan_orchestrator import ScanPlan, build_scan_plan

# --------------------------------------------------------------------------- #
#  Category -> scanner keys (modules run by machine_scan_service.scan)
# --------------------------------------------------------------------------- #
CATEGORY_SCANNERS: dict[str, set[str]] = {
    # 1. Hardware discovery
    "hardware": {"hardware", "performance"},
    # 2. Peripheral discovery
    "peripherals": {"hardware", "external_devices", "drivers"},
    "audio": {"hardware", "external_devices"},
    "webcam": {"hardware", "external_devices"},
    "printer": {"hardware", "external_devices"},
    "display": {"hardware", "external_devices"},
    "bluetooth": {"hardware", "external_devices"},
    "usb": {"hardware", "external_devices", "drivers"},
    "mouse": {"hardware", "external_devices"},
    "keyboard": {"hardware", "external_devices"},
    # 3. Software discovery
    "software": {"installed_software", "store_apps", "startup_programs"},
    "application": {"installed_software", "store_apps", "processes", "services", "app_health"},
    # 4. Operating system
    "windows": {"operating_system", "services", "event_logs", "windows_health"},
    "windows_update": {"operating_system", "services"},
    # 5. Security
    "security": {"security", "operating_system", "network", "processes", "startup_programs"},
    "account": {"security", "operating_system"},
    # 6-7. Process & service intelligence
    "process": {"processes", "performance"},
    "service": {"services", "processes"},
    "performance": {"hardware", "performance", "processes", "event_logs"},
    # 8. Event logs
    "event_logs": {"event_logs", "crash_analysis"},
    # 9. Storage intelligence
    "storage": {"storage_intelligence", "hardware"},
    # 10. Network intelligence
    "network": {"network"},
    "wifi": {"network"},
    # 11. Driver intelligence
    "driver": {"drivers"},
    # 12. Application health
    "app_health": {"app_health", "processes", "crash_analysis", "installed_software"},
    # 13. Windows health
    "windows_health": {"windows_health", "operating_system", "services", "crash_analysis"},
    # 14-15. Performance & reliability
    "reliability": {"crash_analysis", "event_logs", "windows_health", "services"},
    "crash": {"crash_analysis", "event_logs", "hardware", "performance", "operating_system"},
    "boot": {"performance", "operating_system", "crash_analysis", "startup_programs", "services"},
    # 16. User activity
    "user_activity": {"user_activity", "operating_system"},
    # 17. Change tracking
    "change": {"installed_software", "store_apps", "services", "startup_programs", "security", "operating_system"},
    # 18-19. Historical telemetry & incident reconstruction
    "telemetry": set(),
    "incident": {"event_logs", "crash_analysis", "processes", "services"},
    # 20. Predictive analytics
    "predictive": {"hardware", "crash_analysis", "storage_intelligence", "performance"},
    # 21-22. Dev & AI environment
    "dev_environment": {"dev_environment", "installed_software", "processes"},
    "ai_environment": {"ai_environment", "hardware", "processes"},
    # 23. Compliance
    "compliance": {"security", "operating_system"},
    # 24-25. Knowledge graph & executive health
    "knowledge_graph": {"processes", "services", "drivers", "crash_analysis"},
    "executive_health": {"hardware", "performance", "security", "operating_system",
                          "crash_analysis", "network", "storage_intelligence", "processes"},
    "battery": {"hardware", "performance"},
}

_DOMAIN_ALIASES: dict[str, str] = {
    "windows": "windows",
    "compliance": "compliance",
    "forensic": "executive_health",
}

_SCAN_ONLY_BASE: set[str] = {"hardware", "external_devices"}

SYNTHESIS_LAYERS = ("compliance", "knowledge_graph", "predictive", "health_report")


def scanners_for_domains(domains: list[str] | None) -> set[str] | None:
    """Legacy domain->scanner expansion (prefer ``build_scan_plan``)."""
    if domains is None:
        return None
    selected: set[str] = set()
    for d in domains:
        key = _DOMAIN_ALIASES.get(d, d)
        selected |= CATEGORY_SCANNERS.get(key, CATEGORY_SCANNERS.get(d, set()))
    return selected or _SCAN_ONLY_BASE.copy()


def investigation_scan_plan(message: str, profile) -> ScanPlan:
    """Intent-driven scan plan for a chat investigation."""
    return build_scan_plan(message, profile)


def investigation_domains(profile, message: str = "") -> list[str] | None:
    """Issue domains for hardware/external_devices sub-scoping."""
    plan = build_scan_plan(message, profile)
    if plan.full_scan:
        return None
    return plan.issue_domains


def all_category_names() -> list[str]:
    return sorted(CATEGORY_SCANNERS.keys())
