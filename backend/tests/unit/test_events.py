"""Unit tests for pipeline event helpers."""

import unittest
from uuid import uuid4

from pandora_shared.events import (
    MessageEnvelope,
    PipelineEvent,
    parse_results_idempotency_event,
    parse_source_from_envelope,
)
from pandora_shared.payloads import ParseResultPayload


class EventHelperTests(unittest.TestCase):
    def test_parse_results_idempotency_event_includes_source(self) -> None:
        self.assertEqual(
            parse_results_idempotency_event("text"),
            "pandora.parse.results:text",
        )

    def test_parse_source_from_envelope(self) -> None:
        envelope = MessageEnvelope(
            event=PipelineEvent.PARSE_RESULTS,
            project_id=1,
            pipeline_id=1,
            payload=ParseResultPayload(source="image", data={"urls": []}).model_dump(),
        )
        self.assertEqual(parse_source_from_envelope(envelope), "image")

    def test_parse_source_from_envelope_rejects_wrong_event(self) -> None:
        envelope = MessageEnvelope(
            event=PipelineEvent.BRIEF_READY,
            project_id=1,
            pipeline_id=1,
            payload={},
        )
        with self.assertRaises(ValueError):
            parse_source_from_envelope(envelope)


if __name__ == "__main__":
    unittest.main()
