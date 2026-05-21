"""Unit tests for Phase 6.1 ComponentGenAgent."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch
from uuid import uuid4

WORKERS_SRC = Path(__file__).resolve().parents[3] / "workers" / "src"
if str(WORKERS_SRC) not in sys.path:
    sys.path.insert(0, str(WORKERS_SRC))

from pandora_shared.events import Attempt, MessageEnvelope, PipelineEvent  # noqa: E402
from pandora_shared.payloads import ComponentGeneratedPayload  # noqa: E402
from pandora_workers.agents.component_gen import (  # noqa: E402
    ComponentGenAgent,
    _fallback_component,
    _merge_llm_component,
    _safe_component_name,
    _spec_type,
)


class ComponentGenHelperTests(unittest.TestCase):
    def test_safe_component_name(self) -> None:
        self.assertEqual(_safe_component_name("  Hero CTA  "), "HeroCTA")

    def test_fallback_includes_variants(self) -> None:
        out = _fallback_component(
            {"name": "Button", "type": "button", "variants": ["primary", "secondary"]},
            design_tokens={"primary": "#111"},
        )
        payload = ComponentGeneratedPayload.model_validate(out)
        self.assertIn("primary", payload.variants)
        self.assertIn("Button", payload.tsx_code)
        self.assertIn("<button", payload.tsx_code)

    def test_fallback_card_uses_article_not_button_root(self) -> None:
        out = _fallback_component(
            {"name": "Card", "type": "card", "variants": ["default"]},
            design_tokens={"primary": "#111"},
        )
        payload = ComponentGeneratedPayload.model_validate(out)
        self.assertIn("<article", payload.tsx_code)
        self.assertNotIn("<button", payload.tsx_code)

    def test_spec_type_from_name(self) -> None:
        self.assertEqual(_spec_type({"name": "PrimaryNav"}), "navigation")

    def test_merge_requires_tsx(self) -> None:
        merged = _merge_llm_component(
            {"tsx_code": "", "variants": ["default"]},
            spec={"name": "Card", "type": "card"},
            design_tokens=None,
            global_config=None,
        )
        self.assertIn("Card", merged["tsx_code"])
        self.assertIn("<article", merged["tsx_code"])


class ComponentGenAgentTests(unittest.IsolatedAsyncioTestCase):
    async def test_publishes_component_generated(self) -> None:
        agent = ComponentGenAgent()
        pipeline_id = uuid4()
        work = MessageEnvelope(
            event="pandora.component.generate",
            project_id=5,
            pipeline_id=pipeline_id,
            component_id=42,
            attempt=Attempt(retry_count=0, revision_round=0),
            payload={
                "spec": {"name": "Button", "type": "button", "variants": ["primary"]},
                "spec_index": 0,
                "design_tokens": {"primary": "#2563eb"},
                "global_config": {"theme": "light"},
            },
        )
        llm_out = {
            "tsx_code": "export function Button() { return <button>OK</button>; }",
            "css_code": ".btn { color: red; }",
            "props": {"label": "OK"},
            "variants": ["primary"],
        }
        with (
            patch(
                "pandora_workers.agents.component_gen.complete_json",
                new_callable=AsyncMock,
                return_value=llm_out,
            ),
            patch(
                "pandora_workers.agents.component_gen.render_prompt",
                side_effect=lambda name, **kwargs: name,
            ),
        ):
            result = await agent.handle_work(work)

        self.assertEqual(result.event, PipelineEvent.COMPONENT_GENERATED)
        self.assertEqual(result.component_id, 42)
        data = ComponentGeneratedPayload.model_validate(result.payload)
        self.assertIn("Button", data.tsx_code)

    async def test_llm_failure_uses_fallback(self) -> None:
        agent = ComponentGenAgent()
        work = MessageEnvelope(
            event="pandora.component.generate",
            project_id=1,
            pipeline_id=uuid4(),
            component_id=7,
            payload={"spec": {"name": "Card", "variants": ["default"]}},
        )
        with (
            patch(
                "pandora_workers.agents.component_gen.complete_json",
                new_callable=AsyncMock,
                side_effect=RuntimeError("down"),
            ),
            patch(
                "pandora_workers.agents.component_gen.render_prompt",
                side_effect=lambda name, **kwargs: name,
            ),
        ):
            result = await agent.handle_work(work)
        data = ComponentGeneratedPayload.model_validate(result.payload)
        self.assertIn("Card", data.tsx_code)
        self.assertIn("<article", data.tsx_code)

    async def test_missing_component_id_raises(self) -> None:
        agent = ComponentGenAgent()
        work = MessageEnvelope(
            event="pandora.component.generate",
            project_id=1,
            pipeline_id=uuid4(),
            payload={"spec": {"name": "X"}},
        )
        with self.assertRaises(ValueError):
            await agent.handle_work(work)


if __name__ == "__main__":
    unittest.main()
