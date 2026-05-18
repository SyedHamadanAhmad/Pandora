"""Unit tests for pipeline consumer queue handlers."""

import json
import unittest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from app.services import pipeline_state
from app.services.idempotency import IdempotencyStatus
from app.services.pipeline_consumer import (
    _ensure_verification_if_gate_open,
    _handle_brief_ready,
    _handle_component_outcome,
    _handle_parse_results,
    _handle_schema_ready,
    _handle_showcase_ready,
    _start_verification,
)
from app.services.pipeline_state import PipelineState
from pandora_shared.events import MessageEnvelope, PipelineEvent
from pandora_shared.queues import VERIFICATION_START


def _message(body: dict) -> MagicMock:
    message = MagicMock()
    message.body = json.dumps(body).encode()
    message.ack = AsyncMock()
    message.nack = AsyncMock()
    return message


def _envelope(
    *,
    event: str,
    pipeline_id=None,
    project_id: int = 1,
    component_id: int | None = None,
    payload: dict | None = None,
) -> MessageEnvelope:
    return MessageEnvelope(
        event=event,
        project_id=project_id,
        pipeline_id=pipeline_id or uuid4(),
        component_id=component_id,
        payload=payload or {},
    )


class EnsureVerificationGateTests(unittest.IsolatedAsyncioTestCase):
    async def test_skips_when_db_resolved_below_expected(self) -> None:
        pipeline_id = uuid4()
        state = PipelineState(project_id=1, pipeline_id=pipeline_id, expected_components=3)
        broker = MagicMock()
        broker.publish = AsyncMock()

        with (
            patch(
                "app.services.pipeline_consumer._resolved_component_count",
                new_callable=AsyncMock,
                return_value=2,
            ),
            patch(
                "app.services.pipeline_consumer._expected_component_count",
                new_callable=AsyncMock,
                return_value=3,
            ),
            patch(
                "app.services.pipeline_consumer._start_verification",
                new_callable=AsyncMock,
            ) as start_verification,
        ):
            await _ensure_verification_if_gate_open(state, broker)

        start_verification.assert_not_awaited()

    async def test_starts_when_db_gate_open(self) -> None:
        pipeline_id = uuid4()
        state = PipelineState(project_id=1, pipeline_id=pipeline_id, expected_components=2)
        broker = MagicMock()

        with (
            patch(
                "app.services.pipeline_consumer._resolved_component_count",
                new_callable=AsyncMock,
                return_value=2,
            ),
            patch(
                "app.services.pipeline_consumer._expected_component_count",
                new_callable=AsyncMock,
                return_value=2,
            ),
            patch(
                "app.services.pipeline_consumer._start_verification",
                new_callable=AsyncMock,
            ) as start_verification,
        ):
            await _ensure_verification_if_gate_open(state, broker)

        start_verification.assert_awaited_once_with(state, broker)


class ParseResultsHandlerTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        pipeline_state.pipeline_states.clear()

    def tearDown(self) -> None:
        pipeline_state.pipeline_states.clear()

    async def test_wrong_event_acks(self) -> None:
        pipeline_id = uuid4()
        pipeline_state.init_state_from_thread(
            1,
            pipeline_id,
            MagicMock(content="hi", input_urls=None),
        )
        envelope = _envelope(event=PipelineEvent.BRIEF_READY, pipeline_id=pipeline_id)
        message = _message(envelope.model_dump(mode="json"))

        with patch(
            "app.services.pipeline_consumer.decode_envelope",
            return_value=envelope,
        ):
            await _handle_parse_results(message, MagicMock())

        message.ack.assert_awaited_once()
        message.nack.assert_not_awaited()


class BriefReadyHandlerTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        pipeline_state.pipeline_states.clear()

    def tearDown(self) -> None:
        pipeline_state.pipeline_states.clear()

    async def test_wrong_event_acks(self) -> None:
        pipeline_id = uuid4()
        pipeline_state.pipeline_states[pipeline_id] = PipelineState(
            project_id=1, pipeline_id=pipeline_id
        )
        envelope = _envelope(event=PipelineEvent.SCHEMA_READY, pipeline_id=pipeline_id)
        message = _message(envelope.model_dump(mode="json"))

        with patch(
            "app.services.pipeline_consumer.decode_envelope",
            return_value=envelope,
        ):
            await _handle_brief_ready(message, MagicMock())

        message.ack.assert_awaited_once()


class ComponentOutcomeHandlerTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        pipeline_state.pipeline_states.clear()

    def tearDown(self) -> None:
        pipeline_state.pipeline_states.clear()

    async def test_missing_component_id_nacks_poison(self) -> None:
        pipeline_id = uuid4()
        pipeline_state.pipeline_states[pipeline_id] = PipelineState(
            project_id=1, pipeline_id=pipeline_id
        )
        envelope = _envelope(
            event=PipelineEvent.COMPONENT_VALIDATED,
            pipeline_id=pipeline_id,
            component_id=None,
        )
        message = _message(envelope.model_dump(mode="json"))

        with patch(
            "app.services.pipeline_consumer.decode_envelope",
            return_value=envelope,
        ):
            await _handle_component_outcome(
                message,
                MagicMock(),
                expected_event=PipelineEvent.COMPONENT_VALIDATED,
                sse_type="component_validated",
            )

        message.nack.assert_awaited_once_with(requeue=False)
        message.ack.assert_not_awaited()

    async def test_duplicate_still_ensures_verification(self) -> None:
        pipeline_id = uuid4()
        state = PipelineState(
            project_id=1,
            pipeline_id=pipeline_id,
            expected_components=1,
            resolved_components=1,
        )
        pipeline_state.pipeline_states[pipeline_id] = state
        envelope = _envelope(
            event=PipelineEvent.COMPONENT_VALIDATED,
            pipeline_id=pipeline_id,
            component_id=99,
        )
        message = _message(envelope.model_dump(mode="json"))
        broker = MagicMock()

        with (
            patch(
                "app.services.pipeline_consumer.decode_envelope",
                return_value=envelope,
            ),
            patch(
                "app.services.pipeline_consumer.run_idempotent",
                new_callable=AsyncMock,
                return_value=(IdempotencyStatus.DUPLICATE, None),
            ),
            patch(
                "app.services.pipeline_consumer._ensure_verification_if_gate_open",
                new_callable=AsyncMock,
            ) as ensure_verification,
        ):
            await _handle_component_outcome(
                message,
                broker,
                expected_event=PipelineEvent.COMPONENT_VALIDATED,
                sse_type="component_validated",
            )

        ensure_verification.assert_awaited_once_with(state, broker)
        message.ack.assert_awaited_once()

    async def test_applied_with_open_gate_ensures_verification(self) -> None:
        pipeline_id = uuid4()
        state = PipelineState(
            project_id=1,
            pipeline_id=pipeline_id,
            expected_components=1,
            resolved_components=0,
        )
        pipeline_state.pipeline_states[pipeline_id] = state
        envelope = _envelope(
            event=PipelineEvent.COMPONENT_VALIDATED,
            pipeline_id=pipeline_id,
            component_id=99,
        )
        message = _message(envelope.model_dump(mode="json"))
        broker = MagicMock()

        with (
            patch(
                "app.services.pipeline_consumer.decode_envelope",
                return_value=envelope,
            ),
            patch(
                "app.services.pipeline_consumer.run_idempotent",
                new_callable=AsyncMock,
                return_value=(IdempotencyStatus.APPLIED, "Button"),
            ),
            patch(
                "app.services.pipeline_consumer._increment_resolved_and_check_gate",
                new_callable=AsyncMock,
                return_value=True,
            ),
            patch(
                "app.services.pipeline_consumer._ensure_verification_if_gate_open",
                new_callable=AsyncMock,
            ) as ensure_verification,
            patch("app.services.pipeline_consumer._emit_project_event"),
        ):
            await _handle_component_outcome(
                message,
                broker,
                expected_event=PipelineEvent.COMPONENT_VALIDATED,
                sse_type="component_validated",
            )

        ensure_verification.assert_awaited_once_with(state, broker)
        message.ack.assert_awaited_once()


class SchemaReadyHandlerTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        pipeline_state.pipeline_states.clear()

    def tearDown(self) -> None:
        pipeline_state.pipeline_states.clear()

    async def test_wrong_event_acks(self) -> None:
        pipeline_id = uuid4()
        pipeline_state.pipeline_states[pipeline_id] = PipelineState(
            project_id=1, pipeline_id=pipeline_id
        )
        envelope = _envelope(event=PipelineEvent.BRIEF_READY, pipeline_id=pipeline_id)
        message = _message(envelope.model_dump(mode="json"))

        with patch(
            "app.services.pipeline_consumer.decode_envelope",
            return_value=envelope,
        ):
            await _handle_schema_ready(message, MagicMock())

        message.ack.assert_awaited_once()


class ShowcaseReadyHandlerTests(unittest.IsolatedAsyncioTestCase):
    async def test_wrong_event_acks(self) -> None:
        envelope = _envelope(event=PipelineEvent.BRIEF_READY)
        message = _message(envelope.model_dump(mode="json"))

        with patch(
            "app.services.pipeline_consumer.decode_envelope",
            return_value=envelope,
        ):
            await _handle_showcase_ready(message, MagicMock())

        message.ack.assert_awaited_once()


class StartVerificationTests(unittest.IsolatedAsyncioTestCase):
    async def test_duplicate_claim_skips_publish(self) -> None:
        pipeline_id = uuid4()
        state = PipelineState(project_id=1, pipeline_id=pipeline_id)
        broker = MagicMock()
        broker.publish = AsyncMock()

        with patch(
            "app.services.pipeline_consumer.run_idempotent",
            new_callable=AsyncMock,
            return_value=(IdempotencyStatus.DUPLICATE, None),
        ):
            await _start_verification(state, broker)

        broker.publish.assert_not_awaited()

    async def test_applied_publishes_verification_start(self) -> None:
        pipeline_id = uuid4()
        state = PipelineState(project_id=1, pipeline_id=pipeline_id)
        broker = MagicMock()
        broker.publish = AsyncMock()

        with (
            patch(
                "app.services.pipeline_consumer.run_idempotent",
                new_callable=AsyncMock,
                return_value=(IdempotencyStatus.APPLIED, None),
            ),
            patch("app.services.pipeline_consumer._emit_project_event"),
        ):
            await _start_verification(state, broker)

        broker.publish.assert_awaited_once()
        queue_name, envelope = broker.publish.await_args.args
        self.assertEqual(queue_name, VERIFICATION_START)


if __name__ == "__main__":
    unittest.main()
