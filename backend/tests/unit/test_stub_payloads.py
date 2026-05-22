"""Unit tests for Phase 3 stub worker payload shapes."""

import sys
import unittest
from pathlib import Path
from uuid import uuid4

if Path("/app/pandora_stub").is_dir():
    sys.path.insert(0, "/app")
else:
    sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "workers" / "stub"))

from pandora_shared.events import MessageEnvelope, PipelineEvent  # noqa: E402
from pandora_stub.downstream_worker import (  # noqa: E402
    _brief_ready_payload,
    _component_validated_payload,
    _schema_ready_payload,
    _verification_complete_payload,
)
from pandora_stub.parse_worker import _parse_data  # noqa: E402


class StubPayloadTests(unittest.TestCase):
    def test_parse_data_includes_source_specific_fields(self) -> None:
        work = MessageEnvelope(
            event=PipelineEvent.PARSE_REQUEST,
            project_id=1,
            pipeline_id=uuid4(),
            payload={"content": "hello"},
        )
        data = _parse_data("text", work)
        self.assertEqual(data["content"], "hello")
        self.assertIn("summary", data)

    def test_schema_ready_has_two_component_specs(self) -> None:
        work = MessageEnvelope(
            event=PipelineEvent.SCHEMA_REQUEST,
            project_id=1,
            pipeline_id=uuid4(),
            payload={},
        )
        payload = _schema_ready_payload(work)
        specs = payload["component_specs"]
        self.assertEqual(len(specs), 2)
        self.assertEqual(specs[0]["name"], "Button")

    def test_verification_has_no_blocking_issues(self) -> None:
        work = MessageEnvelope(
            event=PipelineEvent.VERIFICATION_COMPLETE,
            project_id=1,
            pipeline_id=uuid4(),
            payload={},
        )
        payload = _verification_complete_payload(work)
        self.assertEqual(payload["issues"], [])

    def test_component_validated_includes_tsx(self) -> None:
        work = MessageEnvelope(
            event=PipelineEvent.COMPONENT_VALIDATED,
            project_id=1,
            pipeline_id=uuid4(),
            payload={"spec": {"name": "Button"}},
        )
        payload = _component_validated_payload(work)
        self.assertIn("tsx_code", payload)
        self.assertIn("Button", payload["tsx_code"])

    def test_brief_preserves_input_gaps(self) -> None:
        work = MessageEnvelope(
            event=PipelineEvent.BRIEF_REQUEST,
            project_id=1,
            pipeline_id=uuid4(),
            payload={"input_gaps": ["text:timeout"]},
        )
        payload = _brief_ready_payload(work)
        self.assertEqual(payload["input_gaps"], ["text:timeout"])


if __name__ == "__main__":
    unittest.main()
