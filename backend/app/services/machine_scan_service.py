"""Orchestrates the comprehensive machine scan.

Runs every independent scanner concurrently (each on a worker thread so the
blocking PowerShell/psutil calls don't stall the event loop), assembles the
structured report matching the requested data structure, and computes a health
score. The executive summary is generated deterministically from the scan facts.
"""
from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from typing import Any, Optional

from app.core.config import get_settings
from app.core.logging import get_logger
from app.services.storage_intelligence_service import StorageIntelligenceService
from app.services.scan_framework import scanners_for_domains
from app.services.scanners import (
    ai_environment,
    app_health,
    compliance,
    crash,
    dev_environment,
    drivers,
    event_logs,
    external_devices,
    hardware,
    health,
    knowledge_graph,
    network,
    operating_system,
    performance,
    predictive,
    processes,
    security,
    services_scan,
    software,
    startup,
    store_apps,
    user_activity,
    windows_health,
)
from app.services.system_inventory import SystemInventory

logger = get_logger(__name__)

# Domains whose answers benefit from the heavy deep storage tree walk.
_DEEP_STORAGE_DOMAINS = {"storage"}

# Short-lived cache for scoped chat investigation scans (domains -> report).
_scoped_scan_cache: dict[tuple[Any, ...], tuple[float, dict[str, Any]]] = {}


class MachineScanService:
    """Builds a full, structured snapshot of the machine for diagnosis."""

    def __init__(
        self,
        inventory: Optional[SystemInventory] = None,
        storage: Optional[StorageIntelligenceService] = None,
    ) -> None:
        self._inventory = inventory or SystemInventory()
        self._storage = storage or StorageIntelligenceService()

    @staticmethod
    def _select_scanners(domains: Optional[list[str]]) -> Optional[set[str]]:
        """Return the scanner keys needed for ``domains`` (None = run all)."""
        return scanners_for_domains(domains)

    async def scan(
        self,
        *,
        ocr_results: Optional[dict] = None,
        rag_context: Optional[dict] = None,
        target_drive: str | None = None,
        domains: Optional[list[str]] = None,
        scanner_keys: Optional[set[str]] = None,
        run_deep_storage: Optional[bool] = None,
        snapshot: Any = None,
        storage_tree_budget: Optional[float] = None,
        storage_duplicate_budget: Optional[float] = None,
        scan_depth: str | None = None,
    ) -> dict[str, Any]:
        """Run the machine scan.

        ``domains`` scopes the work to only the scanners an issue needs (chat
        troubleshooter). When ``None``, every scanner runs (Full System Scan).
        ``run_deep_storage`` overrides the heavy storage tree walk; when ``None``
        full scans follow ``storage_deep_on_full_scan``; scoped scans only run
        deep storage for storage-domain issues.
        ``snapshot`` lets a caller (the investigation service) reuse an inventory
        snapshot it already collected, avoiding a second expensive enumeration.
        """
        settings = get_settings()
        scoped = domains is not None or scanner_keys is not None

        # Reuse a recent scoped scan for back-to-back chat questions on the same topic.
        cache_ttl = settings.investigation_scan_cache_seconds
        cache_key: tuple[Any, ...] | None = None
        if scoped and cache_ttl > 0:
            cache_key = (
                tuple(sorted(domains or [])),
                tuple(sorted(scanner_keys or [])),
                target_drive or "",
                bool(run_deep_storage) if run_deep_storage is not None else "auto",
            )
            cached = _scoped_scan_cache.get(cache_key)
            if cached and (time.monotonic() - cached[0]) < cache_ttl:
                logger.info("Reusing cached scoped scan (age %.1fs, domains=%s)", time.monotonic() - cached[0], domains)
                return dict(cached[1])

        start = time.perf_counter()

        # Decide the scanner subset for this run.
        if scanner_keys is not None:
            selected_keys = set(scanner_keys)
        else:
            selected_keys = self._select_scanners(domains)

        # Deep storage: scoped scans only when storage-related; full scan follows setting.
        if run_deep_storage is None:
            if scoped:
                run_deep_storage = bool(
                    target_drive
                    or any(d in _DEEP_STORAGE_DOMAINS for d in (domains or []))
                )
            else:
                run_deep_storage = settings.storage_deep_on_full_scan

        tree_budget = (
            storage_tree_budget
            if storage_tree_budget is not None
            else settings.storage_deep_tree_budget_seconds
        )
        dup_budget = (
            storage_duplicate_budget
            if storage_duplicate_budget is not None
            else settings.storage_deep_duplicate_budget_seconds
        )

        # Reuse a caller-supplied snapshot when present; only enumerate inventory
        # if a scanner that needs it will actually run.
        needs_snapshot = selected_keys is None or bool(
            selected_keys & {"installed_software", "services", "app_health"}
        )
        if snapshot is None and needs_snapshot:
            snapshot = await asyncio.to_thread(self._inventory.snapshot)

        async def _deep_storage() -> dict[str, Any] | None:
            if not (settings.storage_deep_enabled and run_deep_storage):
                return None
            try:
                return await asyncio.to_thread(
                    self._storage.deep_scan,
                    tree_budget=tree_budget,
                    duplicate_budget=dup_budget,
                    target_drive=target_drive,
                )
            except Exception as exc:
                logger.warning("Deep storage scan failed: %s", exc)
                return {"error": str(exc), "available": False}

        deep_task = asyncio.create_task(_deep_storage())

        # Scanners that need the installed-app/process inventory.
        inv_scanners = {
            "installed_software": (software.scan, (snapshot,)),
            "services": (services_scan.scan, (snapshot,)),
            "app_health": (lambda inv=snapshot: app_health.scan(inv), (snapshot,)),
        }
        # Standalone scanners. Scoped chat investigations pass ``domains`` so
        # hardware/external_devices only run the probes the issue needs.
        plain_scanners = {
            "hardware": (lambda d=domains: hardware.scan(d), ()),
            "external_devices": (lambda d=domains: external_devices.scan(d), ()),
            "drivers": (drivers.scan, ()),
            "operating_system": (operating_system.scan, ()),
            "performance": (performance.scan, ()),
            "processes": (processes.scan, ()),
            "startup_programs": (startup.scan, ()),
            "event_logs": (event_logs.scan, ()),
            "network": (network.scan, ()),
            "security": (security.scan, ()),
            "crash_analysis": (crash.scan, ()),
            "windows_health": (windows_health.scan, ()),
            "user_activity": (user_activity.scan, ()),
            "store_apps": (store_apps.scan, ()),
            "dev_environment": (dev_environment.scan, ()),
            "ai_environment": (ai_environment.scan, ()),
            # Fast storage intelligence (~12s) - recoverable space, cleanup targets, health.
            "storage_intelligence": (self._storage.quick_scan, ()),
        }

        all_scanners = {**plain_scanners, **inv_scanners}
        if selected_keys is not None:
            all_scanners = {k: v for k, v in all_scanners.items() if k in selected_keys}
        keys = list(all_scanners.keys())
        if scoped:
            logger.info(
                "Scoped scan domains=%s scanners=%s deep_storage=%s",
                domains, sorted(selected_keys or []), run_deep_storage,
            )
        results = await asyncio.gather(
            *(asyncio.to_thread(fn, *args) for fn, args in all_scanners.values()),
            return_exceptions=True,
        )

        sections: dict[str, Any] = {}
        for key, result in zip(keys, results):
            if isinstance(result, Exception):
                logger.warning("Scanner '%s' raised: %s", key, result)
                sections[key] = {"error": str(result), "available": False}
            else:
                sections[key] = result

        # Two top-level buckets only: hardware and software.
        hardware_section = sections.get("hardware", {}) or {}
        hardware_bucket = {
            **hardware_section,
            "performance": sections.get("performance", {}),
            "external_devices": sections.get("external_devices", {}),
            "drivers": sections.get("drivers", {}),
        }

        installed = sections.get("installed_software", {}) or {}
        software_bucket = {
            "operating_system": sections.get("operating_system", {}),
            "installed_applications": installed.get("applications", []),
            "installed_count": installed.get("total_count", 0),
            "by_category": installed.get("by_category", {}),
            "category_counts": installed.get("category_counts", {}),
            "recently_installed_30d": installed.get("recently_installed_30d", []),
            "publishers": installed.get("publishers", {}),
            "remote_access_tools": installed.get("remote_access_tools", []),
            "running_processes": sections.get("processes", {}),
            "services": sections.get("services", {}),
            "startup_programs": sections.get("startup_programs", {}),
            "security": sections.get("security", {}),
            "crash_analysis": sections.get("crash_analysis", {}),
            "event_logs": sections.get("event_logs", {}),
            "network": sections.get("network", {}),
            "storage_intelligence": sections.get("storage_intelligence", {}),
        }
        # New enterprise sections (only present when their scanner ran).
        if "windows_health" in sections:
            software_bucket["windows_health"] = sections.get("windows_health", {})
        if "user_activity" in sections:
            software_bucket["user_activity"] = sections.get("user_activity", {})
        if "store_apps" in sections:
            store = sections.get("store_apps", {}) or {}
            software_bucket["store_applications"] = store.get("applications", [])
            software_bucket["store_application_count"] = store.get("total_count", 0)
        if "dev_environment" in sections:
            software_bucket["dev_environment"] = sections.get("dev_environment", {})
        if "ai_environment" in sections:
            software_bucket["ai_environment"] = sections.get("ai_environment", {})
        if "app_health" in sections:
            software_bucket["app_health"] = sections.get("app_health", {})

        deep_storage = await deep_task
        if deep_storage and not deep_storage.get("error"):
            software_bucket["storage_deep"] = deep_storage
            logger.info(
                "Deep storage scan complete in %.1fs - %d top files, ~%.1f GB recoverable",
                deep_storage.get("scan_duration_seconds") or 0,
                len((deep_storage.get("tree") or {}).get("top_files") or []),
                (deep_storage.get("cleanup") or {}).get("total_potential_gb") or 0,
            )
        elif deep_storage and deep_storage.get("error"):
            software_bucket["storage_deep"] = deep_storage

        # --- Synthesis layers (deterministic analysis over the collected facts) ---
        # Compliance must be computed before the health report so its score can
        # feed the executive scorecard. Each runs only when its inputs are present.
        synth_input = dict(sections)
        synth_input["_hardware_bucket"] = hardware_bucket
        synth_input["_software_bucket"] = software_bucket

        if {"security", "operating_system"} & set(sections):
            comp = compliance.build(synth_input)
            sections["compliance"] = comp
            software_bucket["compliance"] = comp
        if not scoped or {"processes", "services", "drivers", "crash_analysis"} & set(sections):
            kg = knowledge_graph.build(synth_input)
            software_bucket["knowledge_graph"] = kg
        if not scoped or {"crash_analysis", "hardware", "storage_intelligence"} & set(sections):
            software_bucket["predictive"] = predictive.build(synth_input)

        report: dict[str, Any] = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "hardware": hardware_bucket,
            "software": software_bucket,
            "ocr_results": ocr_results or {},
            "rag_context": rag_context or {},
        }
        report["health_report"] = health.build_health_report(sections)

        # LLM summary is generated on demand via generate_summary() / the
        # /full-scan/summary endpoint so the scan itself stays fast.
        report["ai_summary"] = {
            "summary": "",
            "prioritized_actions": [],
            "generated_by_llm": False,
            "model": "",
        }

        elapsed = time.perf_counter() - start
        report["scan_duration_seconds"] = round(elapsed, 1)
        report["scan_scope"] = "scoped" if scoped else "full"
        if scan_depth:
            from app.services.scan_orchestrator import SCAN_DEPTH_BUDGET_SECONDS
            report["scan_depth"] = scan_depth
            report["scan_depth_budget_seconds"] = SCAN_DEPTH_BUDGET_SECONDS.get(scan_depth)  # type: ignore[arg-type]
        logger.info(
            "%s machine scan complete in %.1fs - health %s (%d/100)",
            "Scoped" if scoped else "Full",
            elapsed,
            report["health_report"]["overall_status"],
            report["health_report"]["overall_score"],
        )
        if cache_key is not None and cache_ttl > 0:
            _scoped_scan_cache[cache_key] = (time.monotonic(), dict(report))
        return report

    @staticmethod
    def merge_reports(base: dict[str, Any], extra: dict[str, Any]) -> dict[str, Any]:
        """Merge a follow-up scoped scan into an earlier report (correlation escalation)."""
        if not extra:
            return base
        merged = dict(base)
        for key in ("hardware", "software"):
            bucket = dict(merged.get(key) or {})
            add = extra.get(key) or {}
            for sub_key, value in add.items():
                if value and (sub_key not in bucket or not bucket.get(sub_key)):
                    bucket[sub_key] = value
            merged[key] = bucket
        if extra.get("health_report") and not merged.get("health_report"):
            merged["health_report"] = extra["health_report"]
        merged["scan_duration_seconds"] = round(
            float(merged.get("scan_duration_seconds") or 0)
            + float(extra.get("scan_duration_seconds") or 0),
            1,
        )
        return merged

    # ------------------------------------------------------------------ #
    #  On-demand executive summary (deterministic, no AI model)
    # ------------------------------------------------------------------ #
    async def generate_summary(self, report: dict[str, Any]) -> dict[str, Any]:
        """Build a grounded executive summary directly from the scan facts."""
        return self._deterministic_summary(report)

    @staticmethod
    def _deterministic_summary(report: dict[str, Any]) -> dict[str, Any]:
        """Assemble a multi-sentence health summary + prioritised actions from facts."""
        health = report.get("health_report", {}) or {}
        hw = report.get("hardware", {}) or {}
        sw = report.get("software", {}) or {}
        cpu = hw.get("cpu") or {}
        ram = hw.get("ram") or {}
        sec = sw.get("security") or {}
        crash = sw.get("crash_analysis") or {}
        os_ = sw.get("operating_system") or {}

        score = health.get("overall_score", 0)
        status = health.get("overall_status", "Unknown")
        sentences: list[str] = [f"Overall health is {score}/100 ({status})."]

        cpu_pct = cpu.get("current_usage_pct")
        ram_pct = ram.get("utilization_pct")
        if cpu_pct is not None or ram_pct is not None:
            parts = []
            if cpu_pct is not None:
                parts.append(f"CPU at {cpu_pct}%")
            if ram_pct is not None:
                parts.append(f"RAM at {ram_pct}% of {ram.get('total_gb', '?')} GB")
            sentences.append("Resource use: " + ", ".join(parts) + ".")

        drives = (hw.get("storage") or {}).get("logical_drives", []) or []
        tight = [d for d in drives if (d.get("usage_pct") or 0) >= 85]
        if tight:
            d = tight[0]
            sentences.append(
                f"Drive {d.get('drive')} is {d.get('usage_pct')}% full "
                f"({d.get('free_gb')} GB free)."
            )

        if sec:
            protected = sec.get("protection_active")
            fw = (sec.get("firewall") or {}).get("all_enabled")
            posture = "active" if protected else "needs attention"
            fw_txt = "on" if fw else "partially off"
            sentences.append(f"Security protection is {posture}; firewall is {fw_txt}.")

        crash_sum = crash.get("summary") or {}
        bsod = crash_sum.get("bsod_count") or len(crash.get("bsod_events") or [])
        app_c = crash_sum.get("app_crash_count") or len(crash.get("application_crashes") or [])
        if bsod or app_c:
            sentences.append(
                f"Stability: {bsod} blue-screen and {app_c} app-crash event(s) recorded."
            )
        if (os_.get("pending_reboot") or {}).get("required"):
            sentences.append("A system reboot is pending.")

        actions = list(health.get("recommended_actions", []) or [])
        if not actions:
            actions = ["No critical actions required - keep Windows and drivers up to date."]

        return {
            "summary": " ".join(sentences) if len(sentences) > 1
            else sentences[0] + " No major issues detected.",
            "prioritized_actions": actions[:8],
            "generated_by_llm": False,
            "model": "",
        }

    @staticmethod
    def _build_summary_context(report: dict[str, Any]) -> dict[str, Any]:
        """Compact facts used by the deterministic summary / diagnostics views."""
        hw = report.get("hardware", {}) or {}
        sw = report.get("software", {}) or {}
        cpu = hw.get("cpu") or {}
        ram = hw.get("ram") or {}
        perf = hw.get("performance") or {}
        devices = hw.get("devices") or {}
        external = hw.get("external_devices") or {}
        os_ = sw.get("operating_system") or {}
        win = os_.get("windows") or {}
        net = sw.get("network") or {}
        conn = net.get("connectivity") or {}
        sec = sw.get("security") or {}
        svc = sw.get("services") or {}
        crash = sw.get("crash_analysis") or {}
        logs = sw.get("event_logs") or {}
        proc = sw.get("running_processes") or {}
        startup = sw.get("startup_programs") or {}
        health = report.get("health_report") or {}

        drives = [
            {"drive": d.get("drive"), "used_pct": d.get("usage_pct"), "free_gb": d.get("free_gb")}
            for d in (hw.get("storage") or {}).get("logical_drives", [])
        ]
        smart_bad = [
            d.get("name") for d in (hw.get("disk_health") or {}).get("disks", [])
            if (d.get("smart_health") or "").lower() not in ("healthy", "", "none")
        ]
        top_cpu = [
            {"name": p.get("name"), "cpu_pct": p.get("cpu_pct"), "mem_mb": p.get("memory_mb")}
            for p in (proc.get("top_cpu") or [])[:6]
        ]

        system = hw.get("system") or {}
        activation = os_.get("activation") or {}
        reboot = os_.get("pending_reboot") or {}
        join = os_.get("join_status") or {}
        defender = sec.get("windows_defender") or {}
        accounts = sec.get("local_accounts") or {}
        remote = sec.get("remote_access") or {}
        wifi = net.get("wifi") or {}
        tasks = (startup.get("scheduled_tasks") or {})

        return {
            "health": {
                "score": health.get("overall_score"),
                "status": health.get("overall_status"),
                "hardware_notes": (health.get("categories") or {}).get("hardware", {}).get("notes", []),
                "software_notes": (health.get("categories") or {}).get("software", {}).get("notes", []),
            },
            "machine": {
                "manufacturer": system.get("manufacturer"),
                "model": system.get("model"),
                "serial": system.get("serial_number"),
                "chassis": system.get("chassis_type"),
            },
            "cpu": {
                "name": cpu.get("processor_name"),
                "usage_pct": cpu.get("current_usage_pct"),
                "avg_pct": (perf.get("cpu") or {}).get("average_pct"),
                "virtualization": cpu.get("virtualization_firmware_enabled"),
            },
            "memory": {
                "total_gb": ram.get("total_gb"),
                "used_pct": ram.get("utilization_pct"),
                "page_file_used_pct": (ram.get("virtual_memory") or {}).get("used_pct"),
            },
            "drives": drives,
            "disk_smart_issues": smart_bad,
            "devices": {
                "total": devices.get("total_count"),
                "problems": devices.get("problem_count"),
                "problem_names": [d.get("name") for d in (devices.get("problem_devices") or [])[:8]],
            },
            "external_devices": {
                "total": (external.get("summary") or {}).get("total_external_devices"),
                "issues": (external.get("summary") or {}).get("issues", [])[:8],
                "printers": [
                    {"name": p.get("name"), "status": p.get("health"),
                     "connection": p.get("connection")}
                    for p in (external.get("printers") or {}).get("printers", [])[:6]
                ],
                "monitors": (external.get("monitors") or {}).get("count"),
                "usb_connected": (external.get("usb") or {}).get("count"),
                "bluetooth_connected": (external.get("bluetooth") or {}).get("connected_count"),
                "external_storage": [
                    {"name": s.get("name"), "free_gb": s.get("free_gb"), "health": s.get("health")}
                    for s in (external.get("external_storage") or {}).get("devices", [])[:4]
                ],
            },
            "os": {
                "edition": win.get("edition"),
                "uptime": win.get("uptime_readable"),
                "pending_updates": (os_.get("updates") or {}).get("pending_count"),
                "activated": activation.get("activated"),
                "pending_reboot": reboot.get("required"),
                "azure_ad_joined": join.get("azure_ad_joined"),
                "domain_joined": join.get("domain_joined"),
            },
            "software": {
                "installed_count": sw.get("installed_count"),
                "recently_installed_30d": len(sw.get("recently_installed_30d") or []),
                "remote_access_tools": [a.get("name") for a in (sw.get("remote_access_tools") or [])[:5]],
                "top_cpu_processes": top_cpu,
                "failed_services": [s.get("name") for s in (svc.get("failed_critical") or [])],
                "high_impact_startup": startup.get("high_impact_count"),
                "third_party_logon_tasks": len(tasks.get("third_party_logon_tasks") or []),
            },
            "network": {
                "internet": conn.get("internet"),
                "dns_ok": conn.get("dns_resolution"),
                "latency_ms": conn.get("internet_latency_ms"),
                "wifi_ssid": wifi.get("ssid"),
                "wifi_signal_pct": wifi.get("signal_pct"),
                "proxy_enabled": (net.get("proxy") or {}).get("proxy_enabled"),
                "notable_open_ports": [
                    f"{p.get('port')}/{p.get('service')}"
                    for p in ((net.get("connections") or {}).get("notable_listening") or [])[:8]
                ],
            },
            "security": {
                "protected": sec.get("protection_active"),
                "firewall_on": (sec.get("firewall") or {}).get("all_enabled"),
                "bitlocker": (sec.get("bitlocker") or {}).get("system_drive_protected"),
                "signature_age_days": defender.get("signature_age_days"),
                "uac_enabled": (sec.get("uac") or {}).get("enabled"),
                "secure_boot": (sec.get("secure_boot") or {}).get("enabled"),
                "tpm_ready": (sec.get("tpm") or {}).get("ready"),
                "rdp_enabled": remote.get("rdp_enabled"),
                "smb1_enabled": remote.get("smb1_enabled"),
                "local_admins": accounts.get("administrator_count"),
                "guest_enabled": accounts.get("guest_account_enabled"),
            },
            "stability": (crash.get("summary") or {}) | (logs.get("summary") or {}),
            "storage_intelligence": _storage_summary_context(
                (sw.get("storage_intelligence") or {}) if isinstance(sw, dict) else {},
                (sw.get("storage_deep") or {}) if isinstance(sw, dict) else {},
            ),
        }


def _storage_summary_context(
    si: dict[str, Any],
    deep: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Compact storage-intelligence facts for the LLM health summary."""
    if not si or si.get("error"):
        return {}
    cleanup = si.get("cleanup") or {}
    health = si.get("health") or {}
    top_locs = sorted(
        (si.get("cleanup_locations") or []),
        key=lambda x: float(x.get("size_gb") or 0),
        reverse=True,
    )[:6]
    ctx: dict[str, Any] = {
        "health_score": health.get("overall_score"),
        "health_status": health.get("overall_status"),
        "recoverable_gb": cleanup.get("total_potential_gb"),
        "quick_wins": [
            {"label": i.get("label"), "recover_gb": i.get("recover_gb")}
            for i in (cleanup.get("quick_wins") or [])[:4]
        ],
        "top_cleanup_locations": [
            {"label": x.get("label"), "size_gb": x.get("size_gb")}
            for x in top_locs
        ],
        "notes": (health.get("notes") or [])[:4],
    }
    if deep and not deep.get("error"):
        tree = deep.get("tree") or {}
        ctx["scan_mode"] = "deep"
        ctx["largest_files"] = [
            {"path": f.get("path"), "size_gb": f.get("size_gb")}
            for f in (tree.get("top_files") or [])[:10]
        ]
        ctx["largest_folders"] = [
            {"path": f.get("path"), "size_gb": f.get("size_gb")}
            for f in (tree.get("top_folders") or [])[:6]
        ]
    return ctx
