"""Normalize component variant JSON for API responses."""

from __future__ import annotations

from typing import Any


def variants_for_api(raw: Any) -> list[dict[str, Any]] | None:
    """
    Coerce stored variants to ``list[dict]`` for Pydantic models.

    Workers persist variant names as strings (e.g. ``["default", "primary"]``);
    some paths may already store objects (e.g. ``{"name": "primary"}``).
    """
    if raw is None:
        return None
    if not isinstance(raw, list):
        return None

    out: list[dict[str, Any]] = []
    for item in raw:
        if isinstance(item, str):
            name = item.strip()
            if name:
                out.append({"name": name})
        elif isinstance(item, dict):
            out.append(dict(item))
    return out if out else None
