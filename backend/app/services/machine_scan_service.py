"""Orchestrates the comprehensive machine scan.

Runs every independent scanner concurrently (each on a worker thread so the
blocking PowerShell/psutil calls don't stall the event loop), assembles the
structured report matching the requested data structure, and computes a health
score. Optionally folds in OCR text and RAG context for the AI layer.
"""
from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime, timezone
from typing import Any, Optional

from app.core.config import get_settings
from app.core.logging import get_logger
from app.services.ollama_service import OllamaService
from app.services.storage_intelligence_service import StorageIntelligenceService
from app.services.scanners import (
    crash,
    event_logs,
    external_devices,
    hardware,
    health,
    network,
    operating_system,
    performance,
    processes,
    security,
    services_scan,
    software,
    startup,
)
from app.services.system_inventory import SystemInventory

logger = get_logger(__name__)

_HEALTH_SYSTEM = (
    "You are a senior Windows IT support engineer writing an enterprise health and compliance "
    "report for a managed PC. You are given a JSON snapshot collected live from THIS machine "
    "(health scores, hardware identity, storage/SMART, storage intelligence recoverable space, security posture - antivirus, firewall, "
    "BitLocker, TPM, Secure Boot, UAC, SMBv1, local admins - OS activation, pending reboots, "
    "domain/Azure AD join, network exposure, crashes, services, and connected EXTERNAL hardware - "
    "printers (online/offline), monitors, USB devices, Bluetooth peripherals, external storage). "
    "Cover, in order of impact: "
    "(1) overall condition, (2) performance/resource pressure, (3) security & compliance risks, "
    "(4) stability problems, (5) anything an IT admin should remediate. STRICT RULES: use ONLY "
    "the data provided; never invent numbers, devices, or issues; cite the actual figures. "
    "Return ONLY the requested JSON."
)


# Which scanner keys each issue domain needs. Used to run a fast, scoped scan
# for the chat troubleshooter instead of the whole machine every time.
_DOMAIN_SCANNERS: dict[str, set[str]] = {
    "audio": {"hardware", "external_devices"},
    "webcam": {"hardware", "external_devices"},
    "printer": {"hardware", "external_devices"},
    "display": {"hardware", "external_devices"},
    "bluetooth": {"hardware", "external_devices"},
    "usb": {"hardware", "external_devices"},
    "mouse": {"hardware", "external_devices"},
    "keyboard": {"hardware", "external_devices"},
    "storage": {"storage_intelligence"},
    "performance": {"hardware", "performance", "processes", "event_logs"},
    "application": {"installed_software", "processes", "services"},
    "windows_update": {"operating_system", "services"},
    "network": {"network"},
    "wifi": {"network"},
    "security": {"security", "operating_system"},
    "account": {"security", "operating_system"},
    "boot": {"performance", "operating_system", "crash_analysis"},
    "battery": {"hardware", "performance"},
}

# Domains whose answers benefit from the heavy deep storage tree walk.
_DEEP_STORAGE_DOMAINS = {"storage"}


class MachineScanService:
    """Builds a full, structured snapshot of the machine for diagnosis."""

    def __init__(
        self,
        inventory: Optional[SystemInventory] = None,
        ollama: Optional[OllamaService] = None,
        use_llm: bool = False,
        summary_model: str = "",
        storage: Optional[StorageIntelligenceService] = None,
    ) -> None:
        self._inventory = inventory or SystemInventory()
        self._ollama = ollama
        self._use_llm = use_llm
        self._summary_model = summary_model
        self._storage = storage or StorageIntelligenceService()

    @staticmethod
    def _select_scanners(domains: Optional[list[str]]) -> Optional[set[str]]:
        """Return the scanner keys needed for ``domains`` (None = run all)."""
        if domains is None:
            return None
        selected: set[str] = set()
        for d in domains:
            selected |= _DOMAIN_SCANNERS.get(d, set())
        # Unknown/unmapped domains still get a sensible, cheap default so we
        # never run zero scanners (which would yield an empty report).
        return selected or {"hardware", "external_devices"}

    async def scan(
        self,
        *,
        ocr_results: Optional[dict] = None,
        rag_context: Optional[dict] = None,
        target_drive: str | None = None,
        domains: Optional[list[str]] = None,
        run_deep_storage: Optional[bool] = None,
    ) -> dict[str, Any]:
        """Run the machine scan.

        ``domains`` scopes the work to only the scanners an issue needs (chat
        troubleshooter). When ``None``, every scanner runs (Full System Scan).
        ``run_deep_storage`` overrides the heavy storage tree walk; when ``None``
        it defaults to True for a full scan and to storage-domain issues only.
        """
        start = time.perf_counter()
        settings = get_settings()

        # Decide the scanner subset for this run.
        selected_keys = self._select_scanners(domains)
        scoped = domains is not None

        # Deep storage: full scans always do it; scoped scans only when relevant.
        if run_deep_storage is None:
            if scoped:
                run_deep_storage = bool(
                    target_drive
                    or any(d in _DEEP_STORAGE_DOMAINS for d in (domains or []))
                )
            else:
                run_deep_storage = True

        snapshot = await asyncio.to_thread(self._inventory.snapshot)

        async def _deep_storage() -> dict[str, Any] | None:
            if not (settings.storage_deep_enabled and run_deep_storage):
                return None
            try:
                return await asyncio.to_thread(
                    self._storage.deep_scan,
                    tree_budget=settings.storage_deep_tree_budget_seconds,
                    duplicate_budget=settings.storage_deep_duplicate_budget_seconds,
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
        }
        # Standalone scanners.
        plain_scanners = {
            "hardware": (hardware.scan, ()),
            "external_devices": (external_devices.scan, ()),
            "operating_system": (operating_system.scan, ()),
            "performance": (performance.scan, ()),
            "processes": (processes.scan, ()),
            "startup_programs": (startup.scan, ()),
            "event_logs": (event_logs.scan, ()),
            "network": (network.scan, ()),
            "security": (security.scan, ()),
            "crash_analysis": (crash.scan, ()),
            # Fast storage intelligence (~12s) — recoverable space, cleanup targets, health.
            "storage_intelligence": (self._storage.quick_scan, ()),
        }

        all_scanners = {**plain_scanners, **inv_scanners}
        if selected_keys is not None:
            all_scanners = {k: v for k, v in all_scanners.items() if k in selected_keys}
        keys = list(all_scanners.keys())
        if scoped:
            logger.info(
                "Scoped scan for domains=%s -> scanners=%s deep_storage=%s",
                domains, keys, run_deep_storage,
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

        deep_storage = await deep_task
        if deep_storage and not deep_storage.get("error"):
            software_bucket["storage_deep"] = deep_storage
            logger.info(
                "Deep storage scan complete in %.1fs — %d top files, ~%.1f GB recoverable",
                deep_storage.get("scan_duration_seconds") or 0,
                len((deep_storage.get("tree") or {}).get("top_files") or []),
                (deep_storage.get("cleanup") or {}).get("total_potential_gb") or 0,
            )
        elif deep_storage and deep_storage.get("error"):
            software_bucket["storage_deep"] = deep_storage

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
        logger.info(
            "%s machine scan complete in %.1fs - health %s (%d/100)",
            "Scoped" if scoped else "Full",
            elapsed,
            report["health_report"]["overall_status"],
            report["health_report"]["overall_score"],
        )
        return report

    # ------------------------------------------------------------------ #
    #  On-demand LLM summary
    # ------------------------------------------------------------------ #
    async def generate_summary(self, report: dict[str, Any]) -> dict[str, Any]:
        """Generate a grounded LLM narrative from a completed scan report."""
        return await self._ai_summary(report)

    async def _ai_summary(self, report: dict[str, Any]) -> dict[str, Any]:
        health = report.get("health_report", {})
        fallback = {
            "summary": (
                f"Overall health {health.get('overall_score', 0)}/100 "
                f"({health.get('overall_status', 'Unknown')}). "
                + (" ".join(health.get("recommended_actions", [])[:3]) or "No major issues detected.")
            ),
            "prioritized_actions": health.get("recommended_actions", [])[:6],
            "generated_by_llm": False,
            "model": "",
        }
        if not (self._use_llm and self._ollama):
            return fallback
        try:
            if not await self._ollama.health():
                logger.info("Ollama offline - using deterministic scan summary.")
                return fallback
            context = self._build_summary_context(report)
            payload = json.dumps(context, default=str, separators=(",", ":"))
            logger.info("Summary LLM context size: %d chars (model=%s)", len(payload),
                        self._summary_model or self._ollama.default_model)
            prompt = (
                "Machine scan facts (live from this Windows PC):\n"
                + payload
                + '\n\nReturn ONLY JSON: {"summary": string (5-8 sentences covering condition, '
                "performance, security/compliance posture and stability - cite numbers from the "
                "facts), \"prioritized_actions\": array of 4-8 concrete remediation steps ordered "
                "by urgency, each naming the exact component/setting to fix}."
            )
            used_model = self._summary_model or self._ollama.default_model
            raw = await self._ollama.generate(
                prompt,
                system=_HEALTH_SYSTEM,
                model=used_model,
                json_mode=True,
                temperature=0.15,
                options={"num_ctx": 6144, "num_predict": 800},
            )
            data = json.loads(raw)
            if isinstance(data, dict):
                summary = str(data.get("summary") or "").strip()
                actions = [
                    str(a).strip() for a in data.get("prioritized_actions", [])
                    if isinstance(a, (str, int, float)) and str(a).strip()
                ]
                if summary:
                    return {
                        "summary": summary,
                        "prioritized_actions": actions[:8] or fallback["prioritized_actions"],
                        "generated_by_llm": True,
                        "model": used_model,
                    }
        except Exception as exc:  # pragma: no cover - never break the scan
            logger.warning("AI scan summary failed, using deterministic: %s", exc)
        return fallback

    @staticmethod
    def _build_summary_context(report: dict[str, Any]) -> dict[str, Any]:
        """Compact facts for the LLM - small prompt = fast inference on remote Ollama."""
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
