"""Unit tests for storybook publish helpers."""

from __future__ import annotations

import unittest
from uuid import uuid4

from app.services.storybook_publish import build_component_generate_envelope
from pandora_shared.events import MessageEnvelope


class _Component:
    id = 42
    spec_index = 0
    retry_count = 1
    revision_round = 2
    revision_instruction = "fix button"


class _Schema:
    component_specs = [{"name": "Button", "type": "button"}]


class BuildEnvelopeTests(unittest.TestCase):
    def test_build_component_generate_envelope_shape(self) -> None:
        pipeline_id = uuid4()
        envelope = build_component_generate_envelope(
            project_id=10,
            pipeline_id=pipeline_id,
            component=_Component(),  # type: ignore[arg-type]
            schema=_Schema(),  # type: ignore[arg-type]
            design_tokens={"primary": "#fff"},
            global_config={"theme": "light"},
            revision_instruction="fix button",
            revision_round=3,
        )
        self.assertIsInstance(envelope, MessageEnvelope)
        self.assertEqual(envelope.project_id, 10)
        self.assertEqual(envelope.pipeline_id, pipeline_id)
        self.assertEqual(envelope.component_id, 42)
        self.assertEqual(envelope.attempt.revision_round, 3)
        self.assertEqual(envelope.attempt.retry_count, 1)
        self.assertEqual(envelope.payload["spec"]["name"], "Button")
        self.assertTrue(envelope.payload["storybook_ad_hoc"])


if __name__ == "__main__":
    unittest.main()
