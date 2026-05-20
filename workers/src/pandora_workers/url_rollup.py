"""Build token-efficient ``ParseUrlAgent`` result payloads."""

from __future__ import annotations

import json
from collections.abc import Iterable
from typing import Any

from pandora_workers.url_extract import filter_font_list

MAX_COLORS = 12
MAX_KEYWORDS = 16
MAX_COMPONENT_CANDIDATES = 15

_ROLLUP_KEYS = (
    "summary",
    "keywords",
    "fonts",
    "colors",
    "component_candidates",
    "layout_hints",
    "tone_hints",
)


def dedupe_strings(items: Iterable[object]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        text = str(item).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
    return out


def normalize_page_summary(summary: dict[str, Any], *, url: str) -> dict[str, Any]:
    """Normalize one per-page LLM result (fonts filtered, lists capped)."""
    fonts = filter_font_list(summary.get("fonts") or [])
    colors = dedupe_strings(summary.get("colors") or [])[:MAX_COLORS]
    keywords = dedupe_strings(summary.get("keywords") or [])[:MAX_KEYWORDS]
    components = dedupe_strings(summary.get("component_candidates") or [])[:MAX_COMPONENT_CANDIDATES]
    return {
        "url": url,
        "summary": (summary.get("summary") or "").strip()[:2000] or None,
        "keywords": keywords,
        "fonts": fonts,
        "colors": colors,
        "component_candidates": components,
        "layout_hints": (summary.get("layout_hints") or "").strip()[:1000] or None,
        "tone_hints": (summary.get("tone_hints") or "").strip()[:200] or None,
    }


def rollup_from_pages(pages: list[dict[str, Any]]) -> dict[str, Any]:
    """Mechanical merge when only one page (no second LLM)."""
    if len(pages) != 1:
        raise ValueError("rollup_from_pages expects exactly one normalized page")
    page = pages[0]
    return {key: page.get(key) for key in _ROLLUP_KEYS}


def compact_pages_for_synthesis(pages: list[dict[str, Any]]) -> str:
    """JSON blob for multi-page synthesis prompt (per-page detail only)."""
    return json.dumps(pages, ensure_ascii=False, separators=(",", ":"))


def apply_synthesized_rollup(
    synthesized: dict[str, Any],
    *,
    urls: list[str],
    pages: list[dict[str, Any]],
    crawl_success_count: int,
) -> dict[str, Any]:
    """Top-level brief input from second LLM pass; keep ``pages`` for audit."""
    return {
        "urls": urls,
        "crawl_success_count": crawl_success_count,
        "summary": (synthesized.get("summary") or "").strip()[:2000] or None,
        "keywords": dedupe_strings(synthesized.get("keywords") or [])[:MAX_KEYWORDS],
        "fonts": filter_font_list(synthesized.get("fonts") or []),
        "colors": dedupe_strings(synthesized.get("colors") or [])[:MAX_COLORS],
        "component_candidates": dedupe_strings(synthesized.get("component_candidates") or [])[
            :MAX_COMPONENT_CANDIDATES
        ],
        "layout_hints": (synthesized.get("layout_hints") or "").strip()[:1000] or None,
        "tone_hints": (synthesized.get("tone_hints") or "").strip()[:200] or None,
        "pages": pages,
    }
