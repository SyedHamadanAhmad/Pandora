"""Unit tests for storybook token merge and validation (logic only)."""

from __future__ import annotations

import unittest

from fastapi import HTTPException

from app.services.storybook_tokens import merge_design_tokens, validate_and_filter_patch


class StorybookTokenLogicTests(unittest.TestCase):
    def test_merge_enriches_on_primary(self) -> None:
        merged = merge_design_tokens({"primary": "#f97316"}, {"radius": "12px"})
        self.assertEqual(merged["radius"], "12px")
        self.assertEqual(merged["on_primary"], "#ffffff")

    def test_rejects_unknown_key(self) -> None:
        with self.assertRaises(HTTPException) as ctx:
            validate_and_filter_patch({"not_a_token": "#fff"})
        self.assertEqual(ctx.exception.status_code, 400)

    def test_accepts_camel_case_keys(self) -> None:
        patch = validate_and_filter_patch({"textMuted": "#94a3b8"})
        self.assertEqual(patch["text_muted"], "#94a3b8")


if __name__ == "__main__":
    unittest.main()
