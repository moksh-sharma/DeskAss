"""Classify user chat messages before running the diagnosis pipeline."""
from __future__ import annotations

import re
from typing import Literal

Intent = Literal["greeting", "thanks", "capabilities", "troubleshooting"]

_GREETING = re.compile(
    r"^(?:hi|hello|hey|hiya|howdy|yo|sup|good\s+(?:morning|afternoon|evening))"
    r"(?:\s+there)?[\s!.?]*$",
    re.IGNORECASE,
)
_THANKS = re.compile(r"^(?:thanks?|thank\s+you|thx|ty|appreciated)[\s!.?]*$", re.IGNORECASE)
_CAPABILITIES = re.compile(
    r"^(?:what\s+can\s+you\s+do|how\s+can\s+you\s+help|help\??|what\s+do\s+you\s+do)[\s!.?]*$",
    re.IGNORECASE,
)
_PROBLEM_HINT = re.compile(
    r"\b(?:"
    r"crash(?:es|ed|ing)?|slow|error|fail(?:ed|s|ing)?|broken|not\s+work(?:ing)?|"
    r"won'?t|can'?t|cannot|unable|issue|problem|fix|troubleshoot|stuck|dead|"
    r"open(?:ing)?|launch|start(?:ing|up)?|turn\s*on|power|"
    r"blue\s*screen|black\s*screen|bsod|freeze(?:s|z|ing)?|hang(?:s|ing)?|disconnect(?:ed|s|ing)?|"
    r"outlook|teams|vpn|wifi|wi-?fi|bluetooth|printer|scanner|audio|sound|speaker|mic(?:rophone)?|"
    r"monitor|display|screen|usb|webcam|camera|update|install|battery|charging|"
    r"event\s+id|\.net\s+runtime|out\s+of\s+memory|disk\s+full|"
    r"cpu|ram|memory|processor|resource|task\s+manager|"
    r"(?:cpu|ram|memory|system|resource)\s+usage|using\s+the\s+most|"
    r"which\s+app|which\s+process|hogging|"
    r"disk\s+space|low\s+space|most\s+space|more\s+space|taking\s+\S+\s+space|"
    r"which\s+file|what\s+file|largest\s+file|biggest\s+file|largest\s+folder|"
    r"free\s+up|cleanup|clean\s+up|[a-z]\s*:?\s*drive|"
    r"password|login|network|internet|driver|boot|restart|reboot|"
    r"what\s+changed|root\s+cause|most\s+likely|risk\s+assessment|"
    r"machine\s+health|incident\s+report|gradually\s+degrad|"
    r"crash|bsod|defender|antivirus|firewall|forensic|"
    r"pc|computer|laptop|machine|device|adapter|service"
    r")\b",
    re.IGNORECASE,
)


def classify_message(text: str) -> Intent:
    """Return whether the message needs full IT diagnosis or a short reply."""
    msg = text.strip()
    if not msg:
        return "greeting"

    # Strict conversational patterns take precedence over everything else.
    if _GREETING.match(msg):
        return "greeting"
    if _THANKS.match(msg):
        return "thanks"
    if _CAPABILITIES.match(msg):
        return "capabilities"

    # Event-log paste or long descriptions are always troubleshooting.
    if len(msg) >= 60 or _PROBLEM_HINT.search(msg):
        return "troubleshooting"

    # Delegate ambiguous short text to the issue parser: if it recognises any
    # technical domain, app, or symptom, treat it as a real problem to scan.
    # (Imported lazily to avoid any import cycle / startup cost.)
    try:
        from app.services.issue_parser import parse_issue

        profile = parse_issue(msg)
        if profile.domains or profile.apps or profile.symptoms or profile.analysis_mode:
            return "troubleshooting"
    except Exception:
        pass

    # Nothing technical detected - treat as chat.
    return "greeting"


def is_troubleshooting_message(text: str) -> bool:
    return classify_message(text) == "troubleshooting"
