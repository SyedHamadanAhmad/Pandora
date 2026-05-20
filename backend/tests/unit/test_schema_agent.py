"""Unit tests for Phase 5.2 SchemaAgent."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch
from uuid import uuid4

WORKERS_SRC = Path(__file__).resolve().parents[3] / "workers" / "src"
if str(WORKERS_SRC) not in sys.path:
    sys.path.insert(0, str(WORKERS_SRC))

from pandora_shared.events import MessageEnvelope, PipelineEvent  # noqa: E402
from pandora_shared.payloads import SchemaReadyPayload  # noqa: E402
from pandora_workers.agents.schema import (  # noqa: E402
    SchemaAgent,
    _fallback_schema,
    _merge_llm_schema,
    _normalize_spec,
)


class SchemaNormalizeTests(unittest.TestCase):
    def test_normalize_spec_strips(self) -> None:
        s = _normalize_spec({"name": "  Hero  ", "type": "layout", "variants": ["a", "a", "b"], "layout": "full"})
        self.assertEqual(s["name"], "Hero")
        self.assertEqual(s["variants"], ["a", "b"])


class SchemaFallbackTests(unittest.TestCase):
    def test_fallback_from_component_list(self) -> None:
        work = {
            "color_tokens": {"primary": "#111"},
            "design_flavour": "playful",
            "component_list": ["Button", "Card"],
        }
        out = _fallback_schema(work)
        payload = SchemaReadyPayload.model_validate(out)
        self.assertEqual(len(payload.component_specs), 2)
        self.assertEqual(payload.component_specs[0]["name"], "Button")

    def test_merge_caps_specs(self) -> None:
        work = {"component_list": ["A"], "color_tokens": {"primary": "#000"}}
        llm = {
            "design_tokens": {"primary": "#fff"},
            "global_config": {"theme": "dark"},
            "component_specs": [{"name": f"C{i}", "type": "layout", "variants": ["default"]} for i in range(20)],
        }
        merged = _merge_llm_schema(llm, work=work)
        self.assertEqual(len(merged["component_specs"]), 15)


class SchemaAgentTests(unittest.IsolatedAsyncioTestCase):
    async def test_publishes_schema_ready(self) -> None:
        agent = SchemaAgent()
        pipeline_id = uuid4()
        work = MessageEnvelope(
            event=PipelineEvent.SCHEMA_REQUEST,
            project_id=3,
            pipeline_id=pipeline_id,
            payload={
                "color_tokens": {"primary": "#2563eb"},
                "design_flavour": "modern-saas",
                "component_list": ["Button", "Card"],
                "input_gaps": [],
            },
        )
        llm_out = {
            "design_tokens": {"primary": "#2563eb", "radius": "8px"},
            "global_config": {"theme": "light", "design_flavour": "modern-saas"},
            "component_specs": [
                {"name": "Button", "type": "button", "variants": ["primary"], "layout": None},
                {"name": "Card", "type": "card", "variants": ["default"], "layout": "vertical"},
            ],
        }
        with patch(
            "pandora_workers.agents.schema.complete_json",
            new_callable=AsyncMock,
            return_value=llm_out,
        ):
            result = await agent.handle_work(work)

        self.assertEqual(result.event, PipelineEvent.SCHEMA_READY)
        data = SchemaReadyPayload.model_validate(result.payload)
        self.assertEqual(len(data.component_specs), 2)
        self.assertEqual(data.component_specs[0]["name"], "Button")

    async def test_llm_failure_uses_fallback(self) -> None:
        agent = SchemaAgent()
        work = MessageEnvelope(
            event=PipelineEvent.SCHEMA_REQUEST,
            project_id=1,
            pipeline_id=uuid4(),
            payload={
                "color_tokens": {"primary": "#111"},
                "component_list": ["Hero"],
            },
        )
        with patch(
            "pandora_workers.agents.schema.complete_json",
            new_callable=AsyncMock,
            side_effect=RuntimeError("down"),
        ):
            result = await agent.handle_work(work)
        data = SchemaReadyPayload.model_validate(result.payload)
        self.assertTrue(any(s.get("name") == "Hero" for s in data.component_specs))


if __name__ == "__main__":
    unittest.main()
