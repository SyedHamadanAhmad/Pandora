"""Unit tests for URL HTML design-signal extraction."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

WORKERS_SRC = Path(__file__).resolve().parents[3] / "workers" / "src"
if str(WORKERS_SRC) not in sys.path:
    sys.path.insert(0, str(WORKERS_SRC))

from pandora_workers.url_extract import (  # noqa: E402
    extract_colors,
    extract_fonts,
    filter_font_list,
    infer_component_candidates,
)


class UrlExtractTests(unittest.TestCase):
    def test_extract_hex_colors_from_html(self) -> None:
        html = '<style>.hero { color: #635bff; background: #0a2540; }</style>'
        colors = extract_colors(html)
        self.assertIn("#635bff", colors)
        self.assertIn("#0a2540", colors)

    def test_extract_fonts_from_css(self) -> None:
        html = "body { font-family: 'sohne-var', Helvetica, sans-serif; }"
        fonts = extract_fonts(html)
        self.assertTrue(any("sohne" in f.lower() for f in fonts))

    def test_filter_font_list_drops_generic_stack(self) -> None:
        fonts = filter_font_list(
            ["Inter", "system-ui", "-apple-system", "Roboto", "sans-serif"]
        )
        self.assertEqual(fonts, ["Inter"])

    def test_infer_components_from_markdown(self) -> None:
        text = "hero section with bento grid cards and footer navigation"
        names = infer_component_candidates(text)
        self.assertIn("Hero", names)
        self.assertIn("Card", names)
        self.assertIn("Footer", names)


if __name__ == "__main__":
    unittest.main()
