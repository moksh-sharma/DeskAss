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
        "connected", "plugged in",
    ],
    "wifi": [
        "wifi", "wi-fi", "wi fi", "wireless", "ssid", "hotspot", "router",
        "access point", "wlan",
    ],
    "network": [
        "internet", "network", "ethernet", "lan", "dns", "ip address", "no connection",
        "can't connect", "cant connect", "offline", "gateway", "ping", "packet loss",
        "proxy", "vpn",
    ],
    "audio": [
        "sound", "audio", "speaker", "speakers", "no sound", "mute", "muted",
        "microphone", "mic", "volume", "playback", "headset audio",
    ],
    "printer": [
        "printer", "print", "printing", "spooler", "scan", "scanner", "fax",
        "queue stuck", "won't print", "wont print", "connected", "plugged in",
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
    ],
    "performance": [
        "slow", "sluggish", "lag", "laggy", "freeze", "freezing", "froze", "frozen",
        "hang", "hanging", "not responding", "unresponsive", "stopped working",
        "high cpu", "high ram", "high memory", "100%", "overheating",
        "fan", "uptime", "restart", "reboot", "crashed", "crash", "blue screen", "bsod",
        "what happened", "froze up", "locked up",
    ],
    "windows_update": [
        "windows update", "update", "updates", "patch", "kb5", "feature update",
        "pending restart", "update failed", "stuck update", "0x8",
    ],
    "mouse": [
        "mouse", "touchpad", "trackpad", "pointer", "cursor not", "pointing device",
        "mouse pointer", "left click", "right click", "double click", "scroll wheel",
        "connected", "plugged in",
    ],
    "keyboard": [
        "keyboard", "keys not", "typing", "key not working", "keystrokes",
        "numpad", "function key", "shortcut keys", "connected", "plugged in",
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
    ],
    "account": [
        "password", "sign in", "sign-in", "login", "log in", "locked out",
        "pin", "hello", "bitlocker", "credential", "account",
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
    "webcam",
}

# Some domains imply running additional probe packs.
_DOMAIN_EXPANSION: dict[str, list[str]] = {
    "wifi": ["wifi", "network"],
    "boot": ["performance", "windows_update"],
    "battery": ["performance"],
    "security": ["windows_update"],
    "account": ["windows_update"],
    "mouse": ["mouse", "usb"],
    "keyboard": ["keyboard", "usb"],
    "webcam": ["webcam", "usb"],
}


def _count_hits(text: str, keywords: list[str]) -> tuple[int, list[str]]:
    hits: list[str] = []
    for kw in keywords:
        # Use word boundaries for short/ambiguous tokens to avoid false hits.
        if len(kw) <= 3 or kw.isalpha() and " " not in kw and len(kw) <= 4:
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

    needs_clarification = False
    clarification = None
    if not selected and not apps:
        needs_clarification = True
        clarification = (
            "Could you tell me a bit more about the problem? For example: is it about "
            "the internet/Wi-Fi, Bluetooth, sound, webcam/camera, a printer, the display, "
            "a specific app, or the PC feeling slow?"
        )

    profile = IssueProfile(
        domains=selected,
        primary_domain=primary,
        apps=apps,
        symptoms=symptoms,
        confidence=round(confidence, 2),
        needs_clarification=needs_clarification,
        clarification_question=clarification,
        target_drive=extract_target_drive(text),
    )
    logger.info(
        "Parsed issue -> domains=%s apps=%s symptoms=%s conf=%.2f",
        profile.domains, profile.apps, profile.symptoms, profile.confidence,
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
            if tok in low and orig not in matched_apps:
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
