"""Map Microsoft Support article titles/URLs to HelpDesk issue domains."""
from __future__ import annotations

import re

# Mirrors backend issue_parser domains for consistent matching.
_DOMAIN_PATTERNS: dict[str, re.Pattern[str]] = {
    "bluetooth": re.compile(
        r"bluetooth|blue\s*tooth|pairing|airpods|earbuds|headset", re.I
    ),
    "wifi": re.compile(r"wi-?fi|wireless|wlan|hotspot|ssid", re.I),
    "network": re.compile(
        r"internet|network|ethernet|dns|vpn|proxy|connection|offline|gateway", re.I
    ),
    "audio": re.compile(
        r"sound|audio|speaker|microphone|\bmic\b|volume|playback", re.I
    ),
    "printer": re.compile(r"printer|printing|spooler|scanner|\bfax\b", re.I),
    "display": re.compile(
        r"monitor|display|screen|resolution|hdmi|graphics|gpu|flicker", re.I
    ),
    "webcam": re.compile(r"webcam|web\s*cam|camera|video\s*call", re.I),
    "usb": re.compile(r"\busb\b|flash\s*drive|thumb\s*drive|external\s*drive", re.I),
    "storage": re.compile(
        r"disk\s*space|storage|free\s*up|hard\s*drive|\bssd\b|\bhdd\b", re.I
    ),
    "performance": re.compile(
        r"\bslow\b|sluggish|lag|freeze|hang|not\s*responding|overheat|\bfan\b", re.I
    ),
    "windows_update": re.compile(
        r"windows\s*update|feature\s*update|update\s*failed|pending\s*restart", re.I
    ),
    "mouse": re.compile(r"mouse|touchpad|trackpad|pointer|cursor", re.I),
    "keyboard": re.compile(r"keyboard|keystroke|typing|numpad", re.I),
    "battery": re.compile(r"battery|charging|power\s*drain", re.I),
    "boot": re.compile(
        r"\bboot\b|bsod|blue\s*screen|startup|won'?t\s*start|not\s*starting", re.I
    ),
    "security": re.compile(
        r"defender|antivirus|malware|firewall|ransomware|bitlocker|phishing", re.I
    ),
    "account": re.compile(
        r"sign[\s-]?in|login|password|microsoft\s*account|\bpin\b|hello", re.I
    ),
}


def infer_domains(title: str, url: str) -> list[str]:
    slug = url.rsplit("/", 1)[-1] if url else ""
    text = f"{title} {slug}".replace("-", " ")
    found = [domain for domain, pattern in _DOMAIN_PATTERNS.items() if pattern.search(text)]
    if "wifi" in found and "network" not in found:
        found.append("network")
    if "network" in found and re.search(r"wi-?fi|wireless", text, re.I) and "wifi" not in found:
        found.append("wifi")
    return found


def keywords_from_title(title: str, max_words: int = 12) -> list[str]:
    clean = re.sub(r"\s*-\s*Microsoft Support\s*$", "", title, flags=re.I).strip().lower()
    words = re.findall(r"[a-z0-9]+", clean)
    stop = {
        "a", "an", "the", "in", "on", "to", "for", "and", "or", "of", "your", "with",
        "how", "use", "using", "about", "windows", "window", "pc", "is", "are", "be",
    }
    out: list[str] = []
    for w in words:
        if w in stop or len(w) < 3:
            continue
        if w not in out:
            out.append(w)
        if len(out) >= max_words:
            break
    return out
