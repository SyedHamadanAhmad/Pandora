"""Unit tests for pipeline consumer helpers."""

import unittest
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from app.services import pipeline_state
from app.services.pipeline_consumer import (
    merge_parse_results,
    make_parses_complete_callback,
    trigger_brief_work,
)
from app.services.pipeline_state import PipelineState
from pandora_shared.events import MessageEnvelope, PipelineEvent
from pandora_shared.queues import BRIEF_REQUEST


class MergeParseResultsTests(unittest.TestCase):
    def test_merge_combines_sources(self) -> None:
        state = PipelineState(
            project_id=1,
            pipeline_id=uuid4(),
            parse_results={
                "text": {"source": "text", "data": {"content": "hi"}},
                "url": {"source": "url", "data": {"urls": []}},
            },
        )
        merged = merge_parse_results(state)
        self.assertEqual(set(merged["sources"].keys()), {"text", "url"})
        self.assertEqual(merged["input_gaps"], [])

    def test_merge_collects_timeout_gaps(self) -> None:
        state = PipelineState(
            project_id=1,
            pipeline_id=uuid4(),
            parse_results={
                "text": {"source": "text", "data": None, "error": "timeout"},
            },
        )
        merged = merge_parse_results(state)
        self.assertEqual(merged["input_gaps"], ["text:timeout"])


class TriggerBriefWorkTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        pipeline_state.pipeline_states.clear()

    def tearDown(self) -> None:
        pipeline_state.pipeline_states.clear()

    async def test_trigger_brief_work_publishes_request(self) -> None:
        pipeline_id = uuid4()
        state = PipelineState(
            project_id=42,
            pipeline_id=pipeline_id,
            parse_results={"text": {"source": "text", "data": {}}},
        )
        broker = MagicMock()
        broker.publish = AsyncMock()

        await trigger_brief_work(state, broker)

        broker.publish.assert_awaited_once()
        queue_name, envelope = broker.publish.await_args.args
        self.assertEqual(queue_name, BRIEF_REQUEST)
        self.assertEqual(envelope.event, PipelineEvent.BRIEF_REQUEST)
        self.assertEqual(envelope.project_id, 42)
        self.assertEqual(envelope.pipeline_id, pipeline_id)
        self.assertIn("text", envelope.payload["sources"])

    async def test_parses_complete_callback_delegates_to_trigger(self) -> None:
        pipeline_id = uuid4()
        state = PipelineState(
            project_id=1,
            pipeline_id=pipeline_id,
            parse_results={"text": {"source": "text"}},
        )
        broker = MagicMock()
        broker.publish = AsyncMock()
        callback = make_parses_complete_callback(broker)

        await callback(state)

        broker.publish.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
