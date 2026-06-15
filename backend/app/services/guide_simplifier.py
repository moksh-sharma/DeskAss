"""Collapse verbose Microsoft Support steps into short, plain-language instructions."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Iterable

from app.models.schemas import VisualGuideStep

MAX_GUIDE_STEPS = 7
MAX_STEP_CHARS = 220

# Generic Microsoft footer / branding image reused across unrelated articles.
_JUNK_IMAGE_MARKERS = (
    "f4e85874-2a1a-438d-9c3c-17b069c454c0",
)

_SKIP_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"following message appears", re.I),
    re.compile(r'^"?Discoverable as\b', re.I),
    re.compile(r"try the solutions listed below", re.I),
    re.compile(r"choose one of the following", re.I),
    re.compile(r"^Advanced\s*-", re.I),
    re.compile(r"^Default\s*-", re.I),
    re.compile(r"^Fix Bluetooth disappeared", re.I),
    re.compile(r"^Troubleshoot Bluetooth not connecting", re.I),
    re.compile(r"^Troubleshoot transferring files", re.I),
    re.compile(r"^Select Start\s*>\s*Settings\s*>\s*Bluetooth\s*&\s*devices\s*>\s*Devices\s*\.$", re.I),
    re.compile(r"^need more help\??$", re.I),
    re.compile(r"microsoft 365 subscription|microsoft tech community|windows insiders", re.I),
    re.compile(r"want more options|discover community|online support", re.I),
)

_JUNK_SECTION_TITLES: tuple[re.Pattern[str], ...] = (
    re.compile(r"related topics?", re.I),
    re.compile(r"related articles?", re.I),
    re.compile(r"need more help", re.I),
    re.compile(r"see also", re.I),
    re.compile(r"more resources", re.I),
    re.compile(r"contact us", re.I),
)

_PLAIN_STEPS: dict[str, str] = {
    "enable_quick": (
        "Make sure Bluetooth is on: tap the Bluetooth button in the taskbar (bottom-right), "
        "or open Settings → Bluetooth & devices and switch it on."
    ),
    "enable_settings": (
        "Make sure Bluetooth is on: tap the Bluetooth button in the taskbar (bottom-right), "
        "or open Settings → Bluetooth & devices and switch it on."
    ),
    "restart_accessory": (
        "On your Bluetooth device (headphones, mouse, keyboard, etc.): turn it off, wait 10 seconds, "
        "then turn it on again."
    ),
    "range_interference": (
        "Keep the Bluetooth device close to your PC. If it is slow or drops out, unplug nearby USB "
        "cables or hubs and try again."
    ),
    "airplane": (
        "Turn off Airplane mode: click the taskbar icons (bottom-right) and switch Airplane mode off."
    ),
    "toggle_pc_bt": (
        "In Settings → Bluetooth & devices, turn Bluetooth off, wait 10 seconds, then turn it on again."
    ),
    "re_pair": (
        "Remove the device and pair again: Settings → Bluetooth & devices → Devices → "
        "⋯ next to the device → Remove device, then pair it again."
    ),
    "driver_update": (
        "Update Bluetooth drivers: search \"Device Manager\" on the taskbar → Bluetooth → "
        "right-click your adapter → Update driver → Search automatically. Restart when asked."
    ),
    "driver_reinstall": (
        "Still broken? In Device Manager → Bluetooth, right-click your adapter → Uninstall device, "
        "then restart your PC so Windows reinstalls it."
    ),
    "wifi_check": (
        "Check Wi-Fi from the taskbar (bottom-right): make sure Wi-Fi is on and your network shows Connected."
    ),
    "wifi_toggle": (
        "Turn Wi-Fi off and on: click the Wi-Fi icon on the taskbar, or open Settings → Network & internet."
    ),
    "wifi_forget": (
        "Forget and reconnect: Settings → Network & internet → Wi-Fi → your network → Forget, then connect again."
    ),
    "wifi_router": (
        "Restart your router and modem: unplug both for 30 seconds, plug them back in, then try Wi-Fi again."
    ),
    "wifi_band": (
        "Try the other Wi-Fi band: if you see 2.4 GHz and 5 GHz networks, connect to the other one."
    ),
    "wifi_adapter": (
        "Update your Wi-Fi adapter: Device Manager → Network adapters → right-click your Wi-Fi adapter → "
        "Update driver → Search automatically."
    ),
    "mouse_driver": (
        "Update the mouse or touchpad driver: Device Manager → Mice and other pointing devices → "
        "right-click your device → Update driver → Search automatically."
    ),
    "mouse_touchpad": (
        "Re-enable the touchpad: press Fn + the touchpad key, or Settings → Bluetooth & devices → "
        "Touchpad and make sure it is on."
    ),
    "mouse_usb": (
        "For a USB mouse: unplug it, wait 10 seconds, plug into another USB port, or replace wireless batteries."
    ),
    "keyboard_driver": (
        "Update the keyboard driver: Device Manager → Keyboards → right-click your keyboard → "
        "Update driver → Search automatically."
    ),
    "wifi_adapter_reinstall": (
        "Still broken? Device Manager → Network adapters → right-click your Wi-Fi adapter → Uninstall device, "
        "then restart your PC."
    ),
    "printer_restart": (
        "Turn off your printer, unplug it for 30 seconds, plug it back in, and turn it on."
    ),
    "printer_wifi": (
        "Make sure your printer and PC use the same Wi-Fi network (check the printer screen or manual)."
    ),
    "printer_default": (
        "Set your printer as default: Settings → Bluetooth & devices → Printers & scanners → "
        "your printer → Set as default."
    ),
    "printer_queue": (
        "Clear stuck print jobs: Settings → Printers & scanners → your printer → Open print queue → "
        "Cancel all."
    ),
    "printer_spooler": (
        "Restart the print spooler: search \"Services\" on the taskbar → Print Spooler → Restart."
    ),
    "printer_reinstall": (
        "Remove and re-add your printer: Settings → Printers & scanners → Remove the printer, "
        "then Add device and follow the prompts."
    ),
    "mic_privacy": (
        "Allow microphone access: Settings → Privacy & security → Microphone - turn access on for Windows "
        "and your app."
    ),
    "mic_input": (
        "Pick the right mic: Settings → System → Sound → Input - choose your microphone and speak to "
        "see the level bar move."
    ),
    "camera_privacy": (
        "Allow camera access: Settings → Privacy & security → Camera - turn access on for Windows and "
        "your app."
    ),
    "restart_pc": "Restart your PC, then try again.",
}

_INTENT_PRIORITY: tuple[str, ...] = (
    "wifi_check",
    "enable_quick",
    "restart_accessory",
    "range_interference",
    "airplane",
    "toggle_pc_bt",
    "re_pair",
    "wifi_toggle",
    "wifi_forget",
    "wifi_router",
    "wifi_band",
    "mic_privacy",
    "mic_input",
    "camera_privacy",
    "printer_restart",
    "printer_wifi",
    "printer_default",
    "printer_queue",
    "printer_spooler",
    "printer_reinstall",
    "mouse_touchpad",
    "mouse_driver",
    "mouse_usb",
    "keyboard_driver",
    "driver_update",
    "wifi_adapter",
    "wifi_adapter_reinstall",
    "restart_pc",
    "driver_reinstall",
    "driver_manual",
    "discovery",
    "misc",
)

_DROP_INTENTS = frozenset({"discovery", "driver_manual"})

_WIFI_ONLY_INTENTS = frozenset({
    "wifi_check", "wifi_toggle", "wifi_forget", "wifi_router", "wifi_band",
    "wifi_adapter", "wifi_adapter_reinstall",
})

_MOUSE_ONLY_INTENTS = frozenset({
    "mouse_driver", "mouse_touchpad", "mouse_usb",
})

_BLUETOOTH_ONLY_INTENTS = frozenset({
    "enable_quick", "enable_settings", "restart_accessory", "range_interference",
    "toggle_pc_bt", "re_pair", "driver_update", "driver_reinstall",
})


def is_junk_section_title(title: str) -> bool:
    t = (title or "").strip()
    if not t:
        return False
    return any(p.search(t) for p in _JUNK_SECTION_TITLES)


def is_junk_step_text(text: str) -> bool:
    return _should_skip(text)


def is_junk_image(*, image_url: str | None = None, image_name: str | None = None, step_text: str = "") -> bool:
    if step_text.strip() and is_junk_step_text(step_text):
        return True
    blob = f"{image_url or ''} {image_name or ''}".lower()
    return any(marker in blob for marker in _JUNK_IMAGE_MARKERS)


def filter_sections(sections: list[dict]) -> list[dict]:
    """Drop footer/navigation sections and junk steps scraped from Support pages."""
    filtered: list[dict] = []
    for section in sections:
        if is_junk_section_title(section.get("title", "")):
            continue
        steps = [
            s for s in section.get("steps", [])
            if not is_junk_step_text(str(s.get("text", "")))
        ]
        if steps:
            filtered.append({**section, "steps": steps})
    return filtered


def count_good_images_in_guide_data(data: dict) -> int:
    total = 0
    guide_id = str(data.get("id", ""))
    for section in data.get("sections", []):
        if is_junk_section_title(section.get("title", "")):
            continue
        for step in section.get("steps", []):
            image = step.get("image")
            if not image:
                continue
            image_url = step.get("image_url") or f"/api/visual-guides/{guide_id}/{image}"
            if is_junk_image(
                image_url=image_url,
                image_name=str(image),
                step_text=str(step.get("text", "")),
            ):
                continue
            total += 1
    return total


def collect_image_assets_from_guide_data(data: dict, *, guide_id: str | None = None) -> list[tuple[str, str | None]]:
    """Return (image_api_url, caption) pairs for usable screenshots in a guide."""
    gid = guide_id or str(data.get("id", ""))
    assets: list[tuple[str, str | None]] = []
    for section in data.get("sections", []):
        if is_junk_section_title(section.get("title", "")):
            continue
        for step in section.get("steps", []):
            image = step.get("image")
            if not image:
                continue
            image_url = f"/api/visual-guides/{gid}/{image}"
            if is_junk_image(
                image_url=image_url,
                image_name=str(image),
                step_text=str(step.get("text", "")),
            ):
                continue
            assets.append((image_url, step.get("caption")))
    return assets


def load_guide_json(assets_dir: Path, guide_id: str) -> dict | None:
    path = assets_dir / "guides" / guide_id / "guide.json"
    if not path.is_file():
        return None
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def _should_skip(text: str) -> bool:
    t = _clean_step_text(text)
    if len(t) < 12:
        return True
    return any(p.search(t) for p in _SKIP_PATTERNS)


def _domain_set(domains: Iterable[str] | None) -> set[str]:
    return {d.lower() for d in (domains or []) if d}


def _plain_for_intent(intent: str, domains: set[str]) -> str | None:
    if intent in _BLUETOOTH_ONLY_INTENTS and "bluetooth" not in domains:
        return None
    if intent in _WIFI_ONLY_INTENTS and not (domains & {"wifi", "network"}):
        return None
    if intent in _MOUSE_ONLY_INTENTS and "mouse" not in domains and "keyboard" not in domains:
        return None
    return _PLAIN_STEPS.get(intent)


def _classify_intent(text: str) -> str:
    t = _clean_step_text(text).lower()
    if re.search(r"unplug.*printer|power-cycling.*printer|restart your printer", t):
        return "printer_restart"
    if re.search(r"printer.*wi-?fi|same wi-?fi.*printer", t):
        return "printer_wifi"
    if "default printer" in t or "set as default" in t:
        return "printer_default"
    if "print queue" in t or "cancel all" in t:
        return "printer_queue"
    if "print spooler" in t:
        return "printer_spooler"
    if re.search(r"remove and reinstall.*printer|remove.*printer.*add device", t):
        return "printer_reinstall"
    if re.search(r"check your network connection|wi-?fi is turned on|network name shows connected", t):
        return "wifi_check"
    if "airplane mode" in t:
        return "airplane"
    if re.search(r"modem|wireless router|router back", t):
        return "wifi_router"
    if re.search(r"2\.4 ghz|5 ghz|frequency band|wi-?fi channel", t):
        return "wifi_band"
    if re.search(r"quick setting|taskbar.*bluetooth|bluetooth quick", t):
        return "enable_quick"
    if "remove device" in t or "remove the bluetooth device" in t:
        return "re_pair"
    if re.search(r"turn off your bluetooth device|bluetooth device.*turn it back on", t):
        return "restart_accessory"
    if "in range" in t or "usb 3.0" in t or "unshielded usb" in t:
        return "range_interference"
    if re.search(r"turn bluetooth on and off|turn off bluetooth.*turn it back on", t):
        return "toggle_pc_bt"
    if "uninstall device" in t or "scan for hardware changes" in t:
        if re.search(r"network adapter|wi-?fi|wireless", t):
            return "wifi_adapter_reinstall"
        if re.search(r"mouse|touchpad|pointing|mice", t):
            return "mouse_driver"
        if re.search(r"keyboard", t):
            return "keyboard_driver"
        if "bluetooth" in t:
            return "driver_reinstall"
        return "misc"
    if ".exe" in t or "browse my computer" in t or ".inf" in t or ".sys" in t:
        return "driver_manual"
    if "update driver" in t:
        if re.search(r"network adapter|wi-?fi|wireless", t):
            return "wifi_adapter"
        if re.search(r"mouse|touchpad|trackpad|pointing|mice", t):
            return "mouse_driver"
        if re.search(r"keyboard", t):
            return "keyboard_driver"
        if "bluetooth" in t:
            return "driver_update"
        return "misc"
    if re.search(r"settings.*bluetooth", t) and "remove" not in t and "discovery" not in t:
        return "enable_settings"
    if "discovery" in t or "device settings" in t:
        return "discovery"
    if re.search(r"forget", t) and re.search(r"wi-?fi|network", t):
        return "wifi_forget"
    if re.search(r"wi-?fi.*turn|turn.*wi-?fi|network & internet", t):
        return "wifi_toggle"
    if re.search(r"touchpad|trackpad", t) and re.search(r"enable|disable|turn on", t):
        return "mouse_touchpad"
    if re.search(r"mice and other pointing|pointing device|mouse", t) and "uninstall" in t:
        return "mouse_driver"
    if re.search(r"network adapters|wi-?fi adapter", t):
        return "wifi_adapter"
    if re.search(r"microphone|privacy.*mic", t) and "privacy" in t:
        return "mic_privacy"
    if re.search(r"microphone|sound.*input", t) and "input" in t:
        return "mic_input"
    if re.search(r"camera|webcam", t) and "privacy" in t:
        return "camera_privacy"
    if re.search(r"restart your pc|restart your device", t):
        return "restart_pc"
    if re.search(r"restart|shut down", t) and "power" in t:
        return "restart_pc"
    return "misc"


def _clean_step_text(text: str) -> str:
    t = text.strip()
    t = re.sub(r"^Step\s+\d+\.\s*", "", t, flags=re.I)
    t = re.sub(r"Support for Windows 10 has ended.*", "", t, flags=re.I | re.S)
    t = re.sub(r"Open Printers & scanners settings\s*", "", t, flags=re.I)
    return t.strip()


def _simplify_paths(text: str) -> str:
    t = _clean_step_text(text)
    t = re.sub(r"\s+", " ", t)
    t = re.sub(
        r"Select Start\s*>\s*Settings\s*>\s*",
        "Open Settings → ",
        t,
        flags=re.I,
    )
    t = re.sub(
        r"Select Search on the taskbar,?\s*(?:type|enter)\s*(?:for\s*)?([^,]+),?\s*"
        r"and then select Device Manager[^.]*\.",
        r'Open Device Manager (search "\1" on the taskbar).',
        t,
        flags=re.I,
    )
    t = re.sub(r"Press and hold \(or right-click\)", "Right-click", t, flags=re.I)
    t = re.sub(r"\(\s*\)", "", t)
    t = re.sub(r"\s{2,}", " ", t)
    t = re.sub(r"\s*To learn more[^.]*\.", "", t, flags=re.I)
    t = re.sub(r"\s*see Pair a Bluetooth device\s*\.?", "", t, flags=re.I)
    if len(t) > MAX_STEP_CHARS:
        cut = t[: MAX_STEP_CHARS - 1].rsplit(" ", 1)[0]
        t = cut + "…"
    return t.strip()


def _merge_texts(texts: Iterable[str]) -> str:
    parts: list[str] = []
    for raw in texts:
        simple = _simplify_paths(raw)
        if simple and simple not in parts:
            parts.append(simple)
    if not parts:
        return ""
    if len(parts) == 1:
        return parts[0]
    combined = " ".join(parts[:2])
    if len(combined) > MAX_STEP_CHARS:
        return parts[0]
    return combined


def _step_text(step: VisualGuideStep, domains: set[str]) -> str:
    intent = _classify_intent(step.text)
    plain = _plain_for_intent(intent, domains)
    if plain:
        return plain
    if intent == "misc":
        return _simplify_paths(step.text)
    merged = _merge_texts([step.text])
    return merged or _simplify_paths(step.text)


def _distribute_images(
    steps: list[VisualGuideStep],
    image_pool: list[tuple[str, str | None]],
) -> list[VisualGuideStep]:
    """Attach available screenshots to simplified steps (preserves existing step images)."""
    if not image_pool:
        return steps

    pool = list(image_pool)
    out: list[VisualGuideStep] = []
    pool_index = 0

    for step in steps:
        if step.image_url and not is_junk_image(image_url=step.image_url, step_text=step.text):
            out.append(step)
            continue

        image_url: str | None = None
        caption = step.caption
        while pool_index < len(pool):
            candidate_url, candidate_caption = pool[pool_index]
            pool_index += 1
            if not is_junk_image(image_url=candidate_url):
                image_url = candidate_url
                caption = caption or candidate_caption
                break

        out.append(
            VisualGuideStep(
                step=step.step,
                text=step.text,
                caption=caption,
                image_url=image_url,
            )
        )

    return out


def simplify_guide_steps(
    steps: list[VisualGuideStep],
    *,
    domains: list[str] | None = None,
    max_steps: int = MAX_GUIDE_STEPS,
    extra_images: list[tuple[str, str | None]] | None = None,
) -> list[VisualGuideStep]:
    """Reduce many raw Support steps to a short, beginner-friendly list. Keeps screenshots."""
    domain_set = _domain_set(domains)

    image_pool: list[tuple[str, str | None]] = []
    for step in steps:
        if step.image_url and not is_junk_image(image_url=step.image_url, step_text=step.text):
            image_pool.append((step.image_url, step.caption))
    if extra_images:
        image_pool.extend(extra_images)

    simplified: list[VisualGuideStep]

    if len(steps) <= max_steps:
        simplified = [
            VisualGuideStep(
                step=i + 1,
                text=_step_text(s, domain_set),
                caption=s.caption,
                image_url=s.image_url if not is_junk_image(image_url=s.image_url, step_text=s.text) else None,
            )
            for i, s in enumerate(steps)
            if not _should_skip(s.text)
        ][:max_steps]
    else:
        buckets: dict[str, list[VisualGuideStep]] = {}
        for step in steps:
            if _should_skip(step.text):
                continue
            intent = _classify_intent(step.text)
            buckets.setdefault(intent, []).append(step)

        if "enable_settings" in buckets:
            buckets.setdefault("enable_quick", []).extend(buckets.pop("enable_settings"))

        merged: list[VisualGuideStep] = []
        for intent in _INTENT_PRIORITY:
            if intent in _DROP_INTENTS:
                continue
            group = buckets.get(intent)
            if not group:
                continue

            image_step = next(
                (s for s in group if s.image_url and not is_junk_image(image_url=s.image_url, step_text=s.text)),
                None,
            )
            plain = _plain_for_intent(intent, domain_set)
            text = plain or _merge_texts(s.text for s in group)
            if not text:
                continue

            merged.append(
                VisualGuideStep(
                    step=len(merged) + 1,
                    text=text,
                    caption=image_step.caption if image_step else None,
                    image_url=image_step.image_url if image_step else None,
                )
            )
            if len(merged) >= max_steps:
                break

        if not merged:
            for step in steps:
                if _should_skip(step.text):
                    continue
                merged.append(
                    VisualGuideStep(
                        step=len(merged) + 1,
                        text=_step_text(step, domain_set),
                        caption=step.caption,
                        image_url=step.image_url,
                    )
                )
                if len(merged) >= max_steps:
                    break

        simplified = merged

    distributed = _distribute_images(simplified, image_pool)

    return [
        VisualGuideStep(
            step=i + 1,
            text=s.text,
            caption=s.caption,
            image_url=s.image_url,
        )
        for i, s in enumerate(distributed)
    ]


def simplify_resolution_line(text: str) -> str:
    """Plain-language rewrite for supplemental troubleshooting bullets."""
    t = _simplify_paths(text)
    replacements = (
        (r"Verify that the default Bluetooth device.*", "Check Settings → Sound and pick the right output device."),
        (r"Check privacy settings for Bluetooth.*", "Check Settings → Privacy and allow the right app permissions."),
        (r"Check if any apps are using Bluetooth.*", "Close apps that may be using the device, then try again."),
        (r"Regularly update your Bluetooth drivers.*", "Keep device drivers up to date in Device Manager."),
        (r"Monitor privacy settings.*", "Review privacy settings for apps you trust."),
    )
    for pattern, repl in replacements:
        if re.search(pattern, t, re.I):
            return repl
    if len(t) > 160:
        t = t[:157].rstrip() + "…"
    return t


def simplify_prevention_tips(tips: list[str], *, max_items: int = 3) -> list[str]:
    defaults = [
        "Keep Windows updated so fixes arrive automatically.",
        "Restart your PC after changing drivers or device settings.",
        "Remove devices or networks you no longer use.",
    ]
    out: list[str] = []
    for tip in tips:
        simple = simplify_resolution_line(tip)
        if simple and simple not in out:
            out.append(simple)
        if len(out) >= max_items:
            return out
    for tip in defaults:
        if tip not in out:
            out.append(tip)
        if len(out) >= max_items:
            break
    return out


def supplemental_resolution_steps(steps: list[str], *, max_items: int = 3) -> list[str]:
    """Short extras shown only when a visual guide already covers the main flow."""
    out: list[str] = []
    for step in steps:
        simple = simplify_resolution_line(step)
        if not simple or simple in out:
            continue
        lower = simple.lower()
        if any(
            phrase in lower
            for phrase in (
                "settings → bluetooth",
                "settings → network",
                "device manager",
                "turn on bluetooth",
                "remove the device",
                "airplane mode",
                "forget and reconnect",
            )
        ):
            continue
        out.append(simple)
        if len(out) >= max_items:
            break
    return out
