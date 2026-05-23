"""Unit tests for pipeline consumer helpers."""

import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services import pipeline_state
from app.services.pipeline_consumer import (
    merge_parse_results,
    make_parses_complete_callback,
    trigger_brief_work,
)
from app.services.pipeline_state import PipelineState
from pandora_shared.events import PipelineEvent
from pandora_shared.queues import BRIEF_REQUEST


class MergeParseResultsTests(unittest.TestCase):
    def test_merge_combines_sources(self) -> None:
        state = PipelineState(
            project_id=1,
            pipeline_id=1,
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
            pipeline_id=1,
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

    async def test_trigger_brief_work_enqueues_request(self) -> None:
        pipeline_id = 42
        state = PipelineState(
            project_id=42,
            pipeline_id=pipeline_id,
            parse_results={"text": {"source": "text", "data": {}}},
        )

        with (
            patch("app.services.pipeline_consumer.async_session") as mock_session_ctx,
            patch(
                "app.services.pipeline_consumer.mark_brief_requested",
                new_callable=AsyncMock,
            ),
            patch(
                "app.services.pipeline_consumer.enqueue_outbox",
                new_callable=AsyncMock,
                return_value=True,
            ) as enqueue_outbox,
        ):
            db = AsyncMock()
            mock_session_ctx.return_value.__aenter__.return_value = db
            await trigger_brief_work(state)

        enqueue_outbox.assert_awaited_once()
        args = enqueue_outbox.await_args.args
        self.assertEqual(args[1], BRIEF_REQUEST)
        envelope = args[2]
        self.assertEqual(envelope.event, PipelineEvent.BRIEF_REQUEST)
        self.assertEqual(envelope.project_id, 42)
        self.assertEqual(envelope.pipeline_id, pipeline_id)
        self.assertIn("text", envelope.payload["sources"])
        db.commit.assert_awaited_once()

    async def test_parses_complete_callback_delegates_to_trigger(self) -> None:
        pipeline_id = 42
        state = PipelineState(
            project_id=1,
            pipeline_id=pipeline_id,
            parse_results={"text": {"source": "text"}},
        )
        callback = make_parses_complete_callback()

        with patch(
            "app.services.pipeline_consumer.trigger_brief_work",
            new_callable=AsyncMock,
        ) as trigger_brief:
            await callback(state)

        trigger_brief.assert_awaited_once_with(state)


if __name__ == "__main__":
    unittest.main()
