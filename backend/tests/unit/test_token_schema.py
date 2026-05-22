"""Unit tests for storybook token schema constants."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pandora_shared.token_schema import (  # noqa: E402
    EDITABLE_TOKEN_KEYS,
    storybook_token_schema,
)


class TokenSchemaTests(unittest.TestCase):
    def test_editable_includes_primary(self) -> None:
        self.assertIn("primary", EDITABLE_TOKEN_KEYS)

    def test_storybook_token_schema_shape(self) -> None:
        schema = storybook_token_schema()
        self.assertIn("editable", schema)
        self.assertGreaterEqual(len(schema["semantic_pairs"]), 1)
        pair = schema["semantic_pairs"][0]
        self.assertEqual(pair["background"], "primary")
        self.assertEqual(pair["foreground"], "on_primary")


if __name__ == "__main__":
    unittest.main()
