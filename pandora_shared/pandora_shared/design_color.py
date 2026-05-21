"""Contrast helpers for semantic foreground/background token pairs."""

from __future__ import annotations

import re
from typing import Any

# Common dark text colors LLMs use on primary fills (fail contrast on orange/blue).
_DARK_TEXT_RE = re.compile(
    r"color\s*:\s*(?:"
    r"#(?:000000|000|111|222|333|334155|0f172a|1e293b)"
    r"|black"
    r"|rgb\(\s*0\s*,"
    r")",
    re.IGNORECASE,
)

_PRIMARY_BG_RE = re.compile(
    r"background(?:-color)?\s*:\s*[^;]*(?:var\(--primary\)|primary)",
    re.IGNORECASE,
)


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int] | None:
    raw = hex_color.strip().lstrip("#")
    if len(raw) == 3:
        raw = "".join(ch * 2 for ch in raw)
    if len(raw) != 6:
        return None
    try:
        return int(raw[0:2], 16), int(raw[2:4], 16), int(raw[4:6], 16)
    except ValueError:
        return None


def _relative_luminance(r: int, g: int, b: int) -> float:
    def channel(c: int) -> float:
        x = c / 255.0
        return x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4

    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)


def contrasting_foreground(background_hex: str) -> str:
    """Pick light or dark text for a solid background (WCAG luminance heuristic)."""
    rgb = _hex_to_rgb(background_hex)
    if rgb is None:
        return "#ffffff"
    r, g, b = rgb
    if _relative_luminance(r, g, b) < 0.45:
        return "#ffffff"
    return "#0f172a"


def enrich_semantic_color_tokens(tokens: dict[str, Any]) -> dict[str, Any]:
    """Add on-* foreground tokens and base surface/text roles when missing."""
    out: dict[str, Any] = dict(tokens)

    for role in ("primary", "secondary", "accent"):
        bg = out.get(role)
        if isinstance(bg, str) and _hex_to_rgb(bg):
            on_key = f"on_{role}"
            out.setdefault(on_key, contrasting_foreground(bg))

    out.setdefault("surface", "#ffffff")
    out.setdefault("on_surface", contrasting_foreground(str(out["surface"])))
    out.setdefault("text", "#0f172a")
    out.setdefault("text_muted", "#64748b")
    return out


def css_primary_background_with_dark_text(css: str) -> bool:
    """True if CSS likely sets dark text on a primary-colored background."""
    if not css or not _PRIMARY_BG_RE.search(css):
        return False
    if not _DARK_TEXT_RE.search(css):
        return False
    if "on-primary" in css.lower() or "on_primary" in css:
        return False
    return True
