"""Automatic query-intent classification for the diagnosis pipeline.

Every user question is classified before findings are built:

- **troubleshooting** — something is broken, failing, or misbehaving; run fault
  handlers and surface fix steps.
- **informational** — factual status or specs (CPU, IP, is Wi-Fi on, battery
  health, etc.); answer from scan data, no fault template.
- **inventory** — enumerate or count devices, apps, printers, network hosts;
  same response path as informational but triggered by list/count phrasing.
- **holistic** — cross-cutting forensic / predictive / executive questions; uses
  ``analysis_mode`` on the issue profile.

Classification is deterministic (regex + priority rules) and runs inside
``parse_issue`` so the intent is available everywhere downstream.
"""
from __future__ import annotations

import re
from typing import Literal

QueryIntent = Literal["troubleshooting", "informational", "inventory", "holistic"]

# Strong troubleshooting markers — if present, this is NOT a scan-only question.
TROUBLE_RE = re.compile(
    r"\b(why|not\s+working|won'?t|can'?t|cannot|broken|failing|failed|fix|"
    r"crash|crashes|crashing|slow|lag|freeze|freezing|stuck|hang|error|"
    r"disconnect|dropping|isn'?t|doesn'?t|stopped\s+working|keeps|"
    r"won't\s+print|wont\s+print|queue\s+stuck|no\s+sound|black\s+screen|"
    r"blue\s+screen|bsod|offline|unreachable)\b",
    re.I,
)

# Informational lead-ins (question is asking for a fact, not reporting a fault).
INFO_LEAD_RE = re.compile(
    r"^\s*(what|which|how|who|is\s|are\s|does\s|"
    r"do\s|can\s|list|show|tell\s+me|give\s+me|should\s+i)\b",
    re.I,
)

# Connection / status checks without trouble markers.
STATUS_RE = re.compile(
    r"\b("
    r"(?:is|are|am)\s+(?:my\s+)?(?:laptop|pc|computer|machine|this\s+pc)?\s*"
    r"(?:connected|on|using|enabled|running)|"
    r"connected\s+to\s+(?:any\s+)?(?:printer|wifi|wi-?fi|bluetooth|device)s?|"
    r"(?:audio|sound|microphone|mic|speaker|headphone|headset).{0,40}?devices?\s+connected|"
    r"devices?\s+connected.{0,40}?(?:audio|sound|microphone|mic|speaker|bluetooth)\b|"
    r"any\s+printers?\s+connected|"
    r"do\s+i\s+have|"
    r"what\s+is\s+my|what'?s\s+my|"
    r"how\s+much\s+(?:ram|memory|storage|disk|space|battery)|"
    r"how\s+healthy|"
    r"is\s+(?:antivirus|defender|firewall|bitlocker|encryption)\b"
    r")\b",
    re.I,
)

# List / count / enumerate phrasing — inventory intent.
INVENTORY_RE = re.compile(
    r"\b("
    r"how\s+many|"
    r"list\s+(?:all\s+)?|"
    r"show\s+(?:me\s+)?(?:all\s+)?|"
    r"what\s+(?:devices|printers|apps|applications|software|monitors|drives|drivers|servers|audio|microphone|mic|speaker|cameras|webcams)|"
    r"which\s+(?:devices|printers|apps|applications|software|monitors|drives|drivers|audio|microphone|mic|speaker|cameras)|"
    r"(?:devices|printers|apps|servers|shares|folders)\s+(?:on|in|available)|"
    r"available\s+(?:on|in)\s+(?:my\s+)?(?:network|lan)|"
    r"on\s+(?:my|the)\s+network|"
    r"installed\s+(?:software|applications|apps)|"
    r"enumerate|inventory|"
    r"printers?\s+(?:are\s+)?(?:available|on|in)\b"
    r")\b",
    re.I,
)


_LIST_INVENTORY_RE = re.compile(
    r"\b(how\s+many|list\s+(?:all\s+)?|show\s+(?:me\s+)?(?:all\s+)?|enumerate|inventory)\b",
    re.I,
)
# "Which drivers are failing?" — inventory of faults, not a generic troubleshooting flow.
_FAILURE_INVENTORY_RE = re.compile(
    r"\b(?:which|what|list|show|any|are\s+there|tell\s+me)\b.{0,60}?"
    r"\b(?:fail(?:ing|ed)|broken|error|problem|wrong)\b",
    re.I,
)
_ENUMERATE_WHAT_RE = re.compile(
    r"\b(?:what|which)\s+(?:devices|printers|apps|applications|software|monitors|drives|servers|audio|microphone|mic|speaker|cameras|webcams)\b",
    re.I,
)
_ON_NETWORK_RE = re.compile(r"\bon\s+(?:my|the)\s+network\b", re.I)
# Bare "audio devices" / "sound devices" — inventory, not a speaker fault report.
_AUDIO_DEVICE_NOUN_RE = re.compile(
    r"\b(?:audio|sound|microphone|mic|speaker|headphone|headset)\s+devices?\b|"
    r"\bdevices?\s+(?:for\s+)?(?:audio|sound)\b",
    re.I,
)


def classify_query_intent(message: str, analysis_mode: str | None = None) -> QueryIntent:
    """Classify a user message into troubleshooting, informational, inventory, or holistic."""
    if analysis_mode:
        return "holistic"

    msg = (message or "").strip()
    if not msg:
        return "troubleshooting"

    # "Which drivers are failing?" / "what devices have errors?" — status inventory.
    if _FAILURE_INVENTORY_RE.search(msg):
        return "informational"

    # Fault / breakage language always wins.
    if TROUBLE_RE.search(msg):
        return "troubleshooting"

    # "audio devices", "sound devices" — enumerate endpoints, not troubleshoot output.
    if _AUDIO_DEVICE_NOUN_RE.search(msg):
        return "inventory"

    has_status = bool(INFO_LEAD_RE.search(msg) or STATUS_RE.search(msg))
    has_inventory = bool(INVENTORY_RE.search(msg))

    if (
        _LIST_INVENTORY_RE.search(msg)
        or _ENUMERATE_WHAT_RE.search(msg)
        or (_ON_NETWORK_RE.search(msg) and has_inventory)
    ):
        return "inventory"

    # Explicit list/count phrasing, or enumerate patterns without a status check.
    if has_inventory and not has_status:
        return "inventory"

    if has_status:
        return "informational"

    if has_inventory:
        return "inventory"

    return "troubleshooting"


def is_scan_only_intent(intent: str | None) -> bool:
    """True when the answer should come from scan facts, not fault handlers."""
    return intent in ("informational", "inventory")


def is_troubleshooting_intent(intent: str | None) -> bool:
    return intent in (None, "troubleshooting")


def intent_label(intent: str | None) -> str:
    """Human-readable label for logs and debugging."""
    return {
        "troubleshooting": "fault detection",
        "informational": "informational",
        "inventory": "inventory check",
        "holistic": "holistic analysis",
    }.get(intent or "", "fault detection")
