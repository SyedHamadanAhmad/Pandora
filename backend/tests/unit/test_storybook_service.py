"""Unit tests for storybook read-model builders."""

from __future__ import annotations

import unittest

from app.schemas.storybook import StorybookSummary
from app.services.storybook_service import _enriched_tokens, _summary_counts
from pandora_shared.enums import ComponentStatus


class _FakeComponent:
    def __init__(self, status: ComponentStatus) -> None:
        self.status = status


class StorybookServiceTests(unittest.TestCase):
    def test_enriched_tokens_adds_on_primary(self) -> None:
        tokens = _enriched_tokens({"primary": "#f97316"})
        self.assertEqual(tokens["on_primary"], "#ffffff")
        self.assertIn("surface", tokens)

    def test_summary_counts(self) -> None:
        components = [
            _FakeComponent(ComponentStatus.validated),
            _FakeComponent(ComponentStatus.validated),
            _FakeComponent(ComponentStatus.failed),
            _FakeComponent(ComponentStatus.generating),
        ]
        summary = _summary_counts(components)  # type: ignore[arg-type]
        self.assertEqual(summary.total, 4)
        self.assertEqual(summary.validated, 2)
        self.assertEqual(summary.failed, 1)
        self.assertEqual(summary.generating, 1)


if __name__ == "__main__":
    unittest.main()
