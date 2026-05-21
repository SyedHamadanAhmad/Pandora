"""Unit tests for Phase 7.2 ShowcaseAgent."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch
from uuid import uuid4

WORKERS_SRC = Path(__file__).resolve().parents[3] / "workers" / "src"
SHARED = Path(__file__).resolve().parents[3] / "pandora_shared"
if str(WORKERS_SRC) not in sys.path:
    sys.path.insert(0, str(WORKERS_SRC))
if str(SHARED) not in sys.path:
    sys.path.insert(0, str(SHARED))

from pandora_shared.events import MessageEnvelope, PipelineEvent  # noqa: E402
from pandora_shared.payloads import ShowcaseReadyPayload  # noqa: E402
from pandora_shared.showcase_bundle import build_module_manifest  # noqa: E402
from pandora_workers.agents.showcase import (  # noqa: E402
    ShowcaseAgent,
    _fallback_showcase,
    _merge_showcase,
)


class ShowcaseMergeTests(unittest.TestCase):
    def test_fallback_uses_imports(self) -> None:
        work = {
            "components": [
                {
                    "name": "Button",
                    "variants": ["primary"],
                    "props": {"label": "Go"},
                }
            ],
            "module_manifest": build_module_manifest(
                [{"name": "Button", "variants": ["primary"], "props": {"label": "Go"}}]
            ),
        }
        out = _fallback_showcase(work)
        tsx = out["scenes"][0]["scene_tsx_code"]
        self.assertIn("from './Button'", tsx)
        self.assertIn("export default function Showcase", tsx)

    def test_merge_caps_scenes(self) -> None:
        manifest = build_module_manifest([{"name": "Button"}])
        work = {"components": [{"name": "Button"}], "module_manifest": manifest}
        llm = {
            "scenes": [
                {
                    "scene_index": i,
                    "scene_name": f"S{i}",
                    "scene_tsx_code": (
                        "import { Button } from './Button';\n"
                        "export default function Showcase() { return <Button label=\"x\" onClick={() => {}} />; }"
                    ),
                    "components_used": ["Button"],
                }
                for i in range(5)
            ]
        }
        merged = _merge_showcase(llm, work=work)
        self.assertEqual(len(merged["scenes"]), 3)
        self.assertEqual(merged["scenes"][0]["entry_path"], "/Showcase.tsx")

    def test_merge_replaces_bad_imports_with_fallback(self) -> None:
        manifest = build_module_manifest([{"name": "Button", "variants": ["primary"]}])
        work = {"components": [{"name": "Button"}], "module_manifest": manifest}
        llm = {
            "scenes": [
                {
                    "scene_index": 0,
                    "scene_name": "Bad",
                    "scene_tsx_code": (
                        "import { Card } from './Card';\n"
                        "export default function Showcase() { return <Card title=\"x\" />; }\n"
                    ),
                    "components_used": ["Button"],
                }
            ]
        }
        merged = _merge_showcase(llm, work=work)
        self.assertIn("from './Button'", merged["scenes"][0]["scene_tsx_code"])


class ShowcaseAgentTests(unittest.IsolatedAsyncioTestCase):
    async def test_publishes_showcase_ready(self) -> None:
        agent = ShowcaseAgent()
        components = [
            {
                "name": "Button",
                "tsx_code": "export function Button({ label }: { label: string }) { return <button>{label}</button>; }",
                "variants": ["primary"],
                "props": {"label": "OK"},
            }
        ]
        work = MessageEnvelope(
            event="pandora.showcase.generate",
            project_id=11,
            pipeline_id=uuid4(),
            payload={
                "components": components,
                "module_manifest": build_module_manifest(components),
            },
        )
        llm_out = {
            "scenes": [
                {
                    "scene_index": 0,
                    "scene_name": "Hero",
                    "scene_tsx_code": (
                        "import { Button } from './Button';\n"
                        "export default function Showcase() {\n"
                        '  return <div className="hero"><Button label="OK" variant="primary" onClick={() => {}} /></div>;\n'
                        "}"
                    ),
                    "scene_css_code": ".hero { padding: 24px; }",
                    "components_used": ["Button"],
                    "variant_selections": {"Button": "primary"},
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
        self.assertEqual(data.scenes[0].variant_selections, {"Button": "primary"})


if __name__ == "__main__":
    unittest.main()
