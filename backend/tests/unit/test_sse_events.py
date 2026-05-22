"""Unit tests for canonical SSE event type registry."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pandora_shared.sse_events import (  # noqa: E402
    ALL_SSE_EVENT_TYPES,
    COMPONENT_REVISION_STARTED,
    COMPONENT_VALIDATED,
    PIPELINE_COMPLETE,
    STORYBOOK_SSE_EVENT_TYPES,
    TOKEN_REGENERATION_STARTED,
)


class SseEventsTests(unittest.TestCase):
    def test_storybook_events_in_registry(self) -> None:
        self.assertIn(TOKEN_REGENERATION_STARTED, STORYBOOK_SSE_EVENT_TYPES)
        self.assertIn(COMPONENT_REVISION_STARTED, STORYBOOK_SSE_EVENT_TYPES)

    def test_pipeline_complete_not_project_completed(self) -> None:
        self.assertEqual(PIPELINE_COMPLETE, "pipeline_complete")
        self.assertNotIn("project_completed", ALL_SSE_EVENT_TYPES)

    def test_component_outcomes_in_pipeline_set(self) -> None:
        self.assertIn(COMPONENT_VALIDATED, ALL_SSE_EVENT_TYPES)


if __name__ == "__main__":
    unittest.main()
