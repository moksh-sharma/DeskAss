"""Automatic issue parser.

Turns a free-text problem description (and optional screenshot OCR text) into a
structured :class:`IssueProfile`: which technical *domains* it concerns, which
*applications* are named, and the *symptoms* expressed. This drives which live
probe packs the investigation runs - no knowledge base is consulted.
"""
from __future__ import annotations

import re

from app.core.logging import get_logger
from app.models.schemas import IssueProfile
from app.services.question_intent import (
    _FAILURE_INVENTORY_RE,
    _LIST_INVENTORY_RE,
    classify_query_intent,
    intent_label,
)

logger = get_logger(__name__)

_DRIVE_LETTER_RE = re.compile(r"\b(?:on\s+)?(?:my\s+)?([a-z])\s*:?\s*drive\b", re.I)
_DRIVE_PATH_RE = re.compile(r"\b([a-z]):\\", re.I)


def extract_target_drive(text: str) -> str | None:
    """Return a drive letter like 'D:' when the user names a specific drive."""
    if not text:
        return None
    m = _DRIVE_LETTER_RE.search(text)
    if m:
        return f"{m.group(1).upper()}:"
    m = _DRIVE_PATH_RE.search(text)
    if m:
        return f"{m.group(1).upper()}:"
    return None


# Domain -> trigger keywords. Order matters only for tie-breaking readability.
# Keep keywords lowercase; matching is case-insensitive and word-boundary aware
# where it helps avoid false positives (e.g. "bt" only as a standalone token).
_DOMAIN_KEYWORDS: dict[str, list[str]] = {
    "bluetooth": [
        "bluetooth", "blue tooth", "bt", "pair", "pairing", "paired", "unpair",
        "airpods", "earbuds", "headset", "headphones", "headphone", "earphones",
    ],
    "wifi": [
        "wifi", "wi-fi", "wi fi", "wireless", "ssid", "hotspot", "router",
        "access point", "wlan", "connected to wifi", "connected to wi-fi",
        "connected to any wifi", "connected to any wi-fi", "on wifi", "on wi-fi",
        "am i on wifi", "am i on wi-fi", "using wifi", "using wi-fi",
    ],
    "network": [
        "internet", "network", "ethernet", "lan", "dns", "ip address", "no connection",
        "can't connect", "cant connect", "offline", "gateway", "ping", "packet loss",
        "proxy", "vpn", "bandwidth", "data usage", "network requests", "outbound",
        "external server", "external servers", "uploading", "downloading",
        "network traffic", "connecting to", "listening port", "listening ports",
        "which ports", "ports are open", "open port", "open ports", "nas",
        "devices on my network", "devices on the network", "network devices",
        "what servers", "servers online", "servers are available", "switches online",
        "routers online", "access points", "network shares", "shared folders",
        "shared drive", "network resource", "network adapter", "active adapter",
        "dns servers", "what is my ip", "network services", "wifi signal",
    ],
    "application": [
        "what software", "software installed", "software is installed",
        "installed software", "installed applications", "list software", "list apps",
        "what applications", "largest application", "largest app", "biggest application",
        "biggest app", "uninstall", "rarely used", "background app", "background apps",
        "out of date app", "outdated application", "failed update", "app dependencies",
        "software dependencies", "installed silently", "silently installed",
        "highest crash rate", "running in the background", "not been used",
    ],
    "audio": [
        "sound", "audio", "speaker", "speakers", "no sound", "mute", "muted",
        "microphone", "mic", "volume", "playback", "headset audio",
        "audio devices", "audio device", "sound devices", "devices connected",
    ],
    "printer": [
        "printer", "print", "printing", "spooler", "scan", "scanner", "fax",
        "queue stuck", "won't print", "wont print",
        "how many printer", "printers on", "printers in", "printers available",
        "network printer", "printers on my network", "printers in my network",
    ],
    "display": [
        "monitor", "display", "screen", "resolution", "hdmi", "displayport",
        "external monitor", "second screen", "flicker", "gpu", "graphics",
        "refresh rate", "no signal",
    ],
    "webcam": [
        "webcam", "web cam", "camera", "integrated camera", "built-in camera",
        "video call", "video chat", "0xa00f4244", "imaging device", "facetime",
        "black screen camera", "can't find your camera", "cant find your camera",
        "camera not", "camera won't", "camera wont", "camera doesn't", "camera doesnt",
    ],
    "usb": [
        "usb", "flash drive", "pendrive", "pen drive", "thumb drive", "external drive",
        "not recognized", "usb device", "unknown device",
    ],
    "storage": [
        "disk full", "disk space", "low space", "storage", "c drive", "c: drive",
        "d drive", "d: drive", "e drive", "e: drive",
        "hard drive", "ssd", "hdd", "out of space", "no space",
        "free up space", "free up", "clean up", "cleanup", "what can i delete",
        "safe to delete", "taking up space", "taking the most", "taking more space",
        "using the most space", "consuming storage",
        "consuming space", "recover space", "recoverable", "disk usage", "running out of space",
        "what is using", "what's using", "largest files", "largest folders", "delete safely",
        "which file", "what file", "biggest file", "largest file", "most space", "more space",
        "safely delete", "how much space", "space is", "docker", "wsl",
        "temporary files", "temp files", "cache files", "junk files", "downloads",
        "never accessed", "can be archived", "archived", "grew the most", "growing",
        "growing rapidly", "storage trend", "increase suddenly", "increased suddenly",
        "logs consume", "log files", "duplicate", "duplicated", "duplicates",
        "consume the most storage", "consuming the most storage", "largest installed",
        "biggest application", "largest application", "disk full", "why is my disk",
    ],
    "performance": [
        "slow", "sluggish", "lag", "laggy", "freeze", "freezing", "froze", "frozen",
        "hang", "hanging", "not responding", "unresponsive", "stopped working",
        "high cpu", "high ram", "high memory", "100%", "overheating",
        "fan", "uptime", "restart", "reboot", "crashed", "crash", "blue screen", "bsod",
        "what happened", "froze up", "locked up",
        # Resource-usage questions ("what's my CPU/RAM usage", "which app uses most RAM").
        "cpu", "ram", "memory", "processor", "cpu usage", "ram usage",
        "memory usage", "processor usage", "system usage", "resource usage",
        "resource", "resources", "resource monitor", "task manager",
        "using the most", "most ram", "most memory", "most cpu", "using ram",
        "using memory", "using cpu", "consuming cpu", "consuming ram",
        "consuming memory", "hogging", "eating ram", "eating memory", "eating cpu",
        "which app", "which process", "which program", "what app", "what process",
        "what's eating", "whats eating", "usage right now",
    ],
    "windows_update": [
        "windows update", "update", "updates", "patch", "kb5", "feature update",
        "pending restart", "update failed", "stuck update", "0x8",
    ],
    "mouse": [
        "mouse", "touchpad", "trackpad", "pointer", "cursor not", "pointing device",
        "mouse pointer", "left click", "right click", "double click", "scroll wheel",
    ],
    "keyboard": [
        "keyboard", "keys not", "typing", "key not working", "keystrokes",
        "numpad", "function key", "shortcut keys",
    ],
    "battery": [
        "battery", "charging", "not charging", "plugged in", "power", "drain",
        "battery life",
    ],
    "boot": [
        "boot", "won't boot", "wont boot", "not booting", "startup", "bsod", "blue screen",
        "black screen", "bootloop", "won't start", "wont start", "not starting", "no boot",
        "not opening", "won't open", "wont open", "will not open", "not turning on",
        "won't turn on", "wont turn on", "will not turn on", "turn on", "not power on",
        "no power", "dead", "not booting up",
        "pc not", "pc won't", "pc wont", "computer not", "computer won't", "computer wont",
        "laptop not", "laptop won't", "laptop wont",
    ],
    "security": [
        "defender", "antivirus", "virus", "malware", "firewall", "threat",
        "real-time protection", "ransomware", "quarantine",
        "security setting", "disabled", "suspicious", "unsigned", "privilege",
        "privilege escalation", "unusual activity", "listening on", "open port",
        "open ports", "external server", "exfiltration", "risk profile",
        "communicating externally", "running from unusual", "unusual location",
        "tamper", "secure boot", "scheduled task", "scheduled tasks",
        "security risk", "security risks", "how secure", "vulnerabilit",
        "secure is this", "security vulnerabilit", "security posture",
        "suspicious process", "suspicious service", "suspicious network",
        "suspicious registry", "suspicious startup", "elevated privilege",
        "unauthorized", "security score", "registry entries",
    ],
    "account": [
        "password", "sign in", "sign-in", "login", "log in", "locked out",
        "pin", "hello", "bitlocker", "credential", "account",
        "administrator", "admin access", "admin account", "administrator access",
        "who has admin", "user account", "user accounts",
    ],
    "crash": [
        "crash", "crashed", "crashes", "crashing", "bsod", "blue screen",
        "blue-screen", "bugcheck", "stop code", "stop error", "minidump",
        "dump file", "kernel-power", "unexpected shutdown", "hang", "hung",
        "froze", "freeze", "instability", "unstable", "faulting", "appcrash",
    ],
    "driver": [
        "driver", "drivers", "driver update", "driver updates", "driver conflict", "driver error",
        "outdated driver", "out of date driver", "outdated drivers", "out of date drivers",
        "missing driver", "device driver", "code 28", "code 43", "code 10", "driver version",
        "rollback driver", "wdf", "needs update", "need update", "needs updates", "need updates",
        "requires update", "update my drivers", "update drivers", "check drivers", "driver status",
    "which drivers", "drivers failing", "failing drivers", "driver error", "driver errors",
        "driver problem", "driver problems", "failed driver", "failed drivers",
    ],
    "windows": [
        "windows update", "windows component", "windows service", "windows feature",
        "windows error", "windows health", "windows recently", "kb5", "kb4",
        "feature update", "servicing", "cbs", "sfc", "dism", "winsxs",
        "system file", "windows broke", "after windows update",
        "version of windows", "which windows", "windows version", "windows edition",
        "activation", "activated", "windows warning", "windows warnings",
        "windows issue", "windows issues", "windows errors", "windows features",
        "windows components", "needs attention",
    ],
    "change": [
        "what changed", "what's changed", "whats changed", "recently changed",
        "changed recently", "recently installed", "recently updated",
        "what was installed", "newly installed", "new software", "new driver",
        "new service", "registry change", "registry-related", "config change",
        "configuration change", "before the issue", "before it started",
        "before performance", "before crashes", "what changed before",
    ],
    "windows_health": [
        "sfc", "dism", "system file check", "system file corruption", "corrupt files",
        "corrupted files", "files corrupted", "component store", "windows image",
        "image health", "restorehealth", "checkhealth", "scanhealth",
        "windows recovery", "winre", "system integrity", "repair windows",
        "windows corruption", "should i run sfc", "should i run dism",
    ],
    "compliance": [
        "compliance", "compliant", "audit", "hardening", "harden", "baseline",
        "cis benchmark", "security posture", "policy compliance", "encryption compliance",
        "are we compliant", "am i compliant", "compliance check", "compliance score",
    ],
    "user_activity": [
        "login history", "logon history", "who logged in", "sign in history",
        "most used app", "most used apps", "most used application", "least used app",
        "app usage", "application usage", "session duration", "active sessions",
        "user activity", "usage history", "frequently used app",
    ],
    "service": [
        "service dependency", "service dependencies", "service failure",
        "disabled service", "disabled services", "list services", "which services",
    ],
    "process": [
        "process tree", "parent process", "child process", "process list",
        "all processes", "list processes",
    ],
    "hardware": [
        "what cpu", "which cpu", "what processor", "cpu do i have",
        "what gpu", "which gpu", "graphics card", "video card", "gpu do i have",
        "how much ram", "ram installed", "ram is installed", "ram do i have",
        "ram slot", "memory slot", "ram available", "upgrade ram", "upgrade my ram",
        "upgrade ssd", "upgrade my ssd", "hardware upgrade", "upgrades possible",
        "motherboard", "mainboard", "chipset", "bios version", "bios am i", "uefi",
        "serial number", "service tag", "asset tag", "what model", "what machine",
        "storage devices", "drives connected", "disks connected", "what drives",
        "what disks", "how healthy is my ssd", "ssd health", "disk health",
        "battery health", "battery wear", "charge cycle", "replace my battery",
        "what monitors", "monitors attached", "monitor supports hdr", "hdr",
        "what usb", "usb devices", "usb connected", "virtualization",
        "thermal throttling", "overheating", "components overheating",
        "hardware component", "which hardware", "what hardware",
        "serial of my machine",         "what storage",
    ],
    "dev_environment": [
        "docker", "kubernetes", "k8s", "node.js", "nodejs", "npm", "python", "pip",
        "git", "wsl", "vs code", "vscode", "cursor", "developer", "dev environment",
        "maven", "gradle", "conda", "java sdk",
    ],
    "ai_environment": [
        "ollama", "lm studio", "lmstudio", "huggingface", "hugging face",
        "pytorch", "tensorflow", "cuda", "rocm", "ai model", "local llm",
        "machine learning", "gpu compute",
    ],
    "reliability": [
        "reliability", "reliability history", "unexpected restart", "shutdown issue",
        "service failure", "driver failure",
    ],
}

# Application name extraction (separate from domains so we can target processes).
# This is a curated fast-path; ANY other installed app is matched dynamically
# against the live inventory (see enrich_with_inventory()).
_APP_KEYWORDS: dict[str, list[str]] = {
    "Outlook": ["outlook"],
    "Microsoft Teams": ["teams", "ms-teams"],
    "Microsoft Word": ["winword"],
    "Microsoft Excel": ["excel"],
    "Microsoft Office": ["office365", "microsoft 365"],
    "Google Chrome": ["chrome"],
    "Microsoft Edge": ["msedge"],
    "Mozilla Firefox": ["firefox"],
    "Zoom": ["zoom"],
    "OneDrive": ["onedrive"],
    "Cursor": ["cursor"],
    "Visual Studio Code": ["vs code", "vscode"],
    "Docker": ["docker"],
    "Git": ["git"],
    "Python": ["python"],
    "Node.js": ["node.js", "nodejs"],
    "Slack": ["slack"],
    "Notion": ["notion"],
    "Postman": ["postman"],
}

# Common English words that should never be treated as an application name when
# matching dynamically against installed software (avoids silly matches).
_APP_STOPWORDS = {
    "the", "and", "for", "this", "that", "with", "not", "working", "open", "opening",
    "start", "starting", "is", "are", "was", "were", "my", "your", "a", "an", "on",
    "off", "to", "of", "it", "in", "won't", "wont", "can't", "cant", "help", "issue",
    "problem", "error", "app", "application", "program", "software", "windows", "pc",
    "computer", "laptop", "system", "machine", "update", "install", "run", "running",
    # Driver-update questions ("which drivers need updates") must not match random apps.
    "driver", "drivers", "updates", "outdated", "out",
    "list", "all", "the", "show", "enumerate", "installed",
}

# Symptom tags - what kind of failure the user describes.
_SYMPTOM_KEYWORDS: dict[str, list[str]] = {
    "not_working": ["not working", "doesn't work", "doesnt work", "won't work", "wont work", "broken"],
    "not_detected": ["not detected", "not recognized", "missing", "disappeared", "not showing", "can't find", "cant find"],
    "cannot_connect": ["can't connect", "cant connect", "won't connect", "wont connect", "no connection", "disconnect", "disconnects", "dropping"],
    "cannot_pair": ["won't pair", "wont pair", "can't pair", "cant pair", "pairing failed"],
    "crash": ["crash", "crashes", "crashing", "closes", "quit unexpectedly"],
    "slow": ["slow", "sluggish", "lag", "freeze", "hang", "not responding"],
    "no_sound": ["no sound", "no audio", "can't hear", "cant hear", "silent"],
    "after_update": ["after update", "after updating", "since the update", "after upgrade", "after windows update"],
    "error_code": ["error", "code 43", "code 10", "error code", "0x"],
    "wont_start": [
        "won't start", "wont start", "will not start", "not starting", "won't open",
        "wont open", "will not open", "not opening", "does not open", "doesn't open",
        "doesnt open", "won't launch", "wont launch", "will not launch", "not launching",
        "not turning on", "won't turn on", "wont turn on", "will not turn on",
        "not booting", "won't boot", "wont boot", "no power", "dead",
    ],
}

# Domains that have a dedicated live probe pack implemented.
_PROBE_DOMAINS = {
    "bluetooth", "wifi", "network", "audio", "printer", "display", "usb",
    "storage", "performance", "windows_update", "application", "mouse", "keyboard",
    "webcam", "crash", "driver", "windows", "security", "change",
}

# Some domains imply running additional probe packs.
_DOMAIN_EXPANSION: dict[str, list[str]] = {
    "wifi": ["wifi", "network"],
    "boot": ["performance", "windows_update", "startup"],
    "battery": ["performance"],
    "security": ["security", "windows_update"],
    "account": ["windows_update"],
    "mouse": ["mouse", "usb"],
    "keyboard": ["keyboard", "usb"],
    "webcam": ["webcam", "usb"],
    "crash": ["crash", "performance", "driver", "windows"],
    "driver": ["driver", "windows_update"],
    "windows": ["windows", "windows_update"],
    "change": ["change", "windows", "security"],
    "windows_health": ["windows_health", "windows"],
    "compliance": ["compliance", "security"],
}

# ------------------------------------------------------------------ #
#  Holistic analysis intent (forensic / predictive / reasoning / executive)
# ------------------------------------------------------------------ #
_EXECUTIVE_RE = re.compile(
    r"\b(explain|summar(?:y|ize|ise)|overview|report|risk\s+assessment|"
    r"health\s+(?:check|report|summary)|brief\s+me|1[\s-]?minute|5[\s-]?minute|"
    r"one[\s-]?minute|five[\s-]?minute|like\s+i'?m|complete\s+technical\s+report|"
    r"top\s+\d+\s+issues?|top\s+(?:five|5|three|3)\s+issues?|top\s+issues|"
    r"(?:health|security|performance|reliability|storage|compliance|network)\s+score|"
    r"give\s+me\s+a\s+\w+\s+score|a\s+score|remediation\s+plan|fix\s+first|"
    r"what\s+should\s+i\s+fix|biggest\s+impact|issue\s+has\s+the\s+biggest|"
    r"machine\s+health|maintenance\s+should\s+i|"
    r"remediation\s+(?:plan|roadmap|report)|roadmap|prioriti[sz]e|"
    r"this\s+month|next\s+month|business\s+impact|impact[\s-]to[\s-]effort|"
    r"what\s+should\s+it|highest\s+impact)\b",
    re.I,
)
_PREDICTIVE_RE = re.compile(
    r"\b(most\s+likely\s+to\s+occur|likely\s+to\s+fail|failure\s+probability|"
    r"will\s+\w+\s+become|trending\s+toward|developing\s+over\s+time|"
    r"prevent\s+future|going\s+to\s+(?:fail|break|happen)|predict|forecast|"
    r"highest\s+failure|most\s+likely\s+to\s+fail|become\s+a\s+problem\s+soon|"
    r"closest\s+to\s+failure|most\s+likely\s+to\s+occur\s+next|will\s+disk\s+space|"
    r"trending|fixed\s+now\s+to\s+prevent|highest\s+failure\s+probability|"
    r"operational\s+risk|prepare\s+for|what\s+failure|proactive(?:ly)?|"
    r"biggest\s+risk|trend\s+concerns?|what\s+trend|future\s+\w+|will\s+my\s+\w+\s+fail|"
    r"run\s+out\s+of\s+(?:disk|storage)|highest\s+failure\s+risk|"
    r"immediate\s+action|requires?\s+immediate|risk\s+requires|"
    r"most\s+concerning|highest\s+failure\s+probability)\b",
    re.I,
)
_REASONING_RE = re.compile(
    r"\b(biggest\s+issue|top\s+(?:three|3|few)\s+(?:root\s+)?causes|root\s+cause|"
    r"if\s+you\s+could\s+fix\s+only|fix\s+only\s+one|impact[\s-]to[\s-]effort|"
    r"most\s+strongly\s+supports|contradicts\s+your|how\s+confident|"
    r"what\s+assumptions|additional\s+information|incident\s+report|"
    r"single\s+biggest|most\s+likely\s+cause|find\s+the\s+(?:most\s+likely\s+)?cause|"
    r"biggest\s+(?:performance\s+)?bottleneck|biggest\s+\w+\s+bottleneck|"
    r"what\s+evidence|logs?\s+explain)\b",
    re.I,
)
_FORENSIC_RE = re.compile(
    r"\b(what\s+changed|over\s+the\s+last\s+\d+\s+days?|in\s+the\s+last\s+\d+\s+days?|"
    r"this\s+week|today|yesterday|last\s+week|last\s+month|over\s+time|"
    r"gradually\s+degrad|chronological|all\s+(?:available\s+)?telemetry|"
    r"using\s+all\s+|history|forensic|timeline|compared?\s+to\s+last|"
    r"grew\s+the\s+fastest|growing|most\s+often|most\s+frequently|"
    r"highest\s+crash\s+rate|over\s+the\s+last|memory\s+leak|"
    r"who\s+(?:disabled|enabled|changed|installed|removed)|"
    r"most\s+(?:bandwidth|errors|data|requests|warnings|background)|"
    r"causes?\s+the\s+most|increasing|boot\s+time\s+increasing|"
    r"never\s+(?:use|used|accessed)|use\s+most|used\s+most|"
    r"wastes?\s+the\s+most|fastest|highest\s+\w+\s+rate|"
    r"recently|ever\s+been\s+disabled|grown\s+the\s+most|"
    r"unused|appeared\s+recently|added\s+(?:in|recently)|"
    r"correlate|correlation|correlates?\s+with|relationship\s+between|"
    r"link(?:ed)?\s+to|tie\s+together|degrad(?:e|ing|ation)|"
    r"progressively|abnormal(?:ly)?|conflicts?\b|redundant|"
    r"persistence\s+mechanisms?|bypass|excessive|"
    r"introduced\s+(?:instability|failures?)|consistently\s+impacts?|"
    r"reconstruct|incident|postmortem|post-mortem|sequence\s+of\s+events|"
    r"systems?\s+were\s+involved|what\s+occurred|build\s+a\s+timeline|"
    r"root[\s-]cause\s+analysis|before\s+the\s+(?:issue|crash|incident)|"
    r"minutes\s+before|what\s+systems|evidence\s+exists|"
    r"inconsistent|throughout\s+the\s+day|risky\s+action|performed\s+risky|"
    r"usage\s+pattern|workflows?|stress\s+the\s+system|ineffective|"
    r"unreachable|recurring\s+pattern|contribute\s+to)\b",
    re.I,
)

_AUDIENCE_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("cio", re.compile(r"\bcio\b|executive\s+risk|c-level|chief", re.I)),
    ("sysadmin", re.compile(r"system\s+admin|sysadmin|administrator", re.I)),
    ("helpdesk", re.compile(r"help\s*desk|support\s+engineer|technician", re.I)),
    ("user", re.compile(r"non[\s-]?technical|like\s+i'?m\s+a?\s*(?:non|new|begin|regular|normal)", re.I)),
]

_TIME_SCOPE_RE = re.compile(
    r"\b(today|yesterday|this\s+week|last\s+week|this\s+month|last\s+month|"
    r"last\s+night|this\s+morning|this\s+afternoon|over\s+the\s+last\s+\d+\s+days?|"
    r"in\s+the\s+last\s+\d+\s+days?|last\s+\d+\s+days?)\b",
    re.I,
)


def detect_analysis_mode(text: str) -> str | None:
    """Classify a holistic/forensic question. Returns the mode or None.

    Order matters: executive (presentation) and reasoning (meta) intents win over
    generic forensic phrasing, because they change how the answer is written.
    """
    t = text or ""
    # Simple factual score/status questions are informational — not executive briefings.
    if re.search(
        r"^\s*what(?:'s|\s+is)\s+my\s+(?:machine\s+)?(?:health|compliance|security|performance)\s+score\b",
        t,
        re.I,
    ):
        return None
    if _EXECUTIVE_RE.search(t):
        return "executive"
    if _REASONING_RE.search(t):
        return "reasoning"
    if _PREDICTIVE_RE.search(t):
        return "predictive"
    if _FORENSIC_RE.search(t):
        return "forensic"
    return None


def detect_audience(text: str) -> str | None:
    for name, pat in _AUDIENCE_PATTERNS:
        if pat.search(text or ""):
            return name
    return None


def detect_time_scope(text: str) -> str | None:
    m = _TIME_SCOPE_RE.search(text or "")
    return m.group(0).lower() if m else None


def _count_hits(text: str, keywords: list[str]) -> tuple[int, list[str]]:
    hits: list[str] = []
    for kw in keywords:
        # Use word boundaries for short/ambiguous tokens to avoid false hits.
        if len(kw) <= 3 or kw.isalpha() and " " not in kw and len(kw) <= 4:
            if re.search(rf"(?<![a-z0-9]){re.escape(kw)}(?![a-z0-9])", text):
                hits.append(kw)
        elif " " in kw or ":" in kw:
            # Avoid "e drive" matching inside "the drivers".
            if re.search(rf"(?<![a-z0-9]){re.escape(kw)}(?![a-z0-9])", text):
                hits.append(kw)
        elif kw in text:
            hits.append(kw)
    return len(hits), hits


def parse_issue(message: str, ocr_text: str | None = None) -> IssueProfile:
    """Parse free text into a structured issue profile."""
    text = f"{message or ''}\n{ocr_text or ''}".lower()

    # Score every domain by keyword hits.
    scores: dict[str, int] = {}
    for domain, keywords in _DOMAIN_KEYWORDS.items():
        n, _ = _count_hits(text, keywords)
        if n:
            scores[domain] = n

    apps: list[str] = []
    for app, keywords in _APP_KEYWORDS.items():
        n, _ = _count_hits(text, keywords)
        if n:
            apps.append(app)

    symptoms: list[str] = []
    for sym, keywords in _SYMPTOM_KEYWORDS.items():
        n, _ = _count_hits(text, keywords)
        if n:
            symptoms.append(sym)

    # Rank domains; keep those within the top tier (>= best-1) to allow multi-domain.
    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    selected: list[str] = []
    if ranked:
        best = ranked[0][1]
        for domain, score in ranked:
            if score >= max(1, best - 1):
                selected.append(domain)

    # If an app was named but no domain matched, treat it as an application issue.
    if apps and not selected:
        selected.append("application")

    # App context vs whole-PC context: "outlook won't open" is an application
    # problem, not a boot problem. Only keep 'boot' when the user clearly refers
    # to the whole machine (pc/computer/laptop/...) - otherwise an app launch
    # failure should route to the application probe.
    if apps and "boot" in selected:
        has_pc_context = re.search(
            r"\b(pc|computer|laptop|machine|desktop|system|windows)\b", text
        ) is not None
        if not has_pc_context:
            selected = [d for d in selected if d != "boot"]
            if "application" not in selected:
                selected.insert(0, "application")

    primary = selected[0] if selected else None

    # Confidence: based on strength + clarity of the top signal.
    confidence = 0.0
    if ranked:
        top = ranked[0][1]
        confidence = min(0.95, 0.45 + 0.18 * top)
    elif apps:
        confidence = 0.55

    # Symptom-only messages (e.g. "not working") still warrant a live scan.
    if not selected and not apps and symptoms:
        selected.append("usb")

    # Holistic / forensic / executive intent: these questions reason across the
    # whole machine, so they never need clarification even if no single domain matched.
    analysis_mode = detect_analysis_mode(text)
    audience = detect_audience(text) if analysis_mode == "executive" else None
    time_scope = detect_time_scope(text)
    query_intent = classify_query_intent(message or "", analysis_mode)

    # Focused inventory questions should answer only what was asked.
    if query_intent == "inventory" and primary and len(selected) > 1:
        if _LIST_INVENTORY_RE.search(text) or _FAILURE_INVENTORY_RE.search(text):
            selected = [primary]

    needs_clarification = False
    clarification = None
    if not selected and not apps and not analysis_mode:
        needs_clarification = True
        clarification = (
            "Could you tell me a bit more about the problem? For example: is it about "
            "the internet/Wi-Fi, Bluetooth, sound, webcam/camera, a printer, the display, "
            "a specific app, or the PC feeling slow?"
        )

    # A holistic question with no specific domain still gets a confident profile.
    if analysis_mode and not selected:
        primary = primary or "performance"
        if confidence < 0.6:
            confidence = 0.7

    profile = IssueProfile(
        domains=selected,
        primary_domain=primary,
        apps=apps,
        symptoms=symptoms,
        confidence=round(confidence, 2),
        needs_clarification=needs_clarification,
        clarification_question=clarification,
        target_drive=extract_target_drive(text),
        analysis_mode=analysis_mode,
        audience=audience,
        time_scope=time_scope,
        query_intent=query_intent,
    )
    logger.info(
        "Parsed issue -> domains=%s apps=%s symptoms=%s conf=%.2f intent=%s mode=%s",
        profile.domains, profile.apps, profile.symptoms, profile.confidence,
        intent_label(query_intent), profile.analysis_mode or "-",
    )
    return profile


def enrich_with_inventory(
    profile: IssueProfile,
    message: str,
    installed_app_names: list[str],
    process_names: set[str],
) -> IssueProfile:
    """Dynamically match the user's words against the machine's REAL installed
    apps and running processes, so any application (not just the curated list)
    is recognised. Also resolves the ambiguous word "cursor" (the editor vs the
    mouse pointer) based on what's actually present.
    """
    text = (message or "").lower()
    tokens = set(re.findall(r"[a-z0-9.+#-]{3,}", text)) - _APP_STOPWORDS

    matched_apps: list[str] = list(profile.apps)

    # 1. Match tokens against installed application display names.
    installed_lower = [(n, n.lower()) for n in installed_app_names]
    for tok in tokens:
        for orig, low in installed_lower:
            if re.search(rf"(?<![a-z0-9]){re.escape(tok)}(?![a-z0-9])", low) and orig not in matched_apps:
                # Prefer a concise product name (first 4 words).
                short = " ".join(orig.split()[:4])
                if short not in matched_apps:
                    matched_apps.append(short)
                break

    # 2. Match tokens against running process base names (e.g. "cursor" -> cursor.exe).
    for tok in tokens:
        for pname in process_names:
            base = pname[:-4] if pname.endswith(".exe") else pname
            if tok == base and not any(tok in a.lower() for a in matched_apps):
                matched_apps.append(tok.capitalize())
                break

    # 3. Resolve "cursor": editor (installed/running) vs mouse pointer.
    if "cursor" in tokens:
        has_cursor_app = any("cursor" in n.lower() for n in installed_app_names) \
            or any(p.startswith("cursor") for p in process_names)
        if has_cursor_app:
            if not any("cursor" in a.lower() for a in matched_apps):
                matched_apps.append("Cursor")
        else:
            if "mouse" not in profile.domains:
                profile.domains.append("mouse")

    # Dedupe overlapping names (keep the shortest representative, e.g. prefer
    # "Cursor" over "Cursor (User)").
    deduped: list[str] = []
    for a in sorted(matched_apps, key=len):
        al = a.lower()
        if any(al in d.lower() or d.lower() in al for d in deduped):
            continue
        deduped.append(a)
    profile.apps = deduped

    domains = list(profile.domains)
    if deduped and "application" not in domains:
        # Don't pull generic app context into driver/device inventory questions.
        from app.services.machine_scan_info import is_list_audio_devices_question, is_list_drivers_question
        if not is_list_drivers_question(message) and not is_list_audio_devices_question(message):
            domains.append("application")
    profile.domains = domains
    profile.primary_domain = domains[0] if domains else profile.primary_domain

    if profile.domains or profile.apps or profile.symptoms:
        profile.needs_clarification = False
        profile.clarification_question = None
        if profile.confidence < 0.5:
            profile.confidence = 0.6

    logger.info(
        "Inventory-enriched issue -> domains=%s apps=%s",
        profile.domains, profile.apps,
    )
    return profile


def plan_probe_domains(profile: IssueProfile) -> list[str]:
    """Expand the parsed domains into the concrete probe packs to run."""
    planned: list[str] = []

    def add(d: str) -> None:
        if d in _PROBE_DOMAINS and d not in planned:
            planned.append(d)

    for d in profile.domains:
        for expanded in _DOMAIN_EXPANSION.get(d, [d]):
            add(expanded)

    # Always run the application probe when a specific app was named.
    if profile.apps:
        add("application")

    return planned
