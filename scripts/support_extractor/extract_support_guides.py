#!/usr/bin/env python3
"""Extract step-by-step guides (text + screenshots) from support.microsoft.com.

Downloads article images and builds per-guide JSON plus a top-level manifest under
``kb_visual_assets/guides/``. Intended for later integration into HelpDesk Assistant.

Usage (from repo root):
  python scripts/support_extractor/extract_support_guides.py
  python scripts/support_extractor/extract_support_guides.py --clean
  python scripts/support_extractor/extract_support_guides.py --url https://support.microsoft.com/...

Attribution: images are from Microsoft Support; verify redistribution with legal before
shipping in a product build.
"""
from __future__ import annotations

import argparse
import html
import json
import re
import shutil
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urljoin

import httpx

from domains import infer_domains, keywords_from_title
from discover import DEFAULT_INDEX, discover_windows_urls, guide_id_from_url

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[1]
DEFAULT_OUTPUT = PROJECT_ROOT / "kb_visual_assets"
GUIDES_CONFIG = SCRIPT_DIR / "guide_urls.json"
SUPPORT_BASE = "https://support.microsoft.com"

_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) HelpDeskAssistant/1.0"
_RE_MAIN = re.compile(r"<main[^>]*>(.*)</main>", re.S | re.I)
_RE_H2_SPLIT = re.compile(r"<h2[^>]*>", re.I)
_RE_H3_SPLIT = re.compile(r"(<h3[^>]*>.*?</h3>)", re.S | re.I)
_RE_LI = re.compile(r"<li[^>]*>(.*?)</li>", re.S | re.I)
_RE_STEP_HEADING = re.compile(r"^Step\s+\d+\.", re.I)
_RE_IMG = re.compile(r'<img[^>]+src=["\']([^"\']+)["\']', re.I)
_RE_ALT = re.compile(r'alt=["\']([^"\']*)["\']', re.I)
_RE_TITLE = re.compile(r"<title>([^<]+)</title>", re.I)
_RE_TAGS = re.compile(r"<[^>]+>")


def _load_config() -> dict:
    with GUIDES_CONFIG.open(encoding="utf-8") as f:
        return json.load(f)


def _strip_html(fragment: str) -> str:
    text = _RE_TAGS.sub(" ", fragment)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _is_content_image(src: str) -> bool:
    if not src:
        return False
    if "uhf.microsoft.com" in src:
        return False
    if "/images/Facebook" in src or "/images/Linkedin" in src or "/images/Mail" in src:
        return False
    return src.startswith("/images/") or "support.microsoft.com/images/" in src


def _resolve_url(src: str, page_url: str) -> str:
    if src.startswith("http://") or src.startswith("https://"):
        return src
    return urljoin(page_url, src)


def _detect_ext(data: bytes) -> str:
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return ".png"
    if data[:3] == b"\xff\xd8\xff":
        return ".jpg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ".webp"
    if data.lstrip().startswith(b"<svg") or b"<svg" in data[:200]:
        return ".svg"
    if data.lstrip().startswith(b"<?xml") and b"svg" in data[:500]:
        return ".svg"
    return ".png"


def _fetch_html(client: httpx.Client, url: str) -> str:
    resp = client.get(url)
    resp.raise_for_status()
    return resp.text


def _step_from_block(*, text: str, html_block: str) -> dict:
    imgs = [s for s in _RE_IMG.findall(html_block) if _is_content_image(s)]
    alts = _RE_ALT.findall(html_block)
    caption = html.unescape(alts[0]).strip() if alts else None
    return {
        "text": text,
        "image_src": imgs[0] if imgs else None,
        "caption": caption or None,
    }


def _parse_li_steps(chunk: str) -> list[dict]:
    steps: list[dict] = []
    for li_html in _RE_LI.findall(chunk):
        text = _strip_html(li_html)
        if not text:
            continue
        steps.append(_step_from_block(text=text, html_block=li_html))
    return steps


def _parse_h3_steps(chunk: str) -> list[dict]:
    parts = _RE_H3_SPLIT.split(chunk)
    steps: list[dict] = []
    saw_step_one = False

    for i in range(1, len(parts), 2):
        heading = _strip_html(parts[i])
        body = parts[i + 1] if i + 1 < len(parts) else ""
        if not heading:
            continue
        if _RE_STEP_HEADING.match(heading):
            if heading.lower().startswith("step 1."):
                if saw_step_one:
                    break
                saw_step_one = True

        nested = [_strip_html(li) for li in _RE_LI.findall(body)]
        nested = [t for t in nested if t]
        if nested:
            text = f"{heading} {' '.join(nested)}"
        else:
            body_text = _strip_html(re.split(r"<h[34][^>]*>", body, maxsplit=1, flags=re.I)[0])
            text = f"{heading} {body_text}".strip() if body_text else heading

        if text:
            steps.append(_step_from_block(text=text, html_block=body))
    return steps


def _parse_section_steps(chunk: str) -> list[dict]:
    li_steps = _parse_li_steps(chunk)
    has_li_images = any(s.get("image_src") for s in li_steps)
    h3_steps = _parse_h3_steps(chunk)

    if has_li_images:
        return li_steps
    if h3_steps:
        return h3_steps
    return li_steps


def _parse_sections(html_text: str, *, dedupe_titles: bool = False) -> list[dict]:
    main = _RE_MAIN.search(html_text)
    body = main.group(1) if main else html_text
    chunks = _RE_H2_SPLIT.split(body)
    sections: list[dict] = []
    seen_titles: set[str] = set()

    for chunk in chunks[1:]:
        title_m = re.match(r"([^<]+)", chunk)
        title = _strip_html(title_m.group(1)) if title_m else "Untitled"
        key = title.lower()
        if dedupe_titles and key in seen_titles:
            continue
        seen_titles.add(key)
        if re.search(r"related topics?|need more help|see also|more resources", title, re.I):
            continue
        steps = _parse_section_steps(chunk)
        if steps:
            sections.append({"title": title, "steps": steps})
    return sections


def _page_title(html_text: str) -> str:
    m = _RE_TITLE.search(html_text)
    if not m:
        return "Microsoft Support guide"
    return html.unescape(m.group(1)).replace(" - Microsoft Support", "").strip()


def _download_image(client: httpx.Client, url: str) -> tuple[bytes, str]:
    resp = client.get(url)
    resp.raise_for_status()
    ext = _detect_ext(resp.content)
    return resp.content, ext


def _slugify(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]+", "-", value.lower()).strip("-") or "guide"


def extract_guide(
    client: httpx.Client,
    *,
    guide_id: str,
    url: str,
    topic_id: str,
    output_dir: Path,
    sections_include: list[str] | None = None,
    dedupe_section_titles: bool = False,
    dry_run: bool = False,
) -> dict | None:
    html_text = _fetch_html(client, url)
    title = _page_title(html_text)
    if title.lower().startswith("this article has been retired"):
        return None
    sections = _parse_sections(html_text, dedupe_titles=dedupe_section_titles)

    if sections_include:
        allow = {s.lower() for s in sections_include}
        matched = [s for s in sections if s["title"].lower() in allow]
        sections = matched[:1] if matched else []

    guide_dir = output_dir / "guides" / guide_id
    if not dry_run:
        guide_dir.mkdir(parents=True, exist_ok=True)

    global_step = 0
    out_sections: list[dict] = []

    for section in sections:
        out_steps: list[dict] = []
        for step in section["steps"]:
            global_step += 1
            entry: dict = {
                "step": global_step,
                "text": step["text"],
                "caption": step.get("caption"),
                "image": None,
            }
            src = step.get("image_src")
            if src:
                full_url = _resolve_url(src, url)
                filename = f"step-{global_step:02d}{'.png' if dry_run else ''}"
                if not dry_run:
                    data, ext = _download_image(client, full_url)
                    filename = f"step-{global_step:02d}{ext}"
                    (guide_dir / filename).write_bytes(data)
                entry["image"] = filename
                entry["image_url"] = full_url
            out_steps.append(entry)

        out_sections.append({"title": section["title"], "steps": out_steps})

    domains = infer_domains(title, url)
    keywords = keywords_from_title(title)
    resolved_topic = topic_id if topic_id != "general/uncategorized" else _topic_id_from_domains(domains)

    guide_doc = {
        "id": guide_id,
        "topic_id": resolved_topic,
        "domains": domains,
        "keywords": keywords,
        "title": title,
        "source_url": url,
        "attribution": "Microsoft Support",
        "license_note": (
            "Screenshots from support.microsoft.com. Confirm redistribution "
            "with your legal team before use in a shipped product."
        ),
        "sections": out_sections,
        "step_count": global_step,
        "image_count": sum(1 for s in out_sections for st in s["steps"] if st.get("image")),
    }

    if not dry_run:
        with (guide_dir / "guide.json").open("w", encoding="utf-8") as f:
            json.dump(guide_doc, f, indent=2, ensure_ascii=False)

    return guide_doc


def _topic_id_from_domains(domains: list[str]) -> str:
    if not domains:
        return "general/windows"
    primary = domains[0]
    return f"{primary}/support_guide"


def _extract_url_job(
    url: str,
    output_dir: Path,
    *,
    min_images: int,
    dry_run: bool,
) -> dict | None:
    guide_id = guide_id_from_url(url)
    with httpx.Client(
        follow_redirects=True,
        timeout=60.0,
        headers={"User-Agent": _USER_AGENT},
    ) as client:
        doc = extract_guide(
            client,
            guide_id=guide_id,
            url=url,
            topic_id=_topic_id_from_domains(infer_domains("", url)),
            output_dir=output_dir,
            dedupe_section_titles=True,
            dry_run=dry_run,
        )
    if not doc or doc.get("image_count", 0) < min_images:
        if not dry_run and doc and doc.get("image_count", 0) < min_images:
            guide_dir = output_dir / "guides" / guide_id
            if guide_dir.exists():
                shutil.rmtree(guide_dir)
        return None
    return {
        "id": doc["id"],
        "topic_id": doc["topic_id"],
        "domains": doc.get("domains", []),
        "keywords": doc.get("keywords", []),
        "title": doc["title"],
        "source_url": doc["source_url"],
        "step_count": doc["step_count"],
        "image_count": doc["image_count"],
        "path": f"guides/{guide_id}/guide.json",
    }


def crawl_support_guides(
    output_dir: Path,
    *,
    urls: list[str] | None = None,
    min_images: int = 1,
    max_articles: int | None = None,
    workers: int = 6,
    dry_run: bool = False,
) -> list[dict]:
    with httpx.Client(
        follow_redirects=True,
        timeout=120.0,
        headers={"User-Agent": _USER_AGENT},
    ) as client:
        discovered = urls or discover_windows_urls(client)
    if max_articles:
        discovered = discovered[:max_articles]

    print(f"Crawling {len(discovered)} Windows Support article(s)…")
    extracted: list[dict] = []
    failed = 0

    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = {
            pool.submit(
                _extract_url_job,
                url,
                output_dir,
                min_images=min_images,
                dry_run=dry_run,
            ): url
            for url in discovered
        }
        for i, future in enumerate(as_completed(futures), start=1):
            url = futures[future]
            try:
                entry = future.result()
                if entry:
                    extracted.append(entry)
                    print(
                        f"  [{i}/{len(discovered)}] OK {entry['image_count']} img — "
                        f"{entry['title'][:55]}"
                    )
                else:
                    print(f"  [{i}/{len(discovered)}] skip (no step images) — {url[-48:]}")
            except Exception as exc:
                failed += 1
                print(f"  [{i}/{len(discovered)}] FAILED — {url[-48:]}: {exc}", file=sys.stderr)

    extracted.sort(key=lambda e: (-e["image_count"], e["title"]))
    print(f"\nExtracted {len(extracted)} guides with screenshots ({failed} failed).")
    return extracted


def _clean_output(output_dir: Path) -> None:
    guides = output_dir / "guides"
    if guides.exists():
        shutil.rmtree(guides)
    manifest = output_dir / "guides_manifest.json"
    if manifest.exists():
        manifest.unlink()
    legacy = output_dir / "manifest.json"
    if legacy.exists():
        legacy.unlink()
    for child in output_dir.iterdir():
        if child.is_dir() and child.name != "guides":
            shutil.rmtree(child)
        elif child.is_file() and child.name not in (".gitkeep",):
            child.unlink()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", "-o", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--clean", action="store_true", help="Remove old kb_visual_assets content first")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--url", help="Extract a single Support URL (optional)")
    parser.add_argument("--guide-id", default="custom_guide")
    parser.add_argument("--topic-id", default="general/uncategorized")
    parser.add_argument(
        "--crawl",
        action="store_true",
        help="Discover all en-us/windows articles via sitemap and extract guides with screenshots",
    )
    parser.add_argument("--discover-only", action="store_true", help="Save discovered URLs to article_index.json")
    parser.add_argument("--min-images", type=int, default=1, help="Minimum step screenshots per guide (crawl mode)")
    parser.add_argument("--max-articles", type=int, default=None, help="Limit articles processed in crawl mode")
    parser.add_argument("--workers", type=int, default=6, help="Parallel download workers for crawl mode")
    args = parser.parse_args()

    output_dir: Path = args.output.resolve()
    if args.clean and not args.dry_run:
        _clean_output(output_dir)
        print(f"Cleaned {output_dir}")

    if args.discover_only:
        with httpx.Client(
            follow_redirects=True,
            timeout=120.0,
            headers={"User-Agent": _USER_AGENT},
        ) as client:
            urls = discover_windows_urls(client)
        DEFAULT_INDEX.write_text(json.dumps({"urls": urls, "count": len(urls)}, indent=2), encoding="utf-8")
        print(f"Wrote {len(urls)} URLs to {DEFAULT_INDEX}")
        return 0

    if args.crawl:
        urls = None
        if DEFAULT_INDEX.is_file():
            data = json.loads(DEFAULT_INDEX.read_text(encoding="utf-8"))
            urls = data.get("urls")
        extracted = crawl_support_guides(
            output_dir,
            urls=urls,
            min_images=args.min_images,
            max_articles=args.max_articles,
            workers=args.workers,
            dry_run=args.dry_run,
        )
    elif args.url:
        guides = [{
            "id": args.guide_id,
            "topic_id": args.topic_id,
            "url": args.url,
        }]
        extracted = []
    else:
        guides = _load_config().get("guides", [])
        extracted = []

    if not args.crawl:
        if not guides:
            print("No guides configured.", file=sys.stderr)
            return 1

    if not args.crawl:
        extracted = []
    if not args.crawl:
        with httpx.Client(
            follow_redirects=True,
            timeout=60.0,
            headers={"User-Agent": _USER_AGENT},
        ) as client:
            for g in guides:
                gid = g["id"]
                print(f"\nExtracting {gid} …")
                print(f"  {g['url']}")
                try:
                    doc = extract_guide(
                        client,
                        guide_id=gid,
                        url=g["url"],
                        topic_id=g.get("topic_id", "general/uncategorized"),
                        output_dir=output_dir,
                        sections_include=g.get("sections_include"),
                        dry_run=args.dry_run,
                    )
                    if not doc:
                        print("  -> skipped (retired or empty)")
                        continue
                    extracted.append({
                        "id": doc["id"],
                        "topic_id": doc["topic_id"],
                        "domains": doc.get("domains", []),
                        "keywords": doc.get("keywords", []),
                        "title": doc["title"],
                        "source_url": doc["source_url"],
                        "step_count": doc["step_count"],
                        "image_count": doc["image_count"],
                        "path": f"guides/{gid}/guide.json",
                    })
                    print(f"  -> {doc['step_count']} steps, {doc['image_count']} images")
                except Exception as exc:
                    print(f"  FAILED: {exc}", file=sys.stderr)

    total_images = sum(g.get("image_count", 0) for g in extracted)
    manifest = {
        "version": 3,
        "source": "support.microsoft.com",
        "description": "Visual step guides extracted from Microsoft Support Windows articles.",
        "attribution": "Microsoft Support — https://support.microsoft.com",
        "guide_count": len(extracted),
        "total_images": total_images,
        "guides": extracted,
    }

    if args.dry_run:
        print(f"\n[dry-run] Would write {len(extracted)} guide(s)")
        return 0

    output_dir.mkdir(parents=True, exist_ok=True)
    with (output_dir / "guides_manifest.json").open("w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
    print(f"\nWrote {output_dir / 'guides_manifest.json'} ({len(extracted)} guides)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
