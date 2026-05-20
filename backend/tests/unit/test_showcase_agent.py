"""Unit tests for Phase 7.2 ShowcaseAgent."""

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
from pandora_shared.payloads import ShowcaseReadyPayload  # noqa: E402
from pandora_workers.agents.showcase import (  # noqa: E402
    ShowcaseAgent,
    _fallback_showcase,
    _merge_showcase,
)


class ShowcaseMergeTests(unittest.TestCase):
    def test_fallback_uses_component_names(self) -> None:
        work = {"components": [{"name": "Button"}, {"name": "Card"}]}
        out = _fallback_showcase(work)
        self.assertIn("Button", out["scenes"][0]["components_used"])

    def test_merge_caps_scenes(self) -> None:
        work = {"components": []}
        llm = {
            "scenes": [
                {"scene_index": i, "scene_name": f"S{i}", "scene_tsx_code": "<div />"}
                for i in range(5)
            ]
        }
        merged = _merge_showcase(llm, work=work)
        self.assertEqual(len(merged["scenes"]), 3)


class ShowcaseAgentTests(unittest.IsolatedAsyncioTestCase):
    async def test_publishes_showcase_ready(self) -> None:
        agent = ShowcaseAgent()
        work = MessageEnvelope(
            event="pandora.showcase.generate",
            project_id=11,
            pipeline_id=uuid4(),
            payload={
                "components": [
                    {
                        "name": "Button",
                        "tsx_code": "export function Button() { return <button />; }",
                    }
                ],
            },
        )
        llm_out = {
            "scenes": [
                {
                    "scene_index": 0,
                    "scene_name": "Hero",
                    "scene_tsx_code": "<div className='hero' />",
                    "scene_css_code": ".hero {}",
                    "components_used": ["Button"],
                }
            ]
        }
        with patch(
            "pandora_workers.agents.showcase.complete_json",
            new_callable=AsyncMock,
            return_value=llm_out,
        ):
            result = await agent.handle_work(work)

        self.assertEqual(result.event, PipelineEvent.SHOWCASE_READY)
        data = ShowcaseReadyPayload.model_validate(result.payload)
        self.assertEqual(len(data.scenes), 1)


if __name__ == "__main__":
    unittest.main()
