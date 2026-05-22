"""Unit tests for Phase 5.1 BriefAgent."""

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
from pandora_shared.payloads import BriefReadyPayload  # noqa: E402
from pandora_workers.agents.brief import (  # noqa: E402
    BriefAgent,
    _heuristic_defaults,
    _merge_brief_dict,
)


class BriefHeuristicTests(unittest.TestCase):
    def test_heuristic_url_colors_and_components(self) -> None:
        sources = {
            "url": {
                "source": "url",
                "data": {
                    "colors": ["#111", "#222", "#333"],
                    "fonts": ["Inter"],
                    "component_candidates": ["Hero", "Button", "Hero"],
                    "tone_hints": "bold",
                },
            }
        }
        h = _heuristic_defaults(sources)
        self.assertEqual(h["color_tokens"], {"primary": "#111", "secondary": "#222", "accent": "#333"})
        self.assertEqual(h["component_list"], ["Hero", "Button"])
        self.assertEqual(h["tone"], "bold")

    def test_merge_prefers_llm_then_heuristic(self) -> None:
        heuristic = {
            "color_tokens": {"primary": "#111"},
            "typography_scale": {"base": "16px"},
            "spacing_system": {"unit": 4},
            "design_flavour": "modern-saas",
            "tone": "professional",
            "component_list": ["Card"],
        }
        llm = {
            "color_tokens": {"primary": "#000000"},
            "typography_scale": None,
            "spacing_system": None,
            "design_flavour": "editorial",
            "tone": None,
            "component_list": ["Hero", "Hero", "Footer"],
        }
        merged = _merge_brief_dict(llm, input_gaps=["url:timeout"], heuristic=heuristic)
        payload = BriefReadyPayload.model_validate(merged)
        self.assertEqual(payload.input_gaps, ["url:timeout"])
        self.assertEqual(payload.color_tokens, {"primary": "#000000"})
        self.assertEqual(payload.typography_scale, {"base": "16px"})
        self.assertEqual(payload.component_list, ["Hero", "Footer"])


class BriefAgentTests(unittest.IsolatedAsyncioTestCase):
    async def test_publishes_brief_ready(self) -> None:
        agent = BriefAgent()
        pipeline_id = 42
        work = MessageEnvelope(
            event=PipelineEvent.BRIEF_REQUEST,
            project_id=7,
            pipeline_id=pipeline_id,
            payload={
                "sources": {
                    "text": {
                        "source": "text",
                        "data": {"summary": "A dashboard", "tone_hints": "playful"},
                    }
                },
                "input_gaps": [],
            },
        )
        llm_out = {
            "color_tokens": {"primary": "#2563eb"},
            "typography_scale": {"base": "16px", "heading": "20px"},
            "spacing_system": {"unit": 8},
            "design_flavour": "modern-saas",
            "tone": "professional",
            "component_list": ["Button", "Card"],
        }
        with patch(
            "pandora_workers.agents.brief.complete_json",
            new_callable=AsyncMock,
            return_value=llm_out,
        ):
            result = await agent.handle_work(work)

        self.assertEqual(result.event, PipelineEvent.BRIEF_READY)
        self.assertEqual(result.project_id, 7)
        self.assertEqual(result.pipeline_id, pipeline_id)
        data = BriefReadyPayload.model_validate(result.payload)
        self.assertEqual(data.component_list, ["Button", "Card"])
        self.assertEqual(data.input_gaps, [])
        self.assertEqual(data.design_flavour, "modern-saas")

    async def test_llm_failure_still_returns_valid_payload(self) -> None:
        agent = BriefAgent()
        work = MessageEnvelope(
            event=PipelineEvent.BRIEF_REQUEST,
            project_id=1,
            pipeline_id=1,
            payload={
                "sources": {
                    "url": {
                        "source": "url",
                        "data": {
                            "colors": ["#635bff"],
                            "component_candidates": ["Hero"],
                        },
                    }
                },
                "input_gaps": ["image:image_fetch_failed"],
            },
        )
        with patch(
            "pandora_workers.agents.brief.complete_json",
            new_callable=AsyncMock,
            side_effect=RuntimeError("api down"),
        ):
            result = await agent.handle_work(work)

        self.assertEqual(result.event, PipelineEvent.BRIEF_READY)
        data = BriefReadyPayload.model_validate(result.payload)
        self.assertEqual(data.input_gaps, ["image:image_fetch_failed"])
        self.assertEqual(data.color_tokens, {"primary": "#635bff"})
        self.assertEqual(data.component_list, ["Hero"])


if __name__ == "__main__":
    unittest.main()
