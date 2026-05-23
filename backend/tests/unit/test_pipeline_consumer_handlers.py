"""Unit tests for pipeline consumer queue handlers."""

import json
import unittest
from unittest.mock import AsyncMock, MagicMock, patch
from app.services import pipeline_state

_PIPELINE_RUN_ID = 1001
from app.services.idempotency import IdempotencyStatus
from app.services.pipeline_consumer import (
    _ensure_verification_if_gate_open,
    _handle_brief_ready,
    _handle_component_outcome,
    _handle_parse_results,
    _handle_schema_ready,
    _handle_verification_complete,
    _start_verification,
)
from app.services.pipeline_state import PipelineState
from pandora_shared.events import MessageEnvelope, PipelineEvent


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
        pipeline_id=pipeline_id if pipeline_id is not None else _PIPELINE_RUN_ID,
        component_id=component_id,
        payload=payload or {},
    )


class EnsureVerificationGateTests(unittest.IsolatedAsyncioTestCase):
    async def test_skips_when_db_resolved_below_expected(self) -> None:
        pipeline_id = _PIPELINE_RUN_ID
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
            await _ensure_verification_if_gate_open(state)

        start_verification.assert_not_awaited()

    async def test_starts_when_db_gate_open(self) -> None:
        pipeline_id = _PIPELINE_RUN_ID
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
            await _ensure_verification_if_gate_open(state)

        start_verification.assert_awaited_once_with(state)


class ParseResultsHandlerTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        pipeline_state.pipeline_states.clear()

    def tearDown(self) -> None:
        pipeline_state.pipeline_states.clear()

    async def test_wrong_event_acks(self) -> None:
        pipeline_id = _PIPELINE_RUN_ID
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
        pipeline_id = _PIPELINE_RUN_ID
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
        pipeline_id = _PIPELINE_RUN_ID
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
        pipeline_id = _PIPELINE_RUN_ID
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
        pipeline_id = _PIPELINE_RUN_ID
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

    async def test_run_complete_skips_holism_gate(self) -> None:
        """Pipeline state kept after holism completes; storybook regen must not re-run verification."""
        pipeline_id = _PIPELINE_RUN_ID
        state = PipelineState(
            project_id=1,
            pipeline_id=pipeline_id,
            expected_components=3,
            resolved_components=3,
            run_complete=True,
        )
        pipeline_state.pipeline_states[pipeline_id] = state
        envelope = _envelope(
            event=PipelineEvent.COMPONENT_VALIDATED,
            pipeline_id=pipeline_id,
            component_id=1,
        )
        message = _message(envelope.model_dump(mode="json"))

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
            ) as increment_gate,
            patch(
                "app.services.pipeline_consumer._ensure_verification_if_gate_open",
                new_callable=AsyncMock,
            ) as ensure_verification,
            patch("app.services.pipeline_consumer._emit_project_event"),
        ):
            await _handle_component_outcome(
                message,
                MagicMock(),
                expected_event=PipelineEvent.COMPONENT_VALIDATED,
                sse_type="component_validated",
            )

        increment_gate.assert_not_awaited()
        ensure_verification.assert_not_awaited()
        message.ack.assert_awaited_once()

    async def test_ad_hoc_outcome_without_pipeline_state_emits_sse_and_acks(self) -> None:
        """State lost after API restart: still persist + SSE without holism gate."""
        pipeline_id = _PIPELINE_RUN_ID
        envelope = _envelope(
            event=PipelineEvent.COMPONENT_VALIDATED,
            pipeline_id=pipeline_id,
            component_id=42,
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
                return_value=(IdempotencyStatus.APPLIED, "Card"),
            ),
            patch(
                "app.services.pipeline_consumer._increment_resolved_and_check_gate",
                new_callable=AsyncMock,
            ) as increment_gate,
            patch(
                "app.services.pipeline_consumer._ensure_verification_if_gate_open",
                new_callable=AsyncMock,
            ) as ensure_verification,
            patch(
                "app.services.pipeline_consumer._emit_project_event",
            ) as emit_event,
        ):
            await _handle_component_outcome(
                message,
                broker,
                expected_event=PipelineEvent.COMPONENT_VALIDATED,
                sse_type="component_validated",
            )

        increment_gate.assert_not_awaited()
        ensure_verification.assert_not_awaited()
        emit_event.assert_called_once()
        self.assertEqual(emit_event.call_args[0][1]["type"], "component_validated")
        self.assertEqual(emit_event.call_args[0][1]["componentName"], "Card")
        message.ack.assert_awaited_once()
        message.nack.assert_not_awaited()

    async def test_ad_hoc_duplicate_acks_without_verification_or_sse(self) -> None:
        pipeline_id = _PIPELINE_RUN_ID
        envelope = _envelope(
            event=PipelineEvent.COMPONENT_FAILED,
            pipeline_id=pipeline_id,
            component_id=7,
        )
        message = _message(envelope.model_dump(mode="json"))

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
            patch(
                "app.services.pipeline_consumer._emit_project_event",
            ) as emit_event,
        ):
            await _handle_component_outcome(
                message,
                MagicMock(),
                expected_event=PipelineEvent.COMPONENT_FAILED,
                sse_type="component_failed",
            )

        ensure_verification.assert_not_awaited()
        emit_event.assert_not_called()
        message.ack.assert_awaited_once()


class SchemaReadyHandlerTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        pipeline_state.pipeline_states.clear()

    def tearDown(self) -> None:
        pipeline_state.pipeline_states.clear()

    async def test_wrong_event_acks(self) -> None:
        pipeline_id = _PIPELINE_RUN_ID
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


class VerificationCompleteHandlerTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        pipeline_state.pipeline_states.clear()

    def tearDown(self) -> None:
        pipeline_state.pipeline_states.clear()

    async def test_pass_finalizes_without_showcase(self) -> None:
        pipeline_id = _PIPELINE_RUN_ID
        state = PipelineState(project_id=1, pipeline_id=pipeline_id, revision_round=0)
        pipeline_state.pipeline_states[pipeline_id] = state
        envelope = _envelope(
            event=PipelineEvent.VERIFICATION_COMPLETE,
            pipeline_id=pipeline_id,
            payload={"issues": [], "approved": True},
        )
        message = _message(envelope.model_dump(mode="json"))
        broker = MagicMock()
        broker.publish = AsyncMock()

        with (
            patch(
                "app.services.pipeline_consumer.decode_envelope",
                return_value=envelope,
            ),
            patch(
                "app.services.pipeline_consumer.run_idempotent",
                new_callable=AsyncMock,
                return_value=(IdempotencyStatus.APPLIED, None),
            ),
            patch(
                "app.services.pipeline_consumer._finalize_pipeline_run",
                new_callable=AsyncMock,
            ) as finalize,
        ):
            await _handle_verification_complete(message, broker)

        broker.publish.assert_not_awaited()
        finalize.assert_awaited_once_with(state, envelope.project_id, pipeline_id)
        message.ack.assert_awaited_once()

    async def test_pass_duplicate_sets_run_complete(self) -> None:
        pipeline_id = _PIPELINE_RUN_ID
        state = PipelineState(project_id=1, pipeline_id=pipeline_id)
        pipeline_state.pipeline_states[pipeline_id] = state
        envelope = _envelope(
            event=PipelineEvent.VERIFICATION_COMPLETE,
            pipeline_id=pipeline_id,
            payload={"issues": []},
        )
        message = _message(envelope.model_dump(mode="json"))

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
                "app.services.pipeline_consumer._finalize_pipeline_run",
                new_callable=AsyncMock,
            ) as finalize,
            patch(
                "app.services.pipeline_consumer.persist_state",
                new_callable=AsyncMock,
            ),
        ):
            await _handle_verification_complete(message, MagicMock())

        self.assertTrue(state.run_complete)
        finalize.assert_not_awaited()
        message.ack.assert_awaited_once()


class StartVerificationTests(unittest.IsolatedAsyncioTestCase):
    async def test_duplicate_claim_skips_emit(self) -> None:
        pipeline_id = _PIPELINE_RUN_ID
        state = PipelineState(project_id=1, pipeline_id=pipeline_id)

        with (
            patch(
                "app.services.pipeline_consumer.run_idempotent",
                new_callable=AsyncMock,
                return_value=(IdempotencyStatus.DUPLICATE, None),
            ),
            patch("app.services.pipeline_consumer._emit_project_event") as emit_event,
        ):
            await _start_verification(state)

        emit_event.assert_not_called()

    async def test_applied_emits_verification_running(self) -> None:
        pipeline_id = _PIPELINE_RUN_ID
        state = PipelineState(project_id=1, pipeline_id=pipeline_id)

        with (
            patch(
                "app.services.pipeline_consumer.run_idempotent",
                new_callable=AsyncMock,
                return_value=(IdempotencyStatus.APPLIED, None),
            ),
            patch("app.services.pipeline_consumer._emit_project_event") as emit_event,
        ):
            await _start_verification(state)

        emit_event.assert_called_once()
        self.assertEqual(emit_event.call_args[0][1]["type"], "verification_running")


if __name__ == "__main__":
    unittest.main()
