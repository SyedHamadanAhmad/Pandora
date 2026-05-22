"""Static token editor schema for storybook overview (Phase 1a)."""

from __future__ import annotations

from typing import Any

# Keys the overview may edit; server validates PATCH/apply against this list (Phase 1b).
EDITABLE_TOKEN_KEYS: tuple[str, ...] = (
    "primary",
    "secondary",
    "accent",
    "radius",
    "surface",
    "text",
    "text_muted",
)

# Background role -> foreground token (snake_case keys; API camelCases via Pydantic).
SEMANTIC_TOKEN_PAIRS: tuple[dict[str, str], ...] = (
    {"background": "primary", "foreground": "on_primary"},
    {"background": "secondary", "foreground": "on_secondary"},
    {"background": "accent", "foreground": "on_accent"},
    {"background": "surface", "foreground": "on_surface"},
)


def storybook_token_schema() -> dict[str, Any]:
    """Payload fragment for ``GET /storybook`` ``tokenSchema`` field."""
    return {
        "editable": list(EDITABLE_TOKEN_KEYS),
        "semantic_pairs": [dict(pair) for pair in SEMANTIC_TOKEN_PAIRS],
    }
