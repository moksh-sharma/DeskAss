"""AI diagnosis engine - fuses diagnostics, logs, OCR and KB into a grounded
root-cause analysis using Ollama, with heuristic evidence + confidence scoring."""
from __future__ import annotations

import json
import re
from typing import Optional

from app.core.logging import get_logger
from app.models.schemas import (
    DiagnosisResult,
    Evidence,
    EventLogSummary,
    KnowledgeReference,
    RecommendedFix,
    Severity,
    SystemDiagnostics,
)
from app.services.diagnostics_service import (
    CPU_CRIT,
    CPU_WARN,
    DISK_CRIT,
    DISK_WARN,
    RAM_CRIT,
    RAM_WARN,
)
from app.services.ollama_service import OllamaService
from app.services.rag_service import RagService
from app.utils.message_intent import Intent, classify_message

logger = get_logger(__name__)

# Benign Windows events that should NOT be treated as root causes.
_BENIGN_EVENT_IDS: set[tuple[str, int]] = {
    ("netwtw10", 6062),   # Intel Wi-Fi driver notice
    ("win32k", 700),
    ("win32k", 701),
    (".net runtime", 1022),  # profiling API attach - usually harmless
}

# Processes that are often dev/assistant tooling - never recommend killing below this CPU %.
_DEV_PROCESS_NAMES = {"python.exe", "pythonw.exe", "node.exe", "uvicorn.exe", "electron.exe"}

# Not real CPU hogs - ignore as "top CPU" culprits.
_IGNORE_CPU_PROCESS_NAMES = {"system idle process", "memcompression"}

_UPTIME_SLOW_HOURS = 48.0  # 2+ days without restart + slowness → restart-first guidance

SYSTEM_PROMPT = """You are a Senior IT Support Engineer (10+ years) for a Windows enterprise environment.

Your job is to give an ACCURATE, SPECIFIC diagnosis for the EXACT problem the user reported -
not generic advice. Follow these rules strictly:

1. ANCHOR TO THE USER'S ISSUE. Every part of your answer must directly address the specific
   symptom they described (e.g. if they say "Outlook crashes on launch", focus on Outlook
   launch crashes - do not drift into unrelated CPU/RAM advice unless the evidence shows it
   is the cause).
2. USE THE EVIDENCE. Base conclusions only on the supplied system diagnostics, Windows event
   logs, screenshot OCR, and knowledge base context. Never invent metrics, event IDs, file
   names, or error codes that were not provided. If evidence is missing, say so and lower
   confidence accordingly.
3. CITE SPECIFICS. In 'reasoning', reference the actual numbers, process names, event sources,
   error codes, or KB articles that led to your conclusion.
4. DETAILED, ACTIONABLE STEPS. Resolution steps must be precise and reproducible for a
   non-expert: give exact menu paths (e.g. "Settings > Apps > Startup"), exact commands
   (e.g. `outlook.exe /safe`, `ipconfig /flushdns`), what the user should click, and what a
   successful result looks like. Order steps safest-first (least disruptive before drastic).
5. SAFETY. Never auto-execute anything. Every fix requires the user's confirmation.

Be precise and technical, but explain clearly. Quality and accuracy matter more than brevity."""

# A STRUCTURAL template (not a real scenario) showing the depth/shape each step
# should have. It deliberately uses placeholders so the model learns the FORMAT
# without copying any specific application's troubleshooting steps.
_STEP_TEMPLATE = [
    "<First, least-disruptive action that targets the user's exact symptom>: include the exact "
    "Windows location (e.g. 'Settings > System > ...') or the exact command in backticks, what to "
    "click, and what a successful result looks like.",
    "<Next diagnostic step that narrows down the cause>: state precisely what to open/run and how "
    "to interpret the outcome (e.g. 'if X happens, the cause is Y - go to the next step').",
    "<Targeted fix for the most likely cause from the evidence>: exact steps, commands, or settings, "
    "with the expected result.",
    "<Verification step>: how the user confirms the issue is resolved.",
    "<Escalation/fallback if the earlier steps did not help>: a safe, more thorough action, ordered "
    "after the gentler fixes.",
]


_CONVERSATIONAL_REPLIES: dict[Intent, str] = {
    "greeting": (
        "Hi! I'm HelpDesk Assistant. Describe any IT issue on this machine - "
        "for example, \"Bluetooth won't connect\", \"this PC won't start\", or \"Wi-Fi keeps dropping\" - "
        "and I'll run a live scan of the related drivers, services, devices, and logs to pinpoint the cause."
    ),
    "thanks": (
        "You're welcome! Let me know if you run into another issue on this machine."
    ),
    "capabilities": (
        "I can troubleshoot Windows IT problems on this PC. Tell me what's going wrong, "
        "upload an error screenshot, use voice input, or run a full diagnostic scan from the toolbar. "
        "I parse your issue and scan the live system - drivers, services, devices, and event logs - "
        "to diagnose the cause from real evidence."
    ),
}


class DiagnosisService:
    """Builds the structured prompt, calls the LLM and assembles the result."""

    def __init__(self, ollama: OllamaService, rag: RagService) -> None:
        self._ollama = ollama
        self._rag = rag

    def conversational_response(self, message: str) -> DiagnosisResult:
        """Short reply for greetings and other non-troubleshooting chat."""
        intent = classify_message(message)
        if intent == "troubleshooting":
            intent = "greeting"
        text = _CONVERSATIONAL_REPLIES[intent]
        return DiagnosisResult(
            issue_summary=text,
            is_conversational=True,
            severity=Severity.healthy,
            confidence=100,
        )

    async def diagnose(
        self,
        problem: str,
        *,
        diagnostics: Optional[SystemDiagnostics] = None,
        event_logs: Optional[EventLogSummary] = None,
        ocr_text: Optional[str] = None,
        model: Optional[str] = None,
    ) -> DiagnosisResult:
        # 1. Retrieve grounded knowledge base context first.
        kb_query = problem if not ocr_text else f"{problem}\n{ocr_text}"
        references = self._rag.retrieve(kb_query)
        logger.info("RAG retrieved %d knowledge base article(s) for query", len(references))

        # 2. Compute deterministic evidence from raw diagnostics/logs.
        evidence = self._build_evidence(diagnostics, event_logs, ocr_text)
        heuristic_severity = self._heuristic_severity(diagnostics, event_logs)

        # 3. Build the structured prompt.
        prompt = self._build_prompt(problem, diagnostics, event_logs, ocr_text, references)

        # 4. Ask the LLM for a structured JSON diagnosis. Low temperature for accuracy,
        #    larger context + output budget so detailed steps are not truncated.
        used_model = model or self._ollama.default_model
        logger.info("Sending prompt to Ollama model=%s (json_mode=True)...", used_model)
        raw = await self._ollama.generate(
            prompt,
            system=SYSTEM_PROMPT,
            model=used_model,
            json_mode=True,
            temperature=0.15,
            options={"top_p": 0.9, "num_ctx": 6144, "num_predict": 1536, "repeat_penalty": 1.1},
        )

        logger.info("Ollama response received (%d chars)", len(raw))
        result = self._parse_result(raw)
        result.model = used_model
        result.raw_response = raw

        # 5. Merge deterministic evidence + references + severity floor.
        result.evidence = self._merge_evidence(result.evidence, evidence)
        result.knowledge_references = references
        result.severity = self._reconcile_severity(result.severity, heuristic_severity)
        result.confidence = self._reconcile_confidence(result, evidence, references)
        if not result.confidence_reasons:
            result.confidence_reasons = self._default_confidence_reasons(evidence, references)
        result = self._refine_result(problem, result, diagnostics, event_logs)
        return result

    # ------------------------------------------------------------------ #
    #  Prompt construction
    # ------------------------------------------------------------------ #
    def _build_prompt(
        self,
        problem: str,
        diagnostics: Optional[SystemDiagnostics],
        event_logs: Optional[EventLogSummary],
        ocr_text: Optional[str],
        references: list[KnowledgeReference],
    ) -> str:
        parts: list[str] = []
        parts.append("# USER PROBLEM\n" + problem.strip())

        if ocr_text:
            parts.append("# SCREENSHOT OCR TEXT\n" + ocr_text.strip()[:1500])

        if diagnostics:
            parts.append(
                "# SYSTEM DIAGNOSTICS (supporting context - use only if relevant to the symptom)\n"
                + self._format_diagnostics(diagnostics)
            )

        if event_logs and event_logs.available and event_logs.entries:
            parts.append("# WINDOWS EVENT LOGS (recent errors/warnings)\n" + self._format_logs(event_logs))

        if references:
            kb = "\n\n".join(
                f"[{i+1}] {r.title} (category: {r.category})\n{r.snippet}"
                for i, r in enumerate(references)
            )
            parts.append("# KNOWLEDGE BASE CONTEXT\n" + kb)

        hint = self._issue_context_hint(problem, diagnostics)
        if hint:
            parts.append(hint)

        parts.append(self._instructions())
        return "\n\n".join(parts)

    @staticmethod
    def _instructions() -> str:
        # NOTE: field descriptions deliberately state required counts; we avoid
        # showing single-element example arrays because models tend to mirror the
        # cardinality of the example (returning only one item).
        schema_fields = (
            '  "issue_summary": string - one precise sentence restating the user\'s specific problem,\n'
            '  "severity": string - one of "Healthy", "Info", "Warning", "Critical",\n'
            '  "confidence": integer 0-100 - how strongly the evidence supports the root cause,\n'
            '  "confidence_reasons": array of 2-4 strings - each cites a specific piece of evidence,\n'
            '  "root_cause": string - the single most likely cause, specific to the user\'s symptom,\n'
            '  "reasoning": string - 2-4 sentences citing exact numbers/process names/event IDs/'
            "error codes/KB titles that lead to the root cause,\n"
            '  "evidence": array of 2-6 objects, each {"label": string, "value": string, '
            '"severity": "Healthy|Info|Warning|Critical"},\n'
            '  "recommended_fixes": array of 2-4 objects, each {"title": string, "description": '
            'string, "safe_action": string, "requires_confirmation": true},\n'
            '  "resolution_steps": array of 5-8 strings - see the detail requirements below,\n'
            '  "prevention_tips": array of 2-4 strings - specific, actionable\n'
        )
        return (
            "# INSTRUCTIONS\n"
            "Diagnose the SPECIFIC problem in '# USER PROBLEM' above.\n\n"
            "CRITICAL RULES:\n"
            "1. If the user names a specific application or feature (e.g. Outlook, Teams, VPN, "
            "Wi-Fi, Office), your root_cause and EVERY resolution step MUST address that "
            "application's failure mode. Treat system metrics (CPU/RAM/disk) as SUPPORTING "
            "CONTEXT only - do NOT conclude 'high RAM/CPU' is the cause unless a metric is "
            "clearly and directly responsible for the named symptom.\n"
            "1b. UPTIME / GENERAL SLOWNESS: If the user says the PC has been on for many days "
            "or asks whether to restart, the root cause is likely memory leaks and pending "
            "updates from long uptime - NOT normal background CPU. Step 1 MUST be restart the "
            "PC. CPU under 50% and RAM under 85% are usually healthy; do not blame them.\n"
            "1c. NEVER recommend ending python.exe, node.exe, or uvicorn.exe unless they exceed "
            "40% CPU - these are often development or assistant tools running on the machine.\n"
            "1d. IGNORE benign log noise: Intel Netwtw10 Event 6062, Win32k 700/701, and .NET "
            "Runtime 1022 are usually harmless - do not list them as root causes.\n"
            "2. Ground everything in the provided evidence and knowledge base context. In "
            "'reasoning' and 'evidence', cite the actual data you used. Never invent data.\n"
            "3. 'resolution_steps' MUST contain 5-8 entries, each detailed and reproducible for a "
            "non-expert: the exact menu path (e.g. 'File > Options > Add-ins'), exact command in "
            "backticks (e.g. `outlook.exe /safe`), what to click, and the expected result of the "
            "step. Order them safest/least-disruptive first.\n"
            "4. Never recommend automatic execution; every fix requires user confirmation.\n"
            "5. The TEMPLATE below shows only the required SHAPE and depth of each step using "
            "placeholders in <angle brackets>. It is NOT a real solution. Do NOT copy it, and do NOT "
            "mention any application (such as Outlook) unless the user's problem is actually about that "
            "application. Replace every placeholder with concrete actions for the user's REAL problem.\n\n"
            "Respond with ONLY valid JSON containing exactly these fields:\n{\n"
            + schema_fields
            + "}\n\n# STEP TEMPLATE - shape/depth reference ONLY (placeholders, do not copy literally):\n"
            + json.dumps(_STEP_TEMPLATE, indent=2)
            + "\n\nReminder: produce 5-8 detailed steps that address the user's EXACT symptom and the "
            "supplied evidence. Replace all <placeholders>. Output valid JSON only."
        )

    @staticmethod
    def _format_diagnostics(d: SystemDiagnostics) -> str:
        lines = []
        if d.uptime_hours is not None:
            days = round(d.uptime_hours / 24, 1)
            lines.append(f"System uptime: {d.uptime_hours:.1f} hours ({days} days since last restart)")
        lines.extend([
            f"OS: {d.os.system} {d.os.release} (build {d.os.build}), arch {d.os.architecture}, host {d.os.hostname}",
            f"CPU: {d.cpu.usage_percent}% used, {d.cpu.physical_cores} cores / {d.cpu.logical_cores} threads, {d.cpu.frequency_mhz} MHz",
            f"RAM: {d.memory.usage_percent}% used ({d.memory.used_gb}/{d.memory.total_gb} GB, {d.memory.available_gb} GB free)",
        ])
        for disk in d.disks:
            lines.append(f"Disk {disk.device} ({disk.mountpoint}): {disk.usage_percent}% used, {disk.free_gb} GB free of {disk.total_gb} GB")
        lines.append(
            f"Network: {'connected' if d.network.internet_connected else 'NO internet'}, primary IP {d.network.primary_ip}"
        )
        if d.battery.present:
            lines.append(f"Battery: {d.battery.percent}% {'(charging)' if d.battery.charging else '(on battery)'}")
        if d.top_cpu_processes:
            top = ", ".join(f"{p.name} {p.cpu_percent}%" for p in d.top_cpu_processes[:5])
            lines.append(f"Top CPU processes: {top}")
        if d.top_memory_processes:
            topm = ", ".join(f"{p.name} {p.memory_mb}MB" for p in d.top_memory_processes[:5])
            lines.append(f"Top RAM processes: {topm}")
        installed = [s.name for s in d.installed_software if s.installed]
        if installed:
            lines.append("Detected software: " + ", ".join(installed))
        if d.startup_programs:
            lines.append(f"Startup programs ({len(d.startup_programs)}): " + ", ".join(s.name for s in d.startup_programs[:10]))
        return "\n".join(lines)

    @classmethod
    def _is_benign_event(cls, source: str, event_id: Optional[int]) -> bool:
        if event_id is None:
            return False
        return (source.lower(), event_id) in _BENIGN_EVENT_IDS

    @classmethod
    def _format_logs(cls, logs: EventLogSummary) -> str:
        lines = [f"Totals: {logs.error_count} errors, {logs.warning_count} warnings in window."]
        shown = 0
        for e in logs.entries:
            if cls._is_benign_event(e.source, e.event_id):
                continue
            ts = e.time_generated.strftime("%Y-%m-%d %H:%M") if e.time_generated else "?"
            cat = f" [{e.category}]" if e.category else ""
            lines.append(f"- {ts} {e.level}{cat} {e.source} (ID {e.event_id}): {e.message[:200]}")
            shown += 1
            if shown >= 12:
                break
        benign = sum(1 for e in logs.entries if cls._is_benign_event(e.source, e.event_id))
        if benign:
            lines.append(f"(Note: {benign} benign Wi-Fi/kernel/.NET notices omitted from this list.)")
        return "\n".join(lines)

    @classmethod
    def _is_uptime_slowness(cls, problem: str, d: Optional[SystemDiagnostics]) -> bool:
        text = problem.lower()
        asks_restart = any(w in text for w in ("restart", "reboot", "been on for", "uptime", "days and"))
        feels_slow = any(w in text for w in ("slow", "sluggish", "laggy", "lag"))
        long_uptime = False
        if d and d.uptime_hours is not None:
            long_uptime = d.uptime_hours >= _UPTIME_SLOW_HOURS
        if re.search(r"\d+(?:\.\d+)?\s*days?", text):
            long_uptime = True
        return feels_slow and (asks_restart or long_uptime)

    @classmethod
    def _issue_context_hint(cls, problem: str, d: Optional[SystemDiagnostics]) -> str:
        if not cls._is_uptime_slowness(problem, d):
            return ""
        uptime_h = d.uptime_hours if d and d.uptime_hours else None
        days = round(uptime_h / 24, 1) if uptime_h else "several"
        cpu = d.cpu.usage_percent if d else "?"
        ram = d.memory.usage_percent if d else "?"
        return (
            "# ISSUE CONTEXT (READ CAREFULLY)\n"
            f"The user reports general slowness after ~{days} days of uptime.\n"
            "PRIMARY CAUSE: long uptime - memory leaks, stale handles, and pending Windows updates.\n"
            f"Current CPU {cpu}% and RAM {ram}% are supporting context only; do NOT blame them unless "
            "CPU > 50% or RAM > 90%.\n"
            "ANSWER THE USER'S QUESTION: Yes, restart the PC - that should be resolution step 1.\n"
            "Do NOT recommend killing python.exe/node.exe (dev/assistant tools) or netsh winsock reset "
            "for this scenario. Ignore benign Netwtw10 6062 events."
        )

    # ------------------------------------------------------------------ #
    #  Deterministic evidence + scoring
    # ------------------------------------------------------------------ #
    def _build_evidence(
        self,
        d: Optional[SystemDiagnostics],
        logs: Optional[EventLogSummary],
        ocr_text: Optional[str],
    ) -> list[Evidence]:
        evidence: list[Evidence] = []
        if d:
            evidence.append(Evidence(label="CPU Usage", value=f"{d.cpu.usage_percent}%",
                                     severity=self._level(d.cpu.usage_percent, CPU_WARN, CPU_CRIT)))
            evidence.append(Evidence(label="RAM Usage", value=f"{d.memory.usage_percent}%",
                                     severity=self._level(d.memory.usage_percent, RAM_WARN, RAM_CRIT)))
            for disk in d.disks:
                evidence.append(Evidence(label=f"Disk {disk.device} Usage", value=f"{disk.usage_percent}% ({disk.free_gb} GB free)",
                                         severity=self._level(disk.usage_percent, DISK_WARN, DISK_CRIT)))
            if not d.network.internet_connected:
                evidence.append(Evidence(label="Network", value="No internet connectivity", severity=Severity.critical))
            if d.uptime_hours is not None and d.uptime_hours >= _UPTIME_SLOW_HOURS:
                days = round(d.uptime_hours / 24, 1)
                evidence.append(Evidence(
                    label="System Uptime",
                    value=f"{days} days since last restart",
                    severity=Severity.warning if d.uptime_hours >= 72 else Severity.info,
                ))
            if d.top_cpu_processes:
                for p in d.top_cpu_processes:
                    if p.name.lower() in _IGNORE_CPU_PROCESS_NAMES:
                        continue
                    if p.cpu_percent >= 20:
                        evidence.append(Evidence(
                            label="Top CPU Process",
                            value=f"{p.name} ({p.cpu_percent}%)",
                            severity=self._level(p.cpu_percent, 40, 70),
                        ))
                        break
            if d.top_memory_processes:
                p = d.top_memory_processes[0]
                ram_sev = self._level(d.memory.usage_percent, RAM_WARN, RAM_CRIT)
                if ram_sev != Severity.healthy:
                    evidence.append(Evidence(
                        label="Top RAM Process",
                        value=f"{p.name} ({p.memory_mb} MB)",
                        severity=ram_sev,
                    ))
        if logs and logs.available:
            meaningful_errors = sum(
                1 for e in logs.entries
                if e.level == "Error" and not self._is_benign_event(e.source, e.event_id)
            )
            if meaningful_errors:
                evidence.append(Evidence(
                    label="Event Log Errors",
                    value=str(meaningful_errors),
                    severity=Severity.warning if meaningful_errors < 10 else Severity.critical,
                ))
            seen_events: set[str] = set()
            for e in logs.entries:
                if self._is_benign_event(e.source, e.event_id):
                    continue
                if e.category not in {"Application Crash", "Application Hang", "Outlook", "Teams", "Service"}:
                    continue
                key = f"{e.source}:{e.event_id}"
                if key in seen_events:
                    continue
                seen_events.add(key)
                evidence.append(Evidence(
                    label=f"{e.category} Event",
                    value=f"{e.source} (ID {e.event_id}): {e.message[:80]}",
                    severity=Severity.warning,
                ))
                if len(seen_events) >= 3:
                    break
        if ocr_text:
            evidence.append(Evidence(label="Screenshot OCR", value=ocr_text[:120], severity=Severity.info))
        return evidence

    def _heuristic_severity(self, d: Optional[SystemDiagnostics], logs: Optional[EventLogSummary]) -> Severity:
        worst = Severity.healthy
        ranking = {Severity.healthy: 0, Severity.info: 1, Severity.warning: 2, Severity.critical: 3}

        def bump(s: Severity) -> None:
            nonlocal worst
            if ranking[s] > ranking[worst]:
                worst = s

        if d:
            bump(self._level(d.cpu.usage_percent, CPU_WARN, CPU_CRIT))
            bump(self._level(d.memory.usage_percent, RAM_WARN, RAM_CRIT))
            for disk in d.disks:
                bump(self._level(disk.usage_percent, DISK_WARN, DISK_CRIT))
            if not d.network.internet_connected:
                bump(Severity.warning)
        if logs and logs.available:
            meaningful = sum(
                1 for e in logs.entries
                if e.level == "Error" and not self._is_benign_event(e.source, e.event_id)
            )
            if meaningful >= 10:
                bump(Severity.critical)
            elif meaningful > 0:
                bump(Severity.warning)
        if d and d.uptime_hours is not None and d.uptime_hours >= _UPTIME_SLOW_HOURS:
            bump(Severity.info if d.uptime_hours < 72 else Severity.warning)
        return worst

    # Patterns that are almost always wrong for uptime/slowness scenarios.
    _BAD_ADVICE_PATTERNS: tuple[re.Pattern[str], ...] = (
        re.compile(r"end\s+task.*python", re.I),
        re.compile(r"kill.*python", re.I),
        re.compile(r"right[- ]click.*python", re.I),
        re.compile(r"netsh\s+winsock", re.I),
        re.compile(r"winsock\s+reset", re.I),
        re.compile(r"virtual\s+memory", re.I),
        re.compile(r"paging\s+file", re.I),
        re.compile(r"netwtw10", re.I),
        re.compile(r"\b6062\b"),
    )

    _RESTART_STEP = re.compile(r"\brestart\b|\breboot\b", re.I)

    def _mentions_bad_advice(self, text: str) -> bool:
        return any(p.search(text) for p in self._BAD_ADVICE_PATTERNS)

    def _is_restart_step(self, text: str) -> bool:
        return bool(self._RESTART_STEP.search(text))

    def _restart_step(self, days: float) -> str:
        return (
            f"Save your work, then restart the PC (Start > Power > Restart). After ~{days} days of "
            "uptime, a restart clears memory leaks, stale handles, and pending update installs - "
            "you should notice improved responsiveness within a few minutes of signing back in."
        )

    def _refine_result(
        self,
        problem: str,
        result: DiagnosisResult,
        d: Optional[SystemDiagnostics],
        logs: Optional[EventLogSummary],
    ) -> DiagnosisResult:
        """Post-process LLM output to drop harmful or irrelevant advice."""
        uptime_case = self._is_uptime_slowness(problem, d)
        days = round(d.uptime_hours / 24, 1) if d and d.uptime_hours else None

        filtered_evidence: list[Evidence] = []
        for e in result.evidence:
            blob = f"{e.label} {e.value}".lower()
            if self._mentions_bad_advice(blob):
                continue
            if e.label.lower() == "top ram process" and d and d.memory.usage_percent < RAM_WARN:
                continue
            if e.label.lower() == "top cpu process" and d:
                name = e.value.split("(")[0].strip().lower()
                if name in _IGNORE_CPU_PROCESS_NAMES or name in _DEV_PROCESS_NAMES:
                    continue
            if "driver event" in e.label.lower() and ("netwtw10" in blob or "6062" in blob):
                continue
            filtered_evidence.append(e)
        result.evidence = filtered_evidence

        result.recommended_fixes = [
            f for f in result.recommended_fixes
            if not self._mentions_bad_advice(f"{f.title} {f.description} {f.safe_action or ''}")
        ]
        result.resolution_steps = [
            s for s in result.resolution_steps
            if not self._mentions_bad_advice(s)
        ]
        result.confidence_reasons = [
            r for r in result.confidence_reasons
            if not self._mentions_bad_advice(r)
            and "python.exe" not in r.lower()
            and "netwtw10" not in r.lower()
            and not (
                d
                and d.memory.usage_percent < RAM_WARN
                and re.search(r"\b(ram|memory)\b", r, re.I)
            )
            and not (
                d
                and d.cpu.usage_percent < 50
                and re.search(r"\bcpu\b", r, re.I)
            )
        ]

        if not uptime_case:
            return result

        # Uptime / general slowness - enforce restart-first, sane root cause.
        if days is not None:
            expected_root = (
                f"Extended uptime (~{days} days without a restart) has allowed memory leaks, "
                "stale background processes, and pending Windows updates to accumulate - "
                "a common cause of gradual slowness even when CPU and RAM look normal."
            )
            blob = f"{result.root_cause} {result.reasoning}".lower()
            if (
                "python" in blob
                or "netwtw10" in blob
                or "winsock" in blob
                or (d and d.cpu.usage_percent < 50 and "cpu" in result.root_cause.lower())
                or (d and d.memory.usage_percent < 85 and "ram" in result.root_cause.lower())
            ):
                result.root_cause = expected_root
                if "restart" not in result.reasoning.lower():
                    result.reasoning = (
                        f"The PC has been running for ~{days} days. Current CPU "
                        f"({d.cpu.usage_percent if d else '?'}%) and RAM "
                        f"({d.memory.usage_percent if d else '?'}%) are within normal range, "
                        "so the slowness is more likely from long uptime than a runaway process. "
                        "Restarting clears accumulated state and is the safest first fix."
                    )

        if not any(self._is_restart_step(s) for s in result.resolution_steps):
            result.resolution_steps.insert(0, self._restart_step(days or 4.0))

        has_restart_fix = any(
            self._is_restart_step(f"{f.title} {f.description}")
            for f in result.recommended_fixes
        )
        if not has_restart_fix:
            result.recommended_fixes.insert(0, RecommendedFix(
                title="Restart the PC",
                description=(
                    "A restart is the fastest way to recover from days of accumulated uptime. "
                    "Save open files first."
                ),
                safe_action=self._restart_step(days or 4.0),
                requires_confirmation=True,
            ))

        if result.severity == Severity.critical and d:
            if d.cpu.usage_percent < CPU_WARN and d.memory.usage_percent < RAM_WARN:
                result.severity = Severity.warning

        if not result.confidence_reasons and days is not None:
            result.confidence_reasons = [
                f"System uptime: ~{days} days since last restart",
                f"CPU at {d.cpu.usage_percent}% and RAM at {d.memory.usage_percent}% - within normal range"
                if d else "Metrics within normal range",
            ]

        return result

    @staticmethod
    def _level(value: float, warn: float, crit: float) -> Severity:
        if value >= crit:
            return Severity.critical
        if value >= warn:
            return Severity.warning
        return Severity.healthy

    # ------------------------------------------------------------------ #
    #  Result parsing / reconciliation
    # ------------------------------------------------------------------ #
    def _parse_result(self, raw: str) -> DiagnosisResult:
        data = self._extract_json(raw)
        if data is None:
            logger.warning("LLM response was not valid JSON; falling back to text.")
            return DiagnosisResult(
                issue_summary="AI diagnosis (unstructured)",
                root_cause="See reasoning.",
                reasoning=raw.strip()[:4000],
                severity=Severity.info,
                confidence=40,
            )
        try:
            return DiagnosisResult(
                issue_summary=str(data.get("issue_summary", "")),
                severity=self._coerce_severity(data.get("severity")),
                confidence=self._coerce_int(data.get("confidence"), 0, 100),
                confidence_reasons=self._coerce_list(data.get("confidence_reasons")),
                root_cause=str(data.get("root_cause", "")),
                reasoning=str(data.get("reasoning", "")),
                evidence=[self._coerce_evidence(e) for e in data.get("evidence", []) if isinstance(e, dict)],
                recommended_fixes=[self._coerce_fix(f) for f in data.get("recommended_fixes", []) if isinstance(f, dict)],
                resolution_steps=self._coerce_list(data.get("resolution_steps")),
                prevention_tips=self._coerce_list(data.get("prevention_tips")),
            )
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Failed to map LLM JSON to DiagnosisResult: %s", exc)
            return DiagnosisResult(issue_summary="AI diagnosis", reasoning=raw[:4000], confidence=40)

    @classmethod
    def _extract_json(cls, raw: str) -> Optional[dict]:
        raw = raw.strip()
        # Strip Markdown code fences the model sometimes adds.
        if raw.startswith("```"):
            raw = re.sub(r"^```(?:json)?\s*", "", raw)
            raw = re.sub(r"\s*```$", "", raw).strip()

        for candidate in cls._json_candidates(raw):
            data = cls._loads_lenient(candidate)
            if isinstance(data, dict):
                return data
        return None

    @staticmethod
    def _json_candidates(raw: str):  # type: ignore[no-untyped-def]
        """Yield progressively-cleaned JSON candidates to try parsing."""
        yield raw
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            yield match.group(0)

    @staticmethod
    def _loads_lenient(text: str) -> Optional[dict]:
        # 1. Strict parse.
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        # 2. Remove trailing commas before } or ] and retry.
        cleaned = re.sub(r",(\s*[}\]])", r"\1", text)
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            pass
        # 3. Recover from truncated output: close any unterminated string and
        #    balance open brackets so partial-but-useful content still parses.
        repaired = cleaned
        if repaired.count('"') % 2 == 1:
            repaired += '"'
        opens = repaired.count("{") - repaired.count("}")
        if opens > 0:
            repaired = repaired.rstrip().rstrip(",")
            repaired += "}" * opens
        try:
            return json.loads(repaired)
        except json.JSONDecodeError:
            return None

    def _merge_evidence(self, llm_evidence: list[Evidence], heuristic: list[Evidence]) -> list[Evidence]:
        seen = {e.label.lower() for e in heuristic}
        merged = list(heuristic)
        for e in llm_evidence:
            if e.label.lower() not in seen:
                merged.append(e)
                seen.add(e.label.lower())
        return merged

    @staticmethod
    def _reconcile_severity(llm: Severity, heuristic: Severity) -> Severity:
        ranking = {Severity.healthy: 0, Severity.info: 1, Severity.warning: 2, Severity.critical: 3}
        return llm if ranking[llm] >= ranking[heuristic] else heuristic

    @staticmethod
    def _reconcile_confidence(result: DiagnosisResult, evidence: list[Evidence],
                              refs: list[KnowledgeReference]) -> int:
        confidence = result.confidence
        # Boost confidence when we have corroborating hard evidence + KB hits.
        strong_evidence = sum(1 for e in evidence if e.severity in (Severity.warning, Severity.critical))
        good_refs = sum(1 for r in refs if r.score >= 0.4)
        bonus = min(15, strong_evidence * 4 + good_refs * 3)
        if confidence == 0:
            confidence = 45 + bonus
        else:
            confidence = min(99, confidence + (bonus // 2))
        return max(1, min(99, confidence))

    @staticmethod
    def _default_confidence_reasons(evidence: list[Evidence], refs: list[KnowledgeReference]) -> list[str]:
        reasons: list[str] = []
        for e in evidence:
            if e.severity in (Severity.warning, Severity.critical):
                reasons.append(f"{e.label}: {e.value}")
        if refs:
            reasons.append(f"{len(refs)} matching knowledge base article(s)")
        return reasons[:6] or ["Based on available diagnostics and model analysis."]

    # ----- coercion helpers ----- #
    @staticmethod
    def _coerce_severity(value) -> Severity:  # type: ignore[no-untyped-def]
        if isinstance(value, str):
            for s in Severity:
                if s.value.lower() == value.strip().lower():
                    return s
        return Severity.info

    @staticmethod
    def _coerce_int(value, lo: int, hi: int) -> int:  # type: ignore[no-untyped-def]
        try:
            return max(lo, min(hi, int(float(value))))
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _coerce_list(value) -> list[str]:  # type: ignore[no-untyped-def]
        if isinstance(value, list):
            return [str(v) for v in value if str(v).strip()]
        if isinstance(value, str) and value.strip():
            return [value.strip()]
        return []

    def _coerce_evidence(self, e: dict) -> Evidence:
        return Evidence(
            label=str(e.get("label", "Evidence")),
            value=str(e.get("value", "")),
            severity=self._coerce_severity(e.get("severity")),
        )

    @staticmethod
    def _coerce_fix(f: dict) -> RecommendedFix:
        return RecommendedFix(
            title=str(f.get("title", "Fix")),
            description=str(f.get("description", "")),
            requires_confirmation=bool(f.get("requires_confirmation", True)),
            safe_action=f.get("safe_action"),
        )
