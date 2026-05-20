"""Heuristic design-token extraction from crawled HTML/CSS."""

from __future__ import annotations

import re
from collections.abc import Iterable

_HEX_COLOR_RE = re.compile(r"#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})\b")
_RGB_COLOR_RE = re.compile(
    r"\b(?:rgb|rgba|hsl|hsla)\(\s*[\d.%\s,]+\s*\)",
    re.IGNORECASE,
)
_FONT_FAMILY_RE = re.compile(
    r"font-family\s*:\s*([^;}{]+)",
    re.IGNORECASE,
)
_GOOGLE_FONT_RE = re.compile(
    r"fonts\.googleapis\.com/css2?\?family=([^&\"'\s]+)",
    re.IGNORECASE,
)

# CSS generic fallbacks — drop from brief-facing font lists (keep brand families).
_GENERIC_FONT_TOKENS: frozenset[str] = frozenset(
    {
        "system-ui",
        "sans-serif",
        "serif",
        "monospace",
        "cursive",
        "fantasy",
        "inherit",
        "initial",
        "unset",
        "-apple-system",
        "blinkmacsystemfont",
        "segoe ui",
        "roboto",
        "helvetica",
        "helvetica neue",
        "arial",
        "ubuntu",
        "noto sans",
        "liberation sans",
        "franklin gothic medium",
        "arial black",
        "avenir",
        "times",
        "times new roman",
        "courier",
        "courier new",
        "georgia",
        "verdana",
        "tahoma",
        "trebuchet ms",
        "impact",
        "comic sans ms",
    }
)


def filter_font_list(fonts: Iterable[str], *, limit: int = 8) -> list[str]:
    """Keep distinctive font names; remove CSS stack noise."""
    out: list[str] = []
    for raw in fonts:
        name = raw.strip().strip("\"'").split(",")[0].strip()
        if not name:
            continue
        key = name.lower()
        if key in _GENERIC_FONT_TOKENS:
            continue
        if name not in out:
            out.append(name)
        if len(out) >= limit:
            break
    return out


_COMPONENT_HINTS: tuple[tuple[str, str], ...] = (
    ("button", "Button"),
    ("call-to-action", "Button"),
    ("cta", "Button"),
    ("card", "Card"),
    ("bento", "Card"),
    ("hero", "Hero"),
    ("navigation", "Navigation"),
    ("nav bar", "Navigation"),
    ("navbar", "Navigation"),
    ("footer", "Footer"),
    ("accordion", "Accordion"),
    ("carousel", "Carousel"),
    ("logo bar", "LogoBar"),
    ("scrolling logo", "LogoBar"),
    ("dropdown", "Dropdown"),
    ("form", "Form"),
    ("input", "Input"),
    ("stat card", "StatCard"),
    ("pricing", "PricingTable"),
    ("modal", "Modal"),
    ("grid", "Grid"),
)


def extract_colors(html: str, *, limit: int = 24) -> list[str]:
    if not html:
        return []
    found: list[str] = []
    for match in _HEX_COLOR_RE.findall(html):
        normalized = match.lower()
        if len(normalized) == 4:
            normalized = f"#{normalized[1]}{normalized[1]}{normalized[2]}{normalized[2]}{normalized[3]}{normalized[3]}"
        if normalized not in found:
            found.append(normalized)
    for match in _RGB_COLOR_RE.findall(html):
        if match not in found:
            found.append(match)
        if len(found) >= limit:
            break
    return found[:limit]


def _clean_font_name(raw: str) -> str | None:
    name = raw.strip().strip("\"'").split(",")[0].strip()
    if not name or name.lower() in {"inherit", "initial", "unset", "system-ui", "sans-serif", "serif"}:
        return None
    return name


def extract_fonts(html: str, *, limit: int = 12) -> list[str]:
    if not html:
        return []
    fonts: list[str] = []
    for match in _FONT_FAMILY_RE.findall(html):
        cleaned = _clean_font_name(match)
        if cleaned and cleaned not in fonts:
            fonts.append(cleaned)
    for match in _GOOGLE_FONT_RE.findall(html):
        family = match.replace("+", " ").split(":")[0].strip()
        if family and family not in fonts:
            fonts.append(family)
    return filter_font_list(fonts, limit=limit)


def infer_component_candidates(*texts: str) -> list[str]:
    """Guess UI building blocks mentioned in crawl markdown / layout hints."""
    blob = " ".join(t for t in texts if t).lower()
    candidates: list[str] = []
    for needle, label in _COMPONENT_HINTS:
        if needle in blob and label not in candidates:
            candidates.append(label)
    return candidates
