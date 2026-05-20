"""Unit tests for Phase 6.2 FeedbackAgent."""

from __future__ import annotations

import shutil
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

WORKERS_SRC = Path(__file__).resolve().parents[3] / "workers" / "src"
if str(WORKERS_SRC) not in sys.path:
    sys.path.insert(0, str(WORKERS_SRC))

from pandora_shared.events import MessageEnvelope, PipelineEvent  # noqa: E402
from pandora_shared.payloads import ComponentFailedPayload, ComponentValidatedPayload  # noqa: E402
from pandora_workers.agents.feedback import FeedbackAgent  # noqa: E402
from pandora_workers.validation.feedback import run_tsc_and_eslint  # noqa: E402
from pandora_shared.queues import COMPONENT_FAILED, COMPONENT_VALIDATED  # noqa: E402


class FeedbackValidationTests(unittest.IsolatedAsyncioTestCase):
    async def test_typical_button_tsx_passes_when_tools_available(self) -> None:
        tsx = """
import type { ReactNode } from 'react';

export type ButtonProps = {
  label?: string;
  children?: ReactNode;
  className?: string;
};

export function Button({ label = 'Click', children, className }: ButtonProps) {
  return (
    <button type="button" className={className ?? 'pandora-button'}>
      {children ?? label}
    </button>
  );
}
"""
        ok, errors = await run_tsc_and_eslint(tsx)
        if not shutil.which("npx"):
            self.skipTest("npx not available")
        self.assertTrue(ok, errors)


class FeedbackAgentTests(unittest.IsolatedAsyncioTestCase):
    async def test_valid_code_publishes_validated(self) -> None:
        agent = FeedbackAgent()
        work = MessageEnvelope(
            event=PipelineEvent.COMPONENT_GENERATED,
            project_id=2,
            pipeline_id=uuid4(),
            component_id=99,
            payload={
                "tsx_code": "export function X() { return <span>ok</span>; }",
                "css_code": ".x { color: red; }",
                "props": {},
                "variants": ["default"],
            },
        )
        with patch(
            "pandora_workers.agents.feedback.run_tsc_and_eslint",
            new_callable=AsyncMock,
            return_value=(True, []),
        ):
            result = await agent.handle_work(work)

        self.assertEqual(result.event, PipelineEvent.COMPONENT_VALIDATED)
        ComponentValidatedPayload.model_validate(result.payload)

    async def test_invalid_code_publishes_failed(self) -> None:
        agent = FeedbackAgent()
        work = MessageEnvelope(
            event=PipelineEvent.COMPONENT_GENERATED,
            project_id=2,
            pipeline_id=uuid4(),
            component_id=100,
            payload={
                "tsx_code": "export const broken = ;",
                "css_code": None,
                "variants": ["default"],
            },
        )
        with patch(
            "pandora_workers.agents.feedback.run_tsc_and_eslint",
            new_callable=AsyncMock,
            return_value=(False, ["syntax error"]),
        ):
            result = await agent.handle_work(work)

        self.assertEqual(result.event, PipelineEvent.COMPONENT_FAILED)
        failed = ComponentFailedPayload.model_validate(result.payload)
        self.assertIn("syntax", failed.resolved_error())

    async def test_handle_message_routes_to_failed_queue(self) -> None:
        agent = FeedbackAgent()
        message = MagicMock()
        message.ack = AsyncMock()
        message.nack = AsyncMock()
        message.body = MessageEnvelope(
            event=PipelineEvent.COMPONENT_GENERATED,
            project_id=1,
            pipeline_id=uuid4(),
            component_id=1,
            payload={
                "tsx_code": "bad",
                "variants": ["default"],
            },
        ).model_dump_json().encode()
        channel = MagicMock()
        with patch(
            "pandora_workers.agents.feedback.run_tsc_and_eslint",
            new_callable=AsyncMock,
            return_value=(False, ["err"]),
        ):
            with patch(
                "pandora_workers.agents.feedback.publish",
                new_callable=AsyncMock,
            ) as publish:
                await agent.handle_message(message, channel)

        publish.assert_awaited_once()
        self.assertEqual(publish.await_args[0][1], COMPONENT_FAILED)
        message.ack.assert_awaited_once()

    async def test_handle_message_routes_to_validated_queue(self) -> None:
        agent = FeedbackAgent()
        message = MagicMock()
        message.ack = AsyncMock()
        message.nack = AsyncMock()
        message.body = MessageEnvelope(
            event=PipelineEvent.COMPONENT_GENERATED,
            project_id=1,
            pipeline_id=uuid4(),
            component_id=2,
            payload={
                "tsx_code": "export function Ok() { return null; }",
                "variants": ["default"],
            },
        ).model_dump_json().encode()
        channel = MagicMock()
        with patch(
            "pandora_workers.agents.feedback.run_tsc_and_eslint",
            new_callable=AsyncMock,
            return_value=(True, []),
        ):
            with patch(
                "pandora_workers.agents.feedback.publish",
                new_callable=AsyncMock,
            ) as publish:
                await agent.handle_message(message, channel)

        self.assertEqual(publish.await_args[0][1], COMPONENT_VALIDATED)


if __name__ == "__main__":
    unittest.main()
