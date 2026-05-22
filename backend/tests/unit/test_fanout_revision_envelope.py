"""Unit tests for holism revision fan-out envelope builder."""

from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from app.services.pipeline_consumer import _fanout_revision_generates
from app.services.pipeline_state import PipelineState
from pandora_shared.enums import ComponentStatus
from pandora_shared.events import MessageEnvelope


class _Component:
    def __init__(self) -> None:
        self.id = 5
        self.spec_index = 0
        self.retry_count = 0
        self.revision_round = 0
        self.revision_instruction = "fix contrast"
        self.status = ComponentStatus.revised


class _Schema:
    design_tokens = {"primary": "#f97316"}
    global_config = {"theme": "light"}
    component_specs = [{"name": "Button", "type": "button"}]


class FanoutRevisionEnvelopeTests(unittest.IsolatedAsyncioTestCase):
    async def test_fanout_uses_shared_envelope_without_storybook_ad_hoc(self) -> None:
        pipeline_id = uuid4()
        state = PipelineState(project_id=10, pipeline_id=pipeline_id, revision_round=2)
        component = _Component()
        session = AsyncMock()
        result = MagicMock()
        result.scalars.return_value.all.return_value = [component]
        session.execute = AsyncMock(return_value=result)

        broker = MagicMock()
        broker.publish = AsyncMock()
        envelope = MessageEnvelope(
            event="pandora.verification.complete",
            project_id=10,
            pipeline_id=pipeline_id,
            payload={},
        )

        with (
            patch(
                "app.services.pipeline_consumer._latest_schema_for_project",
                new_callable=AsyncMock,
                return_value=_Schema(),
            ),
            patch(
                "app.services.pipeline_consumer.build_component_generate_envelope",
            ) as build_envelope,
        ):
            build_envelope.return_value = MessageEnvelope(
                event="pandora.component.generate",
                project_id=10,
                pipeline_id=pipeline_id,
                component_id=5,
                payload={},
            )
            await _fanout_revision_generates(session, envelope, state, broker)

        build_envelope.assert_called_once()
        self.assertEqual(build_envelope.call_args.kwargs.get("storybook_ad_hoc"), False)
        broker.publish.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
