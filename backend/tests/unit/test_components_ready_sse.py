"""Unit tests for W-B09 ``components_ready`` SSE emission."""

import json
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services import pipeline_state
from app.services.idempotency import IdempotencyStatus
from app.services.pipeline_consumer import (
    _finalize_pipeline_run,
    _handle_component_outcome,
    _maybe_emit_components_ready,
)
from app.services.pipeline_state import PipelineState, register_storybook_batch
from pandora_shared.events import MessageEnvelope, PipelineEvent
from pandora_shared.sse_events import COMPONENTS_READY

_PIPELINE_RUN_ID = 1001


def _message(body: dict) -> MagicMock:
    message = MagicMock()
    message.body = json.dumps(body).encode()
    message.ack = AsyncMock()
    message.nack = AsyncMock()
    return message


def _envelope(
    *,
    event: str,
    pipeline_id: int | None = None,
    project_id: int = 1,
    component_id: int | None = None,
) -> MessageEnvelope:
    return MessageEnvelope(
        event=event,
        project_id=project_id,
        pipeline_id=pipeline_id if pipeline_id is not None else _PIPELINE_RUN_ID,
        component_id=component_id,
        payload={},
    )


class MaybeEmitComponentsReadyTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        pipeline_state.pipeline_states.clear()

    def tearDown(self) -> None:
        pipeline_state.pipeline_states.clear()

    async def test_emits_when_db_gate_open(self) -> None:
        state = PipelineState(project_id=1, pipeline_id=_PIPELINE_RUN_ID, expected_components=2)
        pipeline_state.pipeline_states[_PIPELINE_RUN_ID] = state

        with (
            patch(
                "app.services.pipeline_consumer._components_ready_gate_open",
                new_callable=AsyncMock,
                return_value=(True, 2),
            ),
            patch("app.services.pipeline_consumer._emit_project_event") as emit,
        ):
            await _maybe_emit_components_ready(state, source="pipeline")

        emit.assert_called_once()
        event = emit.call_args[0][1]
        self.assertEqual(event["type"], COMPONENTS_READY)
        self.assertEqual(event["componentCount"], 2)
        self.assertEqual(event["source"], "pipeline")
        self.assertEqual(state.components_ready_at_revision, 0)

    async def test_skips_duplicate_revision_emit(self) -> None:
        state = PipelineState(
            project_id=1,
            pipeline_id=_PIPELINE_RUN_ID,
            expected_components=2,
            components_ready_at_revision=0,
        )
        pipeline_state.pipeline_states[_PIPELINE_RUN_ID] = state

        with (
            patch(
                "app.services.pipeline_consumer._components_ready_gate_open",
                new_callable=AsyncMock,
                return_value=(True, 2),
            ),
            patch("app.services.pipeline_consumer._emit_project_event") as emit,
        ):
            await _maybe_emit_components_ready(state, source="pipeline")

        emit.assert_not_called()

    async def test_storybook_regen_emits_without_db_gate(self) -> None:
        state = PipelineState(
            project_id=1,
            pipeline_id=_PIPELINE_RUN_ID,
            run_complete=True,
            storybook_batch_expected=3,
        )
        pipeline_state.pipeline_states[_PIPELINE_RUN_ID] = state

        with patch("app.services.pipeline_consumer._emit_project_event") as emit:
            await _maybe_emit_components_ready(state, source="storybook_regen")

        emit.assert_called_once()
        self.assertEqual(emit.call_args[0][1]["source"], "storybook_regen")
        self.assertEqual(emit.call_args[0][1]["componentCount"], 3)


class ComponentOutcomeComponentsReadyTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        pipeline_state.pipeline_states.clear()

    def tearDown(self) -> None:
        pipeline_state.pipeline_states.clear()

    async def test_gate_open_emits_components_ready(self) -> None:
        state = PipelineState(
            project_id=1,
            pipeline_id=_PIPELINE_RUN_ID,
            expected_components=1,
            resolved_components=0,
        )
        pipeline_state.pipeline_states[_PIPELINE_RUN_ID] = state
        envelope = _envelope(
            event=PipelineEvent.COMPONENT_VALIDATED,
            component_id=10,
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
                return_value=True,
            ),
            patch(
                "app.services.pipeline_consumer._maybe_emit_components_ready",
                new_callable=AsyncMock,
            ) as emit_ready,
            patch(
                "app.services.pipeline_consumer._ensure_verification_if_gate_open",
                new_callable=AsyncMock,
            ),
            patch("app.services.pipeline_consumer._emit_project_event"),
        ):
            await _handle_component_outcome(
                message,
                MagicMock(),
                expected_event=PipelineEvent.COMPONENT_VALIDATED,
                sse_type="component_validated",
            )

        emit_ready.assert_awaited_once_with(state, source="pipeline")
        message.ack.assert_awaited_once()

    async def test_storybook_batch_complete_emits_components_ready(self) -> None:
        state = PipelineState(
            project_id=1,
            pipeline_id=_PIPELINE_RUN_ID,
            run_complete=True,
            storybook_batch_expected=2,
            storybook_batch_resolved=1,
        )
        pipeline_state.pipeline_states[_PIPELINE_RUN_ID] = state
        envelope = _envelope(
            event=PipelineEvent.COMPONENT_VALIDATED,
            component_id=5,
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
                return_value=(IdempotencyStatus.APPLIED, "Card"),
            ),
            patch(
                "app.services.pipeline_consumer._maybe_emit_components_ready",
                new_callable=AsyncMock,
            ) as emit_ready,
            patch(
                "app.services.pipeline_consumer._clear_storybook_batch",
                new_callable=AsyncMock,
            ) as clear_batch,
            patch("app.services.pipeline_consumer._emit_project_event"),
        ):
            await _handle_component_outcome(
                message,
                MagicMock(),
                expected_event=PipelineEvent.COMPONENT_VALIDATED,
                sse_type="component_validated",
            )

        emit_ready.assert_awaited_once_with(state, source="storybook_regen")
        clear_batch.assert_awaited_once_with(state)
        message.ack.assert_awaited_once()


class FinalizePipelineRunTests(unittest.IsolatedAsyncioTestCase):
    async def test_finalize_emits_components_ready_fallback(self) -> None:
        state = PipelineState(project_id=1, pipeline_id=_PIPELINE_RUN_ID)

        with (
            patch(
                "app.services.pipeline_consumer.persist_state",
                new_callable=AsyncMock,
            ),
            patch(
                "app.services.pipeline_consumer._maybe_emit_components_ready",
                new_callable=AsyncMock,
            ) as emit_ready,
            patch("app.services.pipeline_consumer._emit_project_event"),
        ):
            await _finalize_pipeline_run(state, project_id=1, pipeline_run_id=_PIPELINE_RUN_ID)

        emit_ready.assert_awaited_once()
        self.assertEqual(
            emit_ready.call_args.kwargs,
            {"source": "pipeline_complete", "skip_revision_dedupe": True},
        )
        self.assertTrue(state.run_complete)


class RegisterStorybookBatchTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        pipeline_state.pipeline_states.clear()

    def tearDown(self) -> None:
        pipeline_state.pipeline_states.clear()

    async def test_registers_batch_on_completed_run(self) -> None:
        state = PipelineState(
            project_id=1,
            pipeline_id=_PIPELINE_RUN_ID,
            run_complete=True,
        )
        pipeline_state.pipeline_states[_PIPELINE_RUN_ID] = state

        with (
            patch(
                "app.services.pipeline_state.async_session",
            ) as session_cm,
            patch(
                "app.services.pipeline_state.get_state",
                new_callable=AsyncMock,
                return_value=state,
            ),
            patch(
                "app.services.pipeline_state.persist_state",
                new_callable=AsyncMock,
            ),
        ):
            db = MagicMock()
            db.commit = AsyncMock()
            session_cm.return_value.__aenter__ = AsyncMock(return_value=db)
            session_cm.return_value.__aexit__ = AsyncMock(return_value=None)

            await register_storybook_batch(_PIPELINE_RUN_ID, 4)

        self.assertEqual(state.storybook_batch_expected, 4)
        self.assertEqual(state.storybook_batch_resolved, 0)
