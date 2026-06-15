"""Match user issues to Microsoft Support visual guides and attach step screenshots."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from app.core.logging import get_logger
from app.models.schemas import DiagnosisResult, VisualGuide, VisualGuideStep
from app.services.guide_simplifier import (
    collect_image_assets_from_guide_data,
    count_good_images_in_guide_data,
    filter_sections,
    is_junk_step_text,
    load_guide_json,
    simplify_guide_steps,
    simplify_prevention_tips,
    supplemental_resolution_steps,
)

logger = get_logger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[3]
_ASSETS_DIR = _REPO_ROOT / "kb_visual_assets"
_MANIFEST_PATH = _ASSETS_DIR / "guides_manifest.json"

_DOMAIN_ALIASES: dict[str, set[str]] = {
    "wifi": {"wifi", "network"},
    "network": {"network", "wifi"},
}

# When the user message matches the left pattern, reject guides whose title matches the right.
_BLOCKED_COMBOS: list[tuple[re.Pattern[str], re.Pattern[str]]] = [
    (re.compile(r"\bpair\b|pairing|cannot_pair", re.I), re.compile(r"one channel|low energy audio", re.I)),
    (re.compile(r"webcam|camera", re.I), re.compile(r"camera roll|mobile device.?s camera", re.I)),
    (re.compile(r"\bslow\b|sluggish|lag|freeze|hang|performance", re.I), re.compile(
        r"brightness|color in windows|theme|wallpaper|lock screen", re.I
    )),
    (re.compile(r"wi-?fi|wireless", re.I), re.compile(r"bluetooth(?!.*wi-?fi)|monitor|display(?!.*network)", re.I)),
    (re.compile(r"bluetooth", re.I), re.compile(r"wi-?fi|wireless(?!.*bluetooth)", re.I)),
    (re.compile(r"printer|printing", re.I), re.compile(r"bluetooth|wi-?fi|camera|microphone", re.I)),
    (re.compile(r"microphone|\bmic\b", re.I), re.compile(r"camera roll|speaker(?!.*mic)", re.I)),
    (re.compile(r"speaker|no sound|audio playback", re.I), re.compile(r"microphone problems(?!.*sound)", re.I)),
    (re.compile(r"mouse|touchpad|trackpad|keyboard", re.I), re.compile(r"wi-?fi|wireless|network adapter", re.I)),
]

_SYMPTOM_HINTS: dict[str, list[tuple[str, float]]] = {
    "cannot_pair": [("pair", 35), ("bluetooth", 20)],
    "cannot_connect": [("connect", 30), ("wi-fi", 25), ("wireless", 20), ("network", 15)],
    "no_sound": [("sound", 30), ("audio", 25), ("speaker", 20)],
    "not_detected": [("detect", 20), ("recognized", 20), ("troubleshoot", 15)],
    "not_working": [("fix", 25), ("troubleshoot", 20), ("problem", 15)],
    "slow": [("performance", 30), ("slow", 25), ("free up", 15), ("startup", 15)],
    "crash": [("crash", 25), ("troubleshoot", 15)],
    "wont_start": [("start", 20), ("boot", 20), ("troubleshoot", 15)],
    "after_update": [("update", 25), ("windows update", 20)],
    "error_code": [("error", 20), ("troubleshoot", 15)],
}

_DOMAIN_REQUIRED_IN_TITLE: dict[str, re.Pattern[str]] = {
    "wifi": re.compile(r"wi-?fi|wireless|network|internet", re.I),
    "network": re.compile(r"network|internet|wi-?fi|wireless|ethernet|dns", re.I),
    "bluetooth": re.compile(r"bluetooth", re.I),
    "printer": re.compile(r"print", re.I),
    "audio": re.compile(r"sound|audio|speaker|microphone|\bmic\b", re.I),
    "display": re.compile(r"monitor|display|screen|hdmi|graphics", re.I),
    "webcam": re.compile(r"camera|webcam", re.I),
    "usb": re.compile(r"usb|drive|device", re.I),
    "storage": re.compile(r"disk|storage|space|drive", re.I),
    "performance": re.compile(r"performance|slow|speed|startup|free up|health", re.I),
    "windows_update": re.compile(r"update", re.I),
    "mouse": re.compile(r"mouse|touchpad|trackpad|keyboard", re.I),
    "keyboard": re.compile(r"keyboard|typing|mouse", re.I),
    "battery": re.compile(r"battery|power|charging", re.I),
    "boot": re.compile(r"boot|start|recovery|startup", re.I),
    "security": re.compile(r"security|defender|firewall|virus|malware", re.I),
    "account": re.compile(r"account|password|sign[\s-]?in|login|pin", re.I),
}

_STOP_WORDS = frozenset({
    "a", "an", "the", "in", "on", "to", "for", "and", "or", "of", "your", "with",
    "how", "use", "using", "about", "windows", "window", "pc", "is", "are", "be",
    "my", "not", "working", "work", "can", "cant", "cannot", "wont", "won", "t",
    "it", "this", "that", "from", "when", "has", "have", "get", "any", "all",
})

_manifest_cache: tuple[float, dict] | None = None


@dataclass(frozen=True)
class MatchContext:
    message: str
    domains: list[str]
    primary_domain: str | None = None
    symptoms: tuple[str, ...] = ()
    issue_summary: str = ""
    root_cause: str = ""


def _load_manifest() -> dict:
    global _manifest_cache
    if not _MANIFEST_PATH.is_file():
        logger.warning("Visual guides manifest not found at %s", _MANIFEST_PATH)
        return {"guides": []}
    mtime = _MANIFEST_PATH.stat().st_mtime
    if _manifest_cache and _manifest_cache[0] == mtime:
        return _manifest_cache[1]
    with _MANIFEST_PATH.open(encoding="utf-8") as f:
        data = json.load(f)
    _manifest_cache = (mtime, data)
    return data


def _expand_domains(domains: set[str]) -> set[str]:
    expanded: set[str] = set()
    for domain in domains:
        expanded.add(domain)
        expanded |= _DOMAIN_ALIASES.get(domain, {domain})
    return expanded


def _tokens(text: str) -> set[str]:
    return {
        t for t in re.findall(r"[a-z0-9]+", text.lower())
        if len(t) > 2 and t not in _STOP_WORDS
    }


def _compose_query(ctx: MatchContext) -> str:
    parts = [
        ctx.message,
        ctx.primary_domain or "",
        " ".join(ctx.domains),
        " ".join(ctx.symptoms),
        ctx.issue_summary,
        ctx.root_cause,
    ]
    return " ".join(p.strip() for p in parts if p and p.strip()).lower()


class VisualGuideService:
    """Loads extracted Support guides and attaches them to diagnoses."""

    def __init__(self, assets_dir: Path | None = None) -> None:
        self._assets_dir = assets_dir or _ASSETS_DIR

    @property
    def available(self) -> bool:
        return (self._assets_dir / "guides_manifest.json").is_file()

    def _manifest_entries(self) -> list[dict]:
        return list(_load_manifest().get("guides", []))

    def _domain_allowed(self, entry: dict, ctx: MatchContext) -> bool:
        domain_set = {d.lower() for d in ctx.domains}
        if not domain_set:
            return True

        title = entry.get("title", "")
        focus = (ctx.primary_domain or ctx.domains[0]).lower()
        required = _DOMAIN_REQUIRED_IN_TITLE.get(focus)
        if required and not required.search(title):
            return False

        expanded = _expand_domains(domain_set)
        entry_domains = {d.lower() for d in entry.get("domains", [])}
        if entry_domains:
            return bool(expanded & entry_domains)
        # Manifest row missing domains - allow when the title matches the issue domain.
        return bool(required and required.search(title))

    def _blocked_combo(self, query: str, title: str) -> bool:
        for query_pat, title_pat in _BLOCKED_COMBOS:
            if query_pat.search(query) and title_pat.search(title):
                return True
        return False

    def _score_entry(self, entry: dict, ctx: MatchContext) -> float:
        if not self._domain_allowed(entry, ctx):
            return 0.0

        query = _compose_query(ctx)
        title = entry.get("title", "")
        title_l = title.lower()
        query_tokens = _tokens(query)
        title_tokens = _tokens(title_l)

        if self._blocked_combo(query, title_l):
            return 0.0

        if not query_tokens:
            return 0.0

        overlap = query_tokens & title_tokens
        score = len(overlap) * 8.0
        # Reward covering important query terms in the title.
        coverage = len(overlap) / max(1, min(len(query_tokens), 8))
        score += coverage * 25.0

        for kw in entry.get("keywords", []):
            kw_l = kw.lower()
            if kw_l in query_tokens or kw_l in query:
                score += 4.0

        for symptom in ctx.symptoms:
            for hint, boost in _SYMPTOM_HINTS.get(symptom, []):
                if hint in query and hint in title_l:
                    score += boost

        # Explicit user intents.
        if re.search(r"\bpair\b|pairing", query) and re.search(r"\bpair\b", title_l):
            score += 40.0
        if re.search(r"connect", query) and "connect" in title_l:
            score += 25.0
        if re.search(r"\bfix\b|not working|problem|troubleshoot", query) and re.search(
            r"\bfix\b|troubleshoot|problem", title_l, re.I
        ):
            score += 20.0
        if re.search(r"microphone|\bmic\b", query) and re.search(r"microphone|\bmic\b", title_l):
            score += 35.0
        if re.search(r"speaker|no sound", query) and re.search(r"sound|speaker|audio", title_l):
            score += 30.0
        if re.search(r"offline", query) and "offline" in title_l:
            score += 30.0
        if re.search(r"external monitor|second screen|hdmi", query) and re.search(
            r"monitor|display|hdmi|screen", title_l, re.I
        ):
            score += 30.0
        if re.search(r"webcam|camera", query) and re.search(
            r"camera|webcam", title_l, re.I
        ) and "roll" not in title_l:
            score += 35.0
        if re.search(r"\bslow\b|sluggish|lag", query) and re.search(
            r"performance|slow|free up|health|startup", title_l, re.I
        ):
            score += 30.0
        if re.search(r"stuck|failed|pending", query) and re.search(
            r"update|free up space", title_l, re.I
        ):
            score += 28.0
        if "windows_update" in {d.lower() for d in ctx.domains} or re.search(
            r"windows\s+update", query
        ):
            if re.search(r"windows update|free up space", title_l, re.I):
                score += 40.0
            if re.search(r"\bdriver\b", title_l) and not re.search(r"\bdriver\b", query):
                score -= 50.0
            if re.search(r"inside this update", title_l):
                score -= 50.0
        if re.search(r"not charging|won.t charge|wont charge", query) and re.search(
            r"charg|battery|power", title_l, re.I
        ):
            score += 28.0

        # Deprioritize generic/reference articles for troubleshooting requests.
        if re.search(r"inside this update", title_l):
            score -= 40.0
        if re.search(r"not working|fix|problem|won'?t|wont|can'?t", query):
            if re.search(r"\bfaq\b|what they mean|analyze the|icons and what|exploring", title_l):
                score -= 30.0

        source = entry.get("source_url", "").lower()
        guide_id = entry.get("id", "").lower()
        if re.search(r"\bfix\b|troubleshoot|problem|not working", query):
            if "/fix-" in source or "troubleshoot" in source:
                score += 12.0
            if "icons-and-what" in guide_id or "what-they-mean" in guide_id:
                score -= 45.0
        if re.search(r"not working|doesn.t work|does not work", query):
            if re.search(r"doesn.t work|does not work", title_l):
                score += 22.0
        if re.search(r"\bpair\b", query) and guide_id.startswith("pair-"):
            score += 20.0
        if re.search(r"connect", query) and guide_id.startswith("connect-to-a-wi-fi"):
            score += 20.0

        guide_data = load_guide_json(self._assets_dir, entry.get("id", ""))
        good_images = count_good_images_in_guide_data(guide_data) if guide_data else 0
        # Allow text-only troubleshooting articles; donor guides can supply screenshots later.
        if good_images <= 0 and not entry.get("domains"):
            return 0.0
        score += good_images * 3.0

        return score

    def _rank_key(self, score: float, entry: dict) -> tuple:
        source = entry.get("source_url", "").lower()
        guide_id = entry.get("id", "").lower()
        return (
            score,
            int(entry.get("image_count", 0)),
            1 if "/fix-" in source or guide_id.startswith("fix-") else 0,
            1 if guide_id.startswith("pair-") or guide_id.startswith("connect-to-a-wi-fi") else 0,
            -1 if "icons-and-what" in guide_id or "camera-roll" in guide_id else 0,
        )

    def match_guide_id(self, ctx: MatchContext) -> str | None:
        entries = self._manifest_entries()
        if not entries:
            return None

        ranked: list[tuple[tuple, dict]] = []
        for entry in entries:
            score = self._score_entry(entry, ctx)
            if score >= 15.0:
                ranked.append((self._rank_key(score, entry), entry))

        if not ranked:
            return None

        ranked.sort(key=lambda item: item[0], reverse=True)
        return ranked[0][1]["id"]

    def _section_score(self, section: dict, query: str) -> float:
        title = section.get("title", "").lower()
        title_tokens = _tokens(title)
        query_tokens = _tokens(query)
        score = len(query_tokens & title_tokens) * 6.0
        if re.search(r"microphone|\bmic\b", query) and "microphone" in title:
            score += 25.0
        if re.search(r"speaker|sound", query) and re.search(r"sound|speaker|audio", title):
            score += 25.0
        if re.search(r"general troubleshooting|how to fix|troubleshooting steps", title):
            score += 50.0
        # Prefer sections with real instructional steps, not footer images.
        steps = section.get("steps", [])
        actionable = sum(
            1 for s in steps
            if len(str(s.get("text", "")).strip()) > 40
            and not is_junk_step_text(str(s.get("text", "")))
        )
        score += actionable * 4.0
        score += sum(
            1 for s in steps
            if s.get("image") and not is_junk_step_text(str(s.get("text", "")))
        ) * 6.0
        return score

    def _donor_rank(self, entry: dict) -> tuple:
        title = entry.get("title", "").lower()
        source = entry.get("source_url", "").lower()
        relevance = 0
        if re.search(r"connect|pair|fix|troubleshoot|problem", title):
            relevance += 3
        if "/fix-" in source or "/connect-" in source or "/pair-" in source:
            relevance += 2
        if re.search(r"analyze|icon|what they mean|inside this update", title):
            relevance -= 3
        data = load_guide_json(self._assets_dir, entry.get("id", ""))
        images = count_good_images_in_guide_data(data) if data else 0
        return (relevance, images)

    def _find_image_donor(self, domains: list[str], exclude_id: str) -> str | None:
        domain_set = _expand_domains({d.lower() for d in domains if d})
        if not domain_set:
            return None

        ranked: list[tuple[tuple, str]] = []
        for entry in self._manifest_entries():
            gid = entry.get("id", "")
            if not gid or gid == exclude_id:
                continue
            entry_domains = _expand_domains({d.lower() for d in entry.get("domains", [])})
            if not domain_set & entry_domains:
                continue
            rank = self._donor_rank(entry)
            if rank[1] <= 0:
                continue
            ranked.append((rank, gid))

        if not ranked:
            return None
        ranked.sort(key=lambda item: item[0], reverse=True)
        return ranked[0][1]

    def _borrowed_images(self, guide_id: str, domains: list[str]) -> list[tuple[str, str | None]]:
        donor_id = self._find_image_donor(domains, guide_id)
        if not donor_id:
            return []
        donor_data = load_guide_json(self._assets_dir, donor_id)
        if not donor_data:
            return []
        assets = collect_image_assets_from_guide_data(donor_data, guide_id=donor_id)
        if assets:
            logger.info(
                "Borrowing %d screenshot(s) from guide %s for %s",
                len(assets),
                donor_id,
                guide_id,
            )
        return assets

    def load_guide(
        self,
        guide_id: str,
        *,
        match_query: str = "",
        domains: list[str] | None = None,
    ) -> VisualGuide | None:
        guide_path = self._assets_dir / "guides" / guide_id / "guide.json"
        if not guide_path.is_file():
            logger.warning("Visual guide JSON missing: %s", guide_path)
            return None

        with guide_path.open(encoding="utf-8") as f:
            data = json.load(f)

        sections = filter_sections(list(data.get("sections", [])))
        if not sections:
            return None

        if match_query and len(sections) > 1:
            scored = [(self._section_score(sec, match_query), sec) for sec in sections]
            scored.sort(key=lambda x: x[0], reverse=True)
            sections = [scored[0][1]]

        steps: list[VisualGuideStep] = []
        step_num = 0
        for section in sections:
            for raw in section.get("steps", []):
                text = str(raw.get("text", "")).strip()
                if is_junk_step_text(text):
                    continue
                step_num += 1
                image = raw.get("image")
                image_url = f"/api/visual-guides/{guide_id}/{image}" if image else None
                steps.append(
                    VisualGuideStep(
                        step=step_num,
                        text=text,
                        caption=raw.get("caption"),
                        image_url=image_url,
                    )
                )

        if not steps:
            return None

        domain_list = list(domains or data.get("domains") or [])
        own_images = count_good_images_in_guide_data(data)
        borrowed = self._borrowed_images(guide_id, domain_list) if own_images < 3 else []
        steps = simplify_guide_steps(
            steps,
            domains=domain_list,
            extra_images=borrowed,
        )

        return VisualGuide(
            id=guide_id,
            title=str(data.get("title", guide_id)),
            source_url=str(data.get("source_url", "")),
            attribution=str(data.get("attribution", "Microsoft Support")),
            section_title=sections[0].get("title") if sections else None,
            steps=steps,
        )

    def attach(
        self,
        result: DiagnosisResult,
        message: str,
        domains: list[str],
        *,
        primary_domain: str | None = None,
        symptoms: list[str] | None = None,
    ) -> DiagnosisResult:
        """Visual guides with screenshots are disabled - use finding resolution steps instead."""
        return result
