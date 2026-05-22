"""Unit tests for pipeline state (cache + timeout helpers)."""

import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from app.models.thread_message import ThreadMessage
from app.services import pipeline_state
from pandora_shared.enums import MessageRole

_PIPELINE_RUN_ID = 42


def _seed_state(**kwargs) -> pipeline_state.PipelineState:
    state = pipeline_state.PipelineState(
        project_id=kwargs.pop("project_id", 1),
        pipeline_id=kwargs.pop("pipeline_id", _PIPELINE_RUN_ID),
        url_count=kwargs.pop("url_count", 0),
        parse_expected=kwargs.pop("parse_expected", 1),
        parse_pending=kwargs.pop("parse_pending", {"text"}),
        **kwargs,
    )
    pipeline_state.pipeline_states[state.pipeline_id] = state
    return state


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

    def test_url_parse_timeout_delay_scales_with_multiple_urls(self) -> None:
        _seed_state(
            url_count=2,
            parse_expected=2,
            parse_pending={"text", "url"},
        )
        delay = pipeline_state._parse_timeout_delay_seconds(_PIPELINE_RUN_ID, "url")
        self.assertEqual(delay, 410.0)

    def test_text_parse_timeout_uses_flat_constant(self) -> None:
        _seed_state(
            url_count=2,
            parse_expected=2,
            parse_pending={"text", "url"},
        )
        with patch.object(pipeline_state, "PARSE_TIMEOUT_SECONDS", 99):
            self.assertEqual(
                pipeline_state._parse_timeout_delay_seconds(_PIPELINE_RUN_ID, "text"),
                99.0,
            )


class PipelineStateAsyncTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        pipeline_state.pipeline_states.clear()

    def tearDown(self) -> None:
        pipeline_state.pipeline_states.clear()

    async def test_record_parse_result_persists(self) -> None:
        _seed_state(parse_expected=2, parse_pending={"text", "url"}, parse_received=0)
        session = AsyncMock()
        run = MagicMock()
        session.get = AsyncMock(return_value=run)

        complete = await pipeline_state.record_parse_result(
            session,
            _PIPELINE_RUN_ID,
            "text",
            {"source": "text"},
        )
        self.assertFalse(complete)
        session.flush.assert_awaited()

    async def test_parse_timeout_increments_received(self) -> None:
        _seed_state(parse_expected=1, parse_pending={"text"}, parse_received=0)
        pipeline_state.schedule_parse_timeouts(_PIPELINE_RUN_ID)

        with (
            patch.object(pipeline_state, "PARSE_TIMEOUT_SECONDS", 0.01),
            patch.object(pipeline_state, "record_parse_result", new_callable=AsyncMock) as record,
        ):
            record.return_value = True
            for task in pipeline_state.pipeline_states[_PIPELINE_RUN_ID]._timeout_tasks:
                task.cancel()
            complete = await pipeline_state.apply_parse_timeout(_PIPELINE_RUN_ID, "text")

        self.assertTrue(complete)
        record.assert_awaited()


if __name__ == "__main__":
    unittest.main()
