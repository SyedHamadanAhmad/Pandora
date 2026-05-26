"""Unit tests for component variant API normalization."""

from __future__ import annotations

import unittest

from app.services.variant_normalize import variants_for_api


class VariantNormalizeTests(unittest.TestCase):
    def test_string_variants_become_name_dicts(self) -> None:
        self.assertEqual(
            variants_for_api(["default", "primary"]),
            [{"name": "default"}, {"name": "primary"}],
        )

    def test_dict_variants_pass_through(self) -> None:
        raw = [{"name": "outline", "props": {"size": "sm"}}]
        self.assertEqual(variants_for_api(raw), raw)

    def test_mixed_list(self) -> None:
        self.assertEqual(
            variants_for_api(["default", {"name": "ghost"}]),
            [{"name": "default"}, {"name": "ghost"}],
        )

    def test_none_and_empty(self) -> None:
        self.assertIsNone(variants_for_api(None))
        self.assertIsNone(variants_for_api([]))


if __name__ == "__main__":
    unittest.main()
