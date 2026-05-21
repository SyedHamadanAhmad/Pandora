"""Unit tests for semantic contrast token helpers."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pandora_shared.design_color import (  # noqa: E402
    contrasting_foreground,
    css_primary_background_with_dark_text,
    enrich_semantic_color_tokens,
)


class DesignColorTests(unittest.TestCase):
    def test_orange_primary_gets_white_on_primary(self) -> None:
        self.assertEqual(contrasting_foreground("#f97316"), "#ffffff")
        tokens = enrich_semantic_color_tokens({"primary": "#f97316"})
        self.assertEqual(tokens["on_primary"], "#ffffff")

    def test_light_primary_gets_dark_on_primary(self) -> None:
        self.assertEqual(contrasting_foreground("#fde68a"), "#0f172a")

    def test_css_lint_detects_dark_on_primary(self) -> None:
        css = ".btn { background: var(--primary); color: #334155; }"
        self.assertTrue(css_primary_background_with_dark_text(css))

    def test_css_lint_allows_on_primary(self) -> None:
        css = ".btn { background: var(--primary); color: var(--on-primary); }"
        self.assertFalse(css_primary_background_with_dark_text(css))


if __name__ == "__main__":
    unittest.main()
