"""Conversational replies for non-troubleshooting chat.

The diagnosis/answer path is fully deterministic and lives in
``InvestigationService``. This module only handles greetings, thanks and
"what can you do" small talk - no AI model is involved.
"""
from __future__ import annotations

from app.core.logging import get_logger
from app.models.schemas import DiagnosisResult, Severity
from app.utils.message_intent import Intent, classify_message

logger = get_logger(__name__)


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
    """Handles short conversational replies (greetings / thanks / capabilities)."""

    def conversational_response(self, message: str) -> DiagnosisResult:
        """Short reply for greetings and other non-troubleshooting chat."""
        intent = classify_message(message)
        if intent == "troubleshooting":
            intent = "greeting"
        text = _CONVERSATIONAL_REPLIES.get(intent, _CONVERSATIONAL_REPLIES["greeting"])
        return DiagnosisResult(
            issue_summary=text,
            is_conversational=True,
            severity=Severity.healthy,
            confidence=100,
        )
