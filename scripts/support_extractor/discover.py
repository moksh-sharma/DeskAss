"""Discover Microsoft Support Windows article URLs from the public sitemap."""
from __future__ import annotations

import re
from pathlib import Path

import httpx

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_INDEX = SCRIPT_DIR / "article_index.json"
_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) HelpDeskAssistant/1.0"
_RE_LOC = re.compile(r"<loc>([^<]+)</loc>")


def discover_windows_urls(
    client: httpx.Client,
    *,
    locale: str = "en-us",
    max_sitemap_indexes: int = 20,
) -> list[str]:
    urls: set[str] = set()
    prefix = f"https://support.microsoft.com/{locale}/windows/"

    for i in range(max_sitemap_indexes):
        sitemap_url = f"https://support.microsoft.com/{locale}/sitemap/index-{i}.xml"
        resp = client.get(sitemap_url)
        if resp.status_code == 404:
            break
        resp.raise_for_status()
        for loc in _RE_LOC.findall(resp.text):
            if loc.startswith(prefix):
                urls.add(loc.split("?")[0].rstrip("/"))

    return sorted(urls)


def guide_id_from_url(url: str) -> str:
    slug = url.rstrip("/").rsplit("/", 1)[-1]
    return slug[:96] or "guide"
