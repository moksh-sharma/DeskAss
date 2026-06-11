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

from app.core.logging import get_logger
from app.services.ollama_service import OllamaService
from app.services.scanners import (
    crash,
    event_logs,
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
    "(health scores, hardware identity, storage/SMART, security posture - antivirus, firewall, "
    "BitLocker, TPM, Secure Boot, UAC, SMBv1, local admins - OS activation, pending reboots, "
    "domain/Azure AD join, network exposure, crashes, services). Cover, in order of impact: "
    "(1) overall condition, (2) performance/resource pressure, (3) security & compliance risks, "
    "(4) stability problems, (5) anything an IT admin should remediate. STRICT RULES: use ONLY "
    "the data provided; never invent numbers, devices, or issues; cite the actual figures. "
    "Return ONLY the requested JSON."
)


class MachineScanService:
    """Builds a full, structured snapshot of the machine for diagnosis."""

    def __init__(
        self,
        inventory: Optional[SystemInventory] = None,
        ollama: Optional[OllamaService] = None,
        use_llm: bool = False,
        summary_model: str = "",
    ) -> None:
        self._inventory = inventory or SystemInventory()
        self._ollama = ollama
        self._use_llm = use_llm
        self._summary_model = summary_model

    async def scan(
        self,
        *,
        ocr_results: Optional[dict] = None,
        rag_context: Optional[dict] = None,
    ) -> dict[str, Any]:
        start = time.perf_counter()
        snapshot = await asyncio.to_thread(self._inventory.snapshot)

        # Scanners that need the installed-app/process inventory.
        inv_scanners = {
            "installed_software": (software.scan, (snapshot,)),
            "services": (services_scan.scan, (snapshot,)),
        }
        # Standalone scanners.
        plain_scanners = {
            "hardware": (hardware.scan, ()),
            "operating_system": (operating_system.scan, ()),
            "performance": (performance.scan, ()),
            "processes": (processes.scan, ()),
            "startup_programs": (startup.scan, ()),
            "event_logs": (event_logs.scan, ()),
            "network": (network.scan, ()),
            "security": (security.scan, ()),
            "crash_analysis": (crash.scan, ()),
        }

        all_scanners = {**plain_scanners, **inv_scanners}
        keys = list(all_scanners.keys())
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
        }

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
        logger.info(
            "Full machine scan complete in %.1fs - health %s (%d/100)",
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
        }
