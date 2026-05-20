"""Heuristic color and layout extraction from images (no vision LLM)."""

from __future__ import annotations

import io
from typing import Any

from PIL import Image


def _rgb_to_hex(r: int, g: int, b: int) -> str:
    return f"#{r:02x}{g:02x}{b:02x}"


def _quantize_colors(image: Image.Image, *, clusters: int = 6) -> list[str]:
    reduced = image.convert("RGB").resize((160, 160))
    quantized = reduced.quantize(colors=clusters, method=Image.Quantize.MEDIANCUT)
    palette = quantized.getpalette()
    if palette is None:
        return []
    counts = quantized.histogram()
    colors: list[tuple[int, str]] = []
    for index, count in enumerate(counts):
        if count == 0:
            continue
        base = index * 3
        r, g, b = palette[base], palette[base + 1], palette[base + 2]
        colors.append((count, _rgb_to_hex(r, g, b)))
    colors.sort(reverse=True)
    seen: set[str] = set()
    ordered: list[str] = []
    for _, hex_color in colors:
        if hex_color in seen:
            continue
        seen.add(hex_color)
        ordered.append(hex_color)
    return ordered[:clusters]


def _assign_color_roles(palette: list[str]) -> dict[str, str]:
    if not palette:
        return {}
    roles: dict[str, str] = {"primary": palette[0]}
    if len(palette) > 1:
        roles["secondary"] = palette[1]
    if len(palette) > 2:
        roles["accent"] = palette[2]
    return roles


def _layout_hint(width: int, height: int) -> str:
    ratio = width / max(height, 1)
    if ratio > 1.4:
        return "wide landscape layout, likely marketing or dashboard screenshot"
    if ratio < 0.8:
        return "tall portrait layout, likely mobile screenshot"
    return "balanced aspect ratio, general UI or brand reference"


def analyze_image_bytes(data: bytes) -> dict[str, Any]:
    """Return parse ``data`` fields from raw image bytes."""
    with Image.open(io.BytesIO(data)) as image:
        rgb = image.convert("RGB")
        width, height = rgb.size
        palette = _quantize_colors(rgb)
        return {
            "palette": palette,
            "color_roles": _assign_color_roles(palette),
            "layout_hints": _layout_hint(width, height),
            "dimensions": {"width": width, "height": height},
            "extraction_method": "pill_heuristic",
        }
