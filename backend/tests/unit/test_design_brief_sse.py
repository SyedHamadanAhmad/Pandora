"""Unit tests for design_brief_ready SSE payload enrichment."""

from __future__ import annotations

import unittest

from app.services.pipeline_consumer import _design_brief_ready_sse_payload
from pandora_shared.events import MessageEnvelope
from pandora_shared.sse_events import DESIGN_BRIEF_READY


class DesignBriefSseTests(unittest.TestCase):
    def test_payload_includes_brief_fields(self) -> None:
        envelope = MessageEnvelope(
            event="pandora.brief.ready",
            project_id=7,
            pipeline_id=42,
            payload={
                "color_tokens": {"primary": "#2563eb"},
                "typography_scale": {"base": "16px"},
                "spacing_system": {"unit": 4},
                "tone": "professional",
                "component_list": ["Button"],
                "input_gaps": ["url:timeout"],
            },
        )
        event = _design_brief_ready_sse_payload(envelope)
        self.assertEqual(event["type"], DESIGN_BRIEF_READY)
        self.assertEqual(event["projectId"], 7)
        self.assertEqual(event["pipelineId"], "42")
        self.assertEqual(event["colorTokens"], {"primary": "#2563eb"})
        self.assertEqual(event["typographyScale"], {"base": "16px"})
        self.assertEqual(event["spacingSystem"], {"unit": 4})
        self.assertEqual(event["tone"], "professional")
        self.assertEqual(event["componentList"], ["Button"])
        self.assertEqual(event["inputGaps"], ["url:timeout"])


if __name__ == "__main__":
    unittest.main()
