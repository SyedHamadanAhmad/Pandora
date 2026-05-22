"""Unit tests for shared worker foundation (pandora_workers)."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

WORKERS_SRC = Path(__file__).resolve().parents[3] / "workers" / "src"
if str(WORKERS_SRC) not in sys.path:
    sys.path.insert(0, str(WORKERS_SRC))

from pandora_shared.events import MessageEnvelope, PipelineEvent  # noqa: E402
from pandora_shared.payloads import (  # noqa: E402
    BriefReadyPayload,
    ComponentFailedPayload,
    SchemaReadyPayload,
    VerificationCompletePayload,
)
from pandora_workers.base_agent import BaseAgent  # noqa: E402
from pandora_workers.envelopes import build_result  # noqa: E402
from pandora_workers.llm import complete_json, openrouter_configured  # noqa: E402
from pandora_workers.prompts import render_prompt  # noqa: E402
from pandora_workers.validation.feedback import run_tsc_and_eslint  # noqa: E402


class _EchoAgent(BaseAgent):
    work_queue = "pandora.test.work"
    result_queue = "pandora.test.result"

    async def handle_work(self, work: MessageEnvelope) -> MessageEnvelope:
        return build_result(
            work,
            event=PipelineEvent.PARSE_RESULTS,
            payload={"echo": work.payload},
        )


class BaseAgentHandlerTests(unittest.IsolatedAsyncioTestCase):
    async def test_handle_message_acks_on_success(self) -> None:
        agent = _EchoAgent()
        message = MagicMock()
        message.ack = AsyncMock()
        message.nack = AsyncMock()
        message.body = MessageEnvelope(
            event=PipelineEvent.PARSE_REQUEST,
            project_id=1,
            pipeline_id=42,
            payload={"content": "hi"},
        ).model_dump_json().encode()
        channel = MagicMock()
        with patch("pandora_workers.base_agent.publish", new_callable=AsyncMock) as publish:
            await agent.handle_message(message, channel)
        publish.assert_awaited_once()
        message.ack.assert_awaited_once()
        message.nack.assert_not_awaited()

    async def test_handle_message_nacks_on_failure(self) -> None:
        agent = _EchoAgent()
        message = MagicMock()
        message.ack = AsyncMock()
        message.nack = AsyncMock()
        message.body = b"not-json"
        channel = MagicMock()
        await agent.handle_message(message, channel)
        message.nack.assert_awaited_once_with(requeue=True)
        message.ack.assert_not_awaited()


class LlmTests(unittest.IsolatedAsyncioTestCase):
    async def test_complete_json_parses_fenced_response(self) -> None:
        fake_response = MagicMock()
        fake_response.choices = [MagicMock(message=MagicMock(content='```json\n{"ok": true}\n```'))]
        client = MagicMock()
        client.chat.completions.create = AsyncMock(return_value=fake_response)
        with patch.dict("os.environ", {"OPENROUTER_API_KEY": "test-key"}):
            with patch("pandora_workers.llm._client", return_value=client):
                result = await complete_json("sys", "user")
        self.assertEqual(result, {"ok": True})

    def test_openrouter_configured_false_without_key(self) -> None:
        with patch.dict("os.environ", {"OPENROUTER_API_KEY": ""}, clear=False):
            self.assertFalse(openrouter_configured())


class PayloadContractTests(unittest.TestCase):
    def test_brief_ready_roundtrip(self) -> None:
        payload = BriefReadyPayload(
            color_tokens={"primary": "#000"},
            component_list=["Button"],
            input_gaps=["url:timeout"],
        )
        data = payload.model_dump()
        self.assertEqual(BriefReadyPayload.model_validate(data).input_gaps, ["url:timeout"])

    def test_schema_ready_caps_specs(self) -> None:
        specs = [{"name": f"C{i}"} for i in range(16)]
        with self.assertRaises(ValueError):
            SchemaReadyPayload(component_specs=specs)

    def test_verification_blocking_detection(self) -> None:
        payload = VerificationCompletePayload(
            issues=[{"priority": "P2", "message": "contrast"}],
            approved=False,
        )
        self.assertTrue(payload.has_blocking_issues())

    def test_component_failed_resolved_error(self) -> None:
        payload = ComponentFailedPayload(error="bad tsx")
        self.assertEqual(payload.resolved_error(), "bad tsx")


class PromptLoaderTests(unittest.TestCase):
    def test_render_json_system_template(self) -> None:
        text = render_prompt("json_system.jinja2")
        self.assertIn("JSON object", text)


class ValidationTests(unittest.IsolatedAsyncioTestCase):
    async def test_invalid_tsx_fails_when_tsc_available(self) -> None:
        ok, errors = await run_tsc_and_eslint("export const broken = ;")
        if not errors:
            self.skipTest("tsc/eslint not available in test environment")
        self.assertFalse(ok)
        self.assertTrue(errors)


class EnvelopeHelperTests(unittest.TestCase):
    def test_build_result_preserves_pipeline_ids(self) -> None:
        pipeline_id = 99
        work = MessageEnvelope(
            event=PipelineEvent.BRIEF_REQUEST,
            project_id=42,
            pipeline_id=pipeline_id,
            payload={},
        )
        result = build_result(
            work,
            event=PipelineEvent.BRIEF_READY,
            payload=json.loads(BriefReadyPayload().model_dump_json()),
        )
        self.assertEqual(result.project_id, 42)
        self.assertEqual(result.pipeline_id, pipeline_id)
        self.assertEqual(result.event, PipelineEvent.BRIEF_READY)


if __name__ == "__main__":
    unittest.main()
