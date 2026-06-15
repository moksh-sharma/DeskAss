"""Classify peripherals as physical hardware vs software/virtual emulations.

Windows often lists virtual devices (Print to PDF, OBS Virtual Camera, Voicemeeter,
Stereo Mix, etc.) alongside or instead of real hardware. Connection answers must
only count physical devices that are actually present.
"""
from __future__ import annotations

import re

# --------------------------------------------------------------------------- #
#  Virtual / software device patterns
# --------------------------------------------------------------------------- #
VIRTUAL_PRINTER_RE = re.compile(
    r"(?i)\b("
    r"onenote|microsoft\s+print\s+to\s+pdf|xps\s+document|microsoft\s+xps|"
    r"fax|pdf\s*writer|snagit|cutepdf|adobe\s+pdf|pdfcreator|bullzip|"
    r"anydesk\s+printer|microsoft\s+shared\s+fax|send\s+to\s+onenote|"
    r"document\s+writer|root\s+print\s+queue|redirected\s+document|"
    r"universal\s+print|microsoft\s+ipp|virtual\s+printer"
    r")\b",
)
VIRTUAL_PRINTER_PORT_RE = re.compile(
    r"(?i)^(portprompt:|nul:|shf:|file:|prompt:|xpsport:|onenote:)",
)

VIRTUAL_AUDIO_RE = re.compile(
    r"(?i)\b("
    r"stereo\s*mix|wave\s*link|voicemeeter|vb-?audio|virtual\s+audio|"
    r"nvidia\s+broadcast|obs\s+audio|krisp|snap\s+camera|iriun|"
    r"droidcam|epoccam|camo\s+audio|manycam|xsplit|elgato\s+virtual|"
    r"steelseries\s+sonar|nahimic|sonic\s+studio|waves\s+maxxaudio\s+virtual|"
    r"what\s+u\s+hear|loopback|virtual\s+cable|cable\s+(input|output)|"
    r"audio\s+relay|soundflower|blackhole"
    r")\b",
)

VIRTUAL_CAMERA_RE = re.compile(
    r"(?i)\b("
    r"obs\s+virtual\s+camera|virtual\s+camera|manycam|snap\s+camera|"
    r"droidcam|epoccam|iriun|camo\s+camera|xsplit\s+v?cam|nvidia\s+broadcast|"
    r"elgato\s+virtual|mmhmm|webcamoid|youcam|altercam|splitcam|"
    r"virtual\s+webcam|avatar\s+camera"
    r")\b",
)

USB_INFRASTRUCTURE_RE = re.compile(
    r"(?i)\b("
    r"host\s+controller|usb\s+root\s+hub|generic\s+usb\s+hub|"
    r"composite\s+device|usb\s+hub|eXtensible\s+Host\s+Controller"
    r")\b",
)

INTERNAL_DISPLAY_CONNECTIONS = frozenset({
    "internal", "lvds", "displayport (embedded)", "udi (embedded)",
})

_CONNECTION_QUESTION_RE = re.compile(
    r"(?i)\b("
    r"connected|plugged\s*in|attached|hooked\s*up|is\s+it\s+on|"
    r"detected|plugged|inserted|present|hooked"
    r")\b",
)


def asks_physical_connection(message: str) -> bool:
    """True when the user is asking whether hardware is physically connected."""
    return bool(_CONNECTION_QUESTION_RE.search(message or ""))


def is_virtual_printer(name: str, driver: str, port: str, typ: str = "") -> bool:
    if str(typ).lower() == "virtual":
        return True
    if VIRTUAL_PRINTER_RE.search(name) or VIRTUAL_PRINTER_RE.search(driver):
        return True
    if VIRTUAL_PRINTER_PORT_RE.match(str(port or "")):
        return True
    if "redirected" in name.lower() or "redirected" in driver.lower():
        return True
    return False


def is_virtual_audio(name: str) -> bool:
    return bool(VIRTUAL_AUDIO_RE.search(name or ""))


def is_virtual_camera(name: str) -> bool:
    return bool(VIRTUAL_CAMERA_RE.search(name or ""))


def is_usb_infrastructure(name: str, device_type: str = "") -> bool:
    blob = f"{name} {device_type}"
    return bool(USB_INFRASTRUCTURE_RE.search(blob))


def is_internal_monitor(connection_type: str | None) -> bool:
    if not connection_type:
        return False
    return connection_type.strip().lower() in INTERNAL_DISPLAY_CONNECTIONS


def partition_physical(
    items: list[dict],
    *,
    virtual_key: str = "is_virtual",
) -> tuple[list[dict], list[dict]]:
    """Split items into (physical, virtual) using the is_virtual flag."""
    physical = [i for i in items if not i.get(virtual_key)]
    virtual = [i for i in items if i.get(virtual_key)]
    return physical, virtual


def connected_physical(items: list[dict], *, health_ok: tuple[str, ...] = ("Connected", "Ready")) -> list[dict]:
    """Items that are physical and reporting a healthy/connected state."""
    return [
        i for i in items
        if i.get("is_physical", True) and not i.get("is_virtual")
        and (
            i.get("connected") is True
            or i.get("working") is True
            or str(i.get("health") or "") in health_ok
        )
        and not i.get("offline")
    ]
