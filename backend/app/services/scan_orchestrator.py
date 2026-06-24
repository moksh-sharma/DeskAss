"""Intent-driven scan orchestration.

Pipeline:
  User question -> intent classification -> entity extraction ->
  required-data mapping -> scan selection -> (optional correlation escalation)

The assistant must NOT run every scanner for every chat question. Only explicit
full-system / audit / executive requests trigger an unrestricted scan.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Literal

from app.models.schemas import IssueProfile
from app.services.machine_scan_info import is_largest_file_question
from app.services.question_intent import (
    TROUBLE_RE,
    _LIST_INVENTORY_RE,
    _ON_NETWORK_RE,
    classify_query_intent,
    is_scan_only_intent,
)

ScanDepth = Literal["quick", "deep", "forensic"]

# Wall-clock budgets per scan level (enterprise SLA targets).
SCAN_DEPTH_BUDGET_SECONDS: dict[ScanDepth, float] = {
    "quick": 2.0,
    "deep": 10.0,
    "forensic": 60.0,
}

# Scanners skipped at quick depth to stay under budget.
QUICK_EXCLUDED_SCANNERS: frozenset[str] = frozenset({
    "event_logs",
    "crash_analysis",
    "windows_health",
    "user_activity",
    "knowledge_graph",
    "predictive",
    "compliance",
    "storage_intelligence",
})

# Spec intent aliases → internal intent keys.
INTENT_ALIASES: dict[str, str] = {
    "software_inventory": "software_analysis",
    "network_analysis": "network_troubleshooting",
    "device_analysis": "hardware_inventory",
    "full_system_scan": "executive_summary",
    "executive_summary": "full_system_scan",
}


def _list_drivers_intent(message: str) -> bool:
    from app.services.machine_scan_info import is_list_drivers_question
    return is_list_drivers_question(message)

# --------------------------------------------------------------------------- #
#  Enterprise intent labels (deterministic, regex + profile rules)
# --------------------------------------------------------------------------- #
ENTERPRISE_INTENTS = (
    "hardware_inventory",
    "hardware_health",
    "software_inventory",
    "software_analysis",
    "performance_analysis",
    "storage_analysis",
    "network_analysis",
    "network_discovery",
    "printer_discovery",
    "device_analysis",
    "application_troubleshooting",
    "network_troubleshooting",
    "printer_management",
    "driver_analysis",
    "security_analysis",
    "malware_investigation",
    "battery_analysis",
    "windows_health",
    "service_analysis",
    "event_log_analysis",
    "crash_analysis",
    "change_analysis",
    "incident_reconstruction",
    "root_cause_analysis",
    "prediction",
    "recommendation",
    "reporting",
    "full_system_scan",
    "executive_summary",
)

# Explicit phrases that require every scanner module.
FULL_SYSTEM_SCAN_RE = re.compile(
    r"\b("
    r"full\s+system\s+scan|"
    r"analyze\s+(?:the\s+)?entire\s+machine|"
    r"complete\s+machine\s+analysis|"
    r"deep\s+health\s+assessment|"
    r"enterprise\s+audit|"
    r"executive\s+health\s+report|"
    r"security\s+audit|"
    r"complete\s+endpoint\s+assessment|"
    r"comprehensive\s+(?:system\s+)?scan|"
    r"run\s+(?:a\s+)?full\s+scan|"
    r"scan\s+(?:the\s+)?entire\s+(?:pc|computer|machine|system)"
    r")\b",
    re.I,
)

# Intent detection patterns (order matters — first match wins for primary routing).
_INTENT_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (FULL_SYSTEM_SCAN_RE, "full_system_scan"),
    (re.compile(r"\b(malware|ransomware|trojan|virus|rootkit|spyware|infected)\b", re.I), "malware_investigation"),
    (re.compile(r"\b(incident\s+reconstruction|post[\s-]?mortem|what\s+occurred|sequence\s+of\s+events|build\s+a\s+timeline)\b", re.I), "incident_reconstruction"),
    (re.compile(r"\b(root[\s-]?cause|find\s+the\s+cause|most\s+likely\s+cause)\b", re.I), "root_cause_analysis"),
    (re.compile(r"\b(battery.{0,30}drain|draining.{0,30}battery|battery\s+life)\b", re.I), "battery_analysis"),
    (re.compile(
        r"\b(?:what|which)\s+printers?\s+(?:are\s+)?(?:available|on|in)\b|"
        r"printers?.{0,20}(?:on|in)\s+(?:my|the)\s+network|"
        r"discovered\s+printers?\b",
        re.I,
    ), "printer_discovery"),
    (re.compile(r"\b(list|show|enumerate).{0,20}drivers?\b|\bdriver\s+inventory\b", re.I), "driver_analysis"),
    (re.compile(r"\b(driver|drivers).{0,40}(?:fail|error|problem|broken)|(?:fail|error|problem).{0,40}(?:driver|drivers)\b", re.I), "driver_analysis"),
    (re.compile(r"\b(event\s+log|event\s+viewer|windows\s+events?)\b", re.I), "event_log_analysis"),
    (re.compile(r"\b(blue\s+screen|bsod|crash(?:es|ed|ing)?|app\s+crash)\b", re.I), "crash_analysis"),
    (re.compile(r"\b(what\s+changed|change\s+tracking|installed\s+recently|removed\s+recently)\b", re.I), "change_analysis"),
    (re.compile(r"\b(windows\s+health|sfc|dism|component\s+store|winre)\b", re.I), "windows_health"),
    (re.compile(r"\b(service|services).{0,30}(?:fail|stop|stuck|not\s+running)\b", re.I), "service_analysis"),
    (re.compile(r"\b(list|show).{0,20}services?\b", re.I), "service_analysis"),
    (re.compile(r"\b(antivirus|defender|firewall|bitlocker|malware|security\s+risk|how\s+secure)\b", re.I), "security_analysis"),
    (re.compile(r"\b(disk\s+full|low\s+space|storage|free\s+up\s+space|largest\s+files?|cleanup)\b", re.I), "storage_analysis"),
    (re.compile(
        r"\b(?:which|what)\s+file|biggest\s+file|largest\s+file|"
        r"taking\s+(?:the\s+)?(?:most|more)\s+space|"
        r"what(?:'s| is)\s+using\s+(?:the\s+)?(?:most|more)\s+space\b",
        re.I,
    ), "storage_analysis"),
    (re.compile(r"\b(installed\s+software|what\s+software|list\s+apps?|applications?\s+installed|software\s+inventory)\b", re.I), "software_inventory"),
    (re.compile(
        r"\b((?:chrome|firefox|edge|teams|zoom|discord|outlook).{0,25}(?:slow|lag|freeze|hang|sluggish)|"
        r"(?:slow|lag|freeze|hang|sluggish).{0,25}(?:chrome|firefox|edge|teams|zoom|discord|outlook))\b",
        re.I,
    ), "application_troubleshooting"),
    (re.compile(r"\b(wifi|wi-?fi|dns|ip\s+address|network\s+adapter|internet)\b", re.I), "network_analysis"),
    (re.compile(r"\b(?:printer\s+queue|won'?t\s+print|print\s+queue|won't\s+print)\b", re.I), "printer_management"),
    (re.compile(r"\bprinter\b(?!s?\s+(?:are|is)\s+(?:available|on|in))", re.I), "printer_management"),
    (re.compile(r"\b(slow|lag|freeze|hang|sluggish|high\s+cpu|high\s+ram|memory\s+usage|why\s+is\s+my\s+(?:pc|laptop|computer)\s+slow)\b", re.I), "performance_analysis"),
    (re.compile(r"\b(usb|bluetooth|webcam|camera|audio|monitor|keyboard|mouse|devices?)\b", re.I), "device_analysis"),
    (re.compile(r"\b(cpu|processor|ram|memory|gpu|graphics\s+card|motherboard)\b", re.I), "hardware_inventory"),
]

# Minimal scanner sets per intent — only what is required to answer accurately.
INTENT_SCANNERS: dict[str, set[str]] = {
    "hardware_inventory": {"hardware"},
    "hardware_health": {"hardware", "performance"},
    "device_analysis": {"hardware", "external_devices", "drivers"},
    "storage_analysis": {"storage_intelligence", "hardware"},
    "software_inventory": {"installed_software", "store_apps"},
    "software_analysis": {"installed_software", "store_apps"},
    "performance_analysis": {"performance", "processes", "startup_programs"},
    "application_troubleshooting": {"processes", "app_health", "crash_analysis", "performance"},
    "network_analysis": {"network"},
    "network_troubleshooting": {"network"},
    "network_discovery": {"network", "external_devices"},
    "printer_discovery": {"network", "external_devices"},
    "printer_management": {"external_devices"},
    "driver_analysis": {"drivers"},
    "security_analysis": {"security", "operating_system"},
    "malware_investigation": {"security", "processes", "event_logs"},
    "battery_analysis": {"hardware", "performance", "processes"},
    "windows_health": {"windows_health", "operating_system", "services"},
    "service_analysis": {"services", "processes"},
    "event_log_analysis": {"event_logs"},
    "crash_analysis": {"crash_analysis", "event_logs"},
    "change_analysis": {"installed_software", "store_apps", "services", "startup_programs"},
    "incident_reconstruction": {"event_logs", "crash_analysis", "processes", "services"},
    "root_cause_analysis": {"event_logs", "crash_analysis", "processes", "services", "performance"},
    "prediction": {"hardware", "crash_analysis", "storage_intelligence", "performance"},
    "recommendation": {"hardware", "performance", "security", "operating_system"},
    "reporting": {"hardware", "performance", "security", "operating_system", "crash_analysis", "network"},
    "full_system_scan": set(),
    "executive_summary": set(),  # full scan — scanners=None
}

# Issue-parser domain -> default enterprise intent when no pattern matched.
_DOMAIN_DEFAULT_INTENT: dict[str, str] = {
    "hardware": "hardware_inventory",
    "storage": "storage_analysis",
    "software": "software_analysis",
    "application": "application_troubleshooting",
    "performance": "performance_analysis",
    "network": "network_troubleshooting",
    "wifi": "network_troubleshooting",
    "printer": "printer_management",
    "driver": "driver_analysis",
    "security": "security_analysis",
    "battery": "battery_analysis",
    "windows": "windows_health",
    "windows_health": "windows_health",
    "service": "service_analysis",
    "process": "performance_analysis",
    "event_logs": "event_log_analysis",
    "crash": "crash_analysis",
    "change": "change_analysis",
    "incident": "incident_reconstruction",
    "predictive": "prediction",
    "compliance": "security_analysis",
    "executive_health": "executive_summary",
    "audio": "hardware_inventory",
    "bluetooth": "hardware_inventory",
    "usb": "hardware_inventory",
    "webcam": "hardware_inventory",
    "display": "hardware_inventory",
    "mouse": "hardware_inventory",
    "keyboard": "hardware_inventory",
    "dev_environment": "software_analysis",
    "ai_environment": "software_analysis",
    "boot": "performance_analysis",
    "windows_update": "windows_health",
    "account": "security_analysis",
    "reliability": "crash_analysis",
    "user_activity": "change_analysis",
    "knowledge_graph": "reporting",
}

_SERVICE_NAMES_RE = re.compile(
    r"\b(spooler|wuauserv|dns|dhcp|winrm|bits|cryptsvc|eventlog|lanmanserver|"
    r"lanmanworkstation|wsearch|themes|audiosrv|bthserv)\b",
    re.I,
)
_ERROR_CODE_RE = re.compile(r"\b(?:code\s+)?(\d{1,2}|0x[0-9a-f]+)\b", re.I)
_EVENT_ID_RE = re.compile(r"\bevent\s+(?:id\s+)?(\d+)\b", re.I)
_HW_COMPONENT_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("cpu", re.compile(r"\b(cpu|processor)\b", re.I)),
    ("ram", re.compile(r"\b(ram|memory)\b", re.I)),
    ("disk", re.compile(r"\b(disk|ssd|hdd|drive|storage)\b", re.I)),
    ("battery", re.compile(r"\bbattery\b", re.I)),
    ("gpu", re.compile(r"\b(gpu|graphics\s+card|video\s+card)\b", re.I)),
    ("printer", re.compile(r"\bprinter", re.I)),
    ("network", re.compile(r"\b(network|lan|wifi|wi-?fi)\b", re.I)),
]


@dataclass
class ExtractedEntities:
    """Structured entities extracted from the user question."""

    applications: list[str] = field(default_factory=list)
    devices: list[str] = field(default_factory=list)
    hardware_components: list[str] = field(default_factory=list)
    services: list[str] = field(default_factory=list)
    drivers: list[str] = field(default_factory=list)
    network_devices: list[str] = field(default_factory=list)
    printers: list[str] = field(default_factory=list)
    error_codes: list[str] = field(default_factory=list)
    event_ids: list[str] = field(default_factory=list)
    windows_components: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, list[str]]:
        return {
            "applications": self.applications,
            "devices": self.devices,
            "hardware_components": self.hardware_components,
            "services": self.services,
            "drivers": self.drivers,
            "network_devices": self.network_devices,
            "printers": self.printers,
            "error_codes": self.error_codes,
            "event_ids": self.event_ids,
            "windows_components": self.windows_components,
        }


@dataclass
class ScanPlan:
    """Selected scanners and depth for one investigation pass."""

    intents: list[str]
    entities: ExtractedEntities
    scanners: set[str] | None  # None = unrestricted (full system scan)
    issue_domains: list[str] | None
    depth: ScanDepth
    run_deep_storage: bool
    full_scan: bool
    reason: str = ""

    def scanner_list(self) -> list[str]:
        if self.scanners is None:
            return []
        return sorted(self.scanners)


def normalize_intent(intent: str) -> str:
    """Map spec-facing intent labels to internal scanner routing keys."""
    return INTENT_ALIASES.get(intent, intent)


def apply_depth_to_scanners(scanners: set[str], depth: ScanDepth) -> set[str]:
    """Trim scanner set for quick-depth SLA (<2s target)."""
    if depth == "quick":
        trimmed = scanners - set(QUICK_EXCLUDED_SCANNERS)
        return trimmed or {"performance"}
    return scanners


def is_full_system_scan_request(message: str) -> bool:
    return bool(FULL_SYSTEM_SCAN_RE.search(message or ""))


def extract_entities(message: str, profile: IssueProfile) -> ExtractedEntities:
    """Pull named entities from the question and parsed profile."""
    text = message or ""
    entities = ExtractedEntities(applications=list(profile.apps or []))

    for comp, pat in _HW_COMPONENT_PATTERNS:
        if pat.search(text) and comp not in entities.hardware_components:
            entities.hardware_components.append(comp)

    if re.search(r"\bprinter", text, re.I):
        entities.printers.append("printer")
    if _ON_NETWORK_RE.search(text):
        entities.network_devices.append("network")

    for svc in _SERVICE_NAMES_RE.findall(text):
        if svc.lower() not in entities.services:
            entities.services.append(svc.lower())

    if re.search(r"\bdriver", text, re.I):
        entities.drivers.append("drivers")

    for code in _ERROR_CODE_RE.findall(text):
        if code not in entities.error_codes:
            entities.error_codes.append(code)
    for eid in _EVENT_ID_RE.findall(text):
        if eid not in entities.event_ids:
            entities.event_ids.append(eid)

    for comp in ("windows update", "defender", "bitlocker", "task scheduler", "registry"):
        if comp in text.lower():
            entities.windows_components.append(comp)

    # Symptom tags become device-context hints.
    for sym in profile.symptoms or []:
        if sym not in entities.devices:
            entities.devices.append(sym)

    return entities


def classify_enterprise_intents(message: str, profile: IssueProfile) -> list[str]:
    """Map a question to one or more enterprise intent labels."""
    text = message or ""

    if is_full_system_scan_request(text) or profile.analysis_mode in ("executive", "forensic", "reasoning"):
        return ["full_system_scan"]

    if profile.analysis_mode == "predictive":
        return ["prediction"]

    intents: list[str] = []
    for pat, intent in _INTENT_PATTERNS:
        if pat.search(text) and intent not in intents:
            intents.append(intent)

    # Printer discovery vs local printer troubleshooting.
    if "printer_discovery" in intents and re.search(r"\b(available|discovered|on\s+(?:my|the)\s+network)\b", text, re.I):
        return ["printer_discovery"]

    if (
        "network_discovery" not in intents
        and "printer_management" in intents
        and (_ON_NETWORK_RE.search(text) or re.search(r"\bavailable\b", text, re.I))
    ):
        intents.insert(0, "printer_discovery")

    # Explicit driver inventory beats incidental app-name token matches.
    if _list_drivers_intent(text):
        return ["driver_analysis"]

    # Named application with slowness / failure -> application troubleshooting only.
    if profile.apps and (
        TROUBLE_RE.search(text)
        or re.search(r"\bslow\b", text, re.I)
        or "application" in (profile.domains or [])
    ):
        if "application_troubleshooting" not in intents:
            intents.insert(0, "application_troubleshooting")
        return ["application_troubleshooting"]

    # Domain fallback from issue parser.
    primary = profile.primary_domain
    if primary:
        default = _DOMAIN_DEFAULT_INTENT.get(primary)
        if default and default not in intents:
            intents.append(default)
    for domain in profile.domains or []:
        default = _DOMAIN_DEFAULT_INTENT.get(domain)
        if default and default not in intents:
            intents.append(default)

    if not intents:
        if is_scan_only_intent(profile.query_intent):
            intents.append("hardware_inventory")
        else:
            intents.append("root_cause_analysis")

    # Inventory/list questions: one primary intent only.
    if profile.query_intent == "inventory" and _LIST_INVENTORY_RE.search(text) and intents:
        primary_intent = intents[0]
        if profile.primary_domain:
            mapped = _DOMAIN_DEFAULT_INTENT.get(profile.primary_domain)
            if mapped and mapped in intents:
                primary_intent = mapped
        return [primary_intent]

    return intents


def _depth_for_intents(intents: list[str], profile: IssueProfile, message: str) -> ScanDepth:
    if profile.analysis_mode in ("forensic", "reasoning") or "incident_reconstruction" in intents:
        return "forensic"
    if profile.analysis_mode == "predictive" or "root_cause_analysis" in intents:
        return "deep"
    if TROUBLE_RE.search(message or "") and not is_scan_only_intent(profile.query_intent):
        if any(i in intents for i in ("performance_analysis", "application_troubleshooting", "crash_analysis")):
            return "deep"
    if is_scan_only_intent(profile.query_intent):
        return "quick"
    return "deep"


def _scanners_for_intents(
    intents: list[str],
    entities: ExtractedEntities,
    profile: IssueProfile,
    depth: ScanDepth,
) -> set[str] | None:
    if "executive_summary" in intents or "full_system_scan" in intents:
        return None

    selected: set[str] = set()
    for intent in intents:
        key = normalize_intent(intent)
        selected |= INTENT_SCANNERS.get(key, INTENT_SCANNERS.get(intent, set()))

    # Application-specific troubleshooting: skip broad software inventory.
    if "application_troubleshooting" in intents and entities.applications:
        selected -= {"installed_software", "store_apps", "startup_programs"}

    # Driver list/inventory never needs storage, printers, or network discovery.
    if intents == ["driver_analysis"] or (
        len(intents) == 1 and intents[0] == "driver_analysis"
    ):
        selected = {"drivers"}

    # Printer/network discovery: never pull security or storage.
    if intents == ["network_discovery"] or (
        "network_discovery" in intents and "printer_management" in intents
    ):
        selected &= {"network", "external_devices"}

    # Performance on desktop-style questions: skip battery-heavy paths when not asked.
    if (
        "performance_analysis" in intents
        and "battery_analysis" not in intents
        and "battery" not in entities.hardware_components
    ):
        pass  # hardware.scan still runs cpu/ram via performance domain — acceptable cost.

    # Deep / forensic passes add diagnostic layers only when needed.
    if depth == "deep":
        if "performance_analysis" in intents:
            selected.add("event_logs")
        if "application_troubleshooting" in intents:
            selected.add("event_logs")
        if "driver_analysis" in intents and TROUBLE_RE.search(message or ""):
            selected.add("event_logs")
    if depth == "forensic":
        selected |= {"event_logs", "crash_analysis", "services"}

    # Always need inventory snapshot inputs when app health runs.
    if "app_health" in selected:
        selected.add("installed_software")

    selected = apply_depth_to_scanners(selected, depth)
    return selected or {"hardware"}


def _issue_domains_for_plan(
    profile: IssueProfile,
    intents: list[str],
    entities: ExtractedEntities,
) -> list[str] | None:
    """Domains passed to hardware/external_devices sub-scoping."""
    if profile.primary_domain:
        base = [profile.primary_domain]
    elif profile.domains:
        base = list(profile.domains[:1])
    else:
        base = []

    if "application_troubleshooting" in intents and profile.apps:
        if "application" not in base:
            base = ["application", *base]

    if "network_discovery" in intents and "printer" not in base:
        base = ["printer", "network", *base]

    if "driver_analysis" in intents and "driver" not in base:
        base = ["driver", *base]

    # Deduplicate preserving order.
    seen: set[str] = set()
    ordered: list[str] = []
    for d in base:
        if d and d not in seen:
            seen.add(d)
            ordered.append(d)
    return ordered or None


def build_scan_plan(message: str, profile: IssueProfile) -> ScanPlan:
    """Produce the minimal scan plan for a user question."""
    entities = extract_entities(message, profile)
    intents = classify_enterprise_intents(message, profile)
    depth = _depth_for_intents(intents, profile, message)
    full_scan = (
        "executive_summary" in intents
        or "full_system_scan" in intents
    ) and (
        is_full_system_scan_request(message)
        or profile.analysis_mode in ("executive", "forensic", "reasoning")
        or not profile.domains
    )

    if full_scan:
        return ScanPlan(
            intents=intents,
            entities=entities,
            scanners=None,
            issue_domains=None,
            depth="forensic",
            run_deep_storage=bool(
                profile.target_drive
                or "storage" in (profile.domains or [])
                or re.search(r"\bdisk|storage|space|drive\b", message or "", re.I)
            ),
            full_scan=True,
            reason="explicit full-system or holistic analysis request",
        )

    scanners = _scanners_for_intents(intents, entities, profile, depth)
    issue_domains = _issue_domains_for_plan(profile, intents, entities)

    run_deep = False
    if "storage_analysis" in intents or profile.target_drive:
        run_deep = depth != "quick"
    if (
        is_largest_file_question(message)
        or re.search(
            r"\blargest\s+files?|deep\s+storage|what\s+can\s+i\s+delete|"
            r"taking\s+(?:the\s+)?(?:most|more)\s+space|biggest\s+file\b",
            message or "",
            re.I,
        )
    ):
        run_deep = True

    reason_bits = [f"intents={','.join(intents)}", f"depth={depth}"]
    if entities.applications:
        reason_bits.append(f"app={entities.applications[0]}")
    return ScanPlan(
        intents=intents,
        entities=entities,
        scanners=scanners,
        issue_domains=issue_domains,
        depth=depth,
        run_deep_storage=run_deep,
        full_scan=False,
        reason="; ".join(reason_bits),
    )


def correlate_escalation(
    plan: ScanPlan,
    report: dict[str, Any],
    message: str = "",
) -> ScanPlan | None:
    """Return an escalated plan when primary evidence is insufficient.

    Implements the correlation rule: add secondary scans only when findings
  require them — never blanket-expand to unrelated domains.
    """
    if plan.full_scan or plan.depth == "forensic":
        return None

    extra: set[str] = set(plan.scanners or [])
    run_deep = plan.run_deep_storage
    escalated = False

    hw = report.get("hardware") or {}
    sw = report.get("software") or {}
    perf = hw.get("performance") or {}
    cpu_pct = perf.get("cpu_usage_pct") or perf.get("current_usage_pct")
    if cpu_pct is None:
        cpu = hw.get("cpu") or {}
        cpu_pct = cpu.get("current_usage_pct")

    procs = (sw.get("running_processes") or {}).get("top_cpu") or []
    top_cpu = (procs[0].get("cpu_pct") if procs else None) or 0

    # Performance: high CPU with a clear top consumer — no escalation.
    if "performance_analysis" in plan.intents and cpu_pct is not None:
        if cpu_pct >= 85 and top_cpu >= 35:
            return None
        if cpu_pct >= 70 and "event_logs" not in extra:
            extra.add("event_logs")
            escalated = True

    # Disk problems -> storage / SMART follow-up.
    disks = hw.get("disks") or hw.get("storage") or {}
    disk_list = disks if isinstance(disks, list) else (disks.get("disks") or [])
    disk_health = hw.get("disk_health") or {}
    if isinstance(disk_health, dict):
        disk_list = list(disk_list) + list(disk_health.get("disks") or [])

    disk_warning = any(
        (d.get("health_status") or d.get("health") or "").lower() in ("warning", "critical", "bad")
        for d in disk_list
        if isinstance(d, dict)
    )
    if disk_warning and "storage_intelligence" not in extra:
        extra.add("storage_intelligence")
        extra.add("hardware")
        run_deep = True
        escalated = True

    crash = sw.get("crash_analysis") or {}
    if (
        "performance_analysis" in plan.intents
        and (crash.get("bsod_events") or crash.get("application_crashes"))
        and "crash_analysis" not in extra
    ):
        extra.add("crash_analysis")
        escalated = True

    if not escalated:
        return None

    new_domains = list(plan.issue_domains or [])
    if "storage_analysis" not in plan.intents and run_deep and "storage" not in new_domains:
        new_domains.append("storage")

    return ScanPlan(
        intents=plan.intents,
        entities=plan.entities,
        scanners=extra,
        issue_domains=new_domains or plan.issue_domains,
        depth="deep",
        run_deep_storage=run_deep,
        full_scan=False,
        reason=f"correlation escalation from {plan.reason}",
    )
