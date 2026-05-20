"""Unit tests for in-memory pipeline state."""

import unittest
from unittest.mock import patch
from uuid import uuid4

from app.models.thread_message import ThreadMessage
from app.services import pipeline_state
from pandora_shared.enums import MessageRole


class PipelineStateTests(unittest.TestCase):
    def setUp(self) -> None:
        pipeline_state.pipeline_states.clear()

    def tearDown(self) -> None:
        pipeline_state.pipeline_states.clear()

    def test_modalities_text_only(self) -> None:
        message = ThreadMessage(
            project_id=1,
            user_id=1,
            role=MessageRole.user,
            content="hello",
        )
        self.assertEqual(pipeline_state.modalities_from_message(message), {"text"})

    def test_init_state_sets_parse_expected_from_modalities(self) -> None:
        message = ThreadMessage(
            project_id=1,
            user_id=1,
            role=MessageRole.user,
            content="hello",
            input_urls=["https://example.com"],
        )
        pipeline_id = uuid4()
        state = pipeline_state.init_state_from_thread(1, pipeline_id, message)
        self.assertEqual(state.parse_expected, 2)
        self.assertEqual(state.parse_pending, {"text", "url"})
        self.assertEqual(state.parse_received, 0)
        self.assertEqual(state.url_count, 1)

    def test_url_parse_timeout_delay_scales_with_multiple_urls(self) -> None:
        pipeline_id = uuid4()
        message = ThreadMessage(
            project_id=1,
            user_id=1,
            role=MessageRole.user,
            content="hello",
            input_urls=["https://a.example", "https://b.example"],
        )
        pipeline_state.init_state_from_thread(1, pipeline_id, message)
        delay = pipeline_state._parse_timeout_delay_seconds(pipeline_id, "url")
        # max(150, 120 + 100*2 + 90) == 410
        self.assertEqual(delay, 410.0)

    def test_text_parse_timeout_uses_flat_constant(self) -> None:
        pipeline_id = uuid4()
        message = ThreadMessage(
            project_id=1,
            user_id=1,
            role=MessageRole.user,
            content="hello",
            input_urls=["https://a.example", "https://b.example"],
        )
        pipeline_state.init_state_from_thread(1, pipeline_id, message)
        with patch.object(pipeline_state, "PARSE_TIMEOUT_SECONDS", 99):
            self.assertEqual(
                pipeline_state._parse_timeout_delay_seconds(pipeline_id, "text"), 99.0
            )
        pipeline_id = uuid4()
        message = ThreadMessage(
            project_id=1,
            user_id=1,
            role=MessageRole.user,
            content="a",
            input_urls=["https://example.com"],
        )
        pipeline_state.init_state_from_thread(1, pipeline_id, message)

        self.assertFalse(
            pipeline_state.record_parse_result(pipeline_id, "text", {"source": "text"})
        )
        self.assertTrue(
            pipeline_state.record_parse_result(pipeline_id, "url", {"source": "url"})
        )


class PipelineStateAsyncTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        pipeline_state.pipeline_states.clear()

    def tearDown(self) -> None:
        pipeline_state.pipeline_states.clear()

    async def test_parse_timeout_increments_received(self) -> None:
        message = ThreadMessage(
            project_id=1,
            user_id=1,
            role=MessageRole.user,
            content="only text",
        )
        pipeline_id = uuid4()
        pipeline_state.init_state_from_thread(1, pipeline_id, message)
        pipeline_state.schedule_parse_timeouts(pipeline_id)

        with patch.object(pipeline_state, "PARSE_TIMEOUT_SECONDS", 0.01):
            for task in pipeline_state.get_state(pipeline_id)._timeout_tasks:
                task.cancel()
            complete = await pipeline_state.apply_parse_timeout(pipeline_id, "text")

        state = pipeline_state.get_state(pipeline_id)
        self.assertTrue(complete)
        self.assertEqual(state.parse_received, 1)
        self.assertEqual(state.parse_pending, set())
        self.assertEqual(state.parse_results["text"]["error"], "timeout")


if __name__ == "__main__":
    unittest.main()
