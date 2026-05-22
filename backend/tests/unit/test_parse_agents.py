"""Unit tests for Phase 4 parse agents."""

from __future__ import annotations

import io
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch
from uuid import uuid4

WORKERS_SRC = Path(__file__).resolve().parents[3] / "workers" / "src"
if str(WORKERS_SRC) not in sys.path:
    sys.path.insert(0, str(WORKERS_SRC))

from PIL import Image  # noqa: E402

from pandora_shared.events import MessageEnvelope, PipelineEvent  # noqa: E402
from pandora_workers.agents.parse_image import ParseImageAgent  # noqa: E402
from pandora_workers.agents.parse_text import ParseTextAgent  # noqa: E402
from pandora_workers.agents.parse_url import ParseUrlAgent  # noqa: E402
from pandora_workers.image_analysis import analyze_image_bytes  # noqa: E402
from pandora_workers.url_crawler import CrawlPageResult  # noqa: E402


def _make_tiny_png() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (8, 8), color=(37, 99, 235)).save(buf, format="PNG")
    return buf.getvalue()


_TINY_PNG = _make_tiny_png()


class ParseTextAgentTests(unittest.IsolatedAsyncioTestCase):
    async def test_publishes_structured_data(self) -> None:
        agent = ParseTextAgent()
        work = MessageEnvelope(
            event=PipelineEvent.PARSE_REQUEST,
            project_id=1,
            pipeline_id=1,
            payload={"content": "Build a fintech dashboard"},
        )
        with patch(
            "pandora_workers.agents.parse_text.complete_json",
            new_callable=AsyncMock,
            return_value={
                "summary": "Fintech dashboard",
                "keywords": ["fintech", "dashboard"],
                "tone_hints": "professional",
                "requirements": [],
            },
        ):
            result = await agent.handle_work(work)
        self.assertEqual(result.event, PipelineEvent.PARSE_RESULTS)
        self.assertEqual(result.payload["source"], "text")
        self.assertIn("summary", result.payload["data"])


class ParseUrlAgentTests(unittest.IsolatedAsyncioTestCase):
    async def test_combines_crawl_and_llm(self) -> None:
        agent = ParseUrlAgent()
        work = MessageEnvelope(
            event=PipelineEvent.PARSE_REQUEST,
            project_id=2,
            pipeline_id=1,
            payload={"urls": ["https://example.com"]},
        )
        pages = [
            CrawlPageResult(
                url="https://example.com",
                markdown="# Example\nA simple page with button and card hero.",
                title="Example",
                extracted_colors=["#635bff"],
                extracted_fonts=["Inter"],
                component_candidates=["Button", "Card", "Hero"],
            )
        ]
        with (
            patch(
                "pandora_workers.agents.parse_url.crawl_urls",
                new_callable=AsyncMock,
                return_value=pages,
            ),
            patch(
                "pandora_workers.agents.parse_url.complete_json",
                new_callable=AsyncMock,
                return_value={
                    "summary": "Simple example site",
                    "keywords": ["example"],
                    "fonts": [],
                    "colors": [],
                    "component_candidates": ["Hero"],
                    "layout_hints": "minimal",
                    "tone_hints": "neutral",
                },
            ),
        ):
            result = await agent.handle_work(work)
        self.assertEqual(result.payload["source"], "url")
        data = result.payload["data"]
        self.assertEqual(data["crawl_success_count"], 1)
        self.assertNotIn("pages", data)
        self.assertIn("Inter", data["fonts"])
        self.assertIn("#635bff", data["colors"])
        self.assertIn("Button", data["component_candidates"])
        self.assertIn("Simple example site", data["summary"])

    async def test_multi_url_uses_synthesis_pass(self) -> None:
        agent = ParseUrlAgent()
        work = MessageEnvelope(
            event=PipelineEvent.PARSE_REQUEST,
            project_id=5,
            pipeline_id=1,
            payload={"urls": ["https://a.com", "https://b.com"]},
        )
        pages = [
            CrawlPageResult(
                url="https://a.com",
                markdown="Site A",
                extracted_colors=["#111111"],
                extracted_fonts=["Inter"],
                component_candidates=["Hero"],
            ),
            CrawlPageResult(
                url="https://b.com",
                markdown="Site B",
                extracted_colors=["#222222"],
                extracted_fonts=["Georgia"],
                component_candidates=["Footer"],
            ),
        ]
        per_page = {
            "summary": "Page summary",
            "keywords": ["kw"],
            "fonts": [],
            "colors": [],
            "component_candidates": [],
            "layout_hints": "layout",
            "tone_hints": "neutral",
        }
        synthesized = {
            "summary": "Unified cross-site summary",
            "keywords": ["kw"],
            "fonts": ["Inter"],
            "colors": ["#111111", "#222222"],
            "component_candidates": ["Hero", "Footer"],
            "layout_hints": "combined layout",
            "tone_hints": "neutral",
        }
        llm = AsyncMock(side_effect=[per_page, per_page, synthesized])
        with (
            patch(
                "pandora_workers.agents.parse_url.crawl_urls",
                new_callable=AsyncMock,
                return_value=pages,
            ),
            patch("pandora_workers.agents.parse_url.complete_json", llm),
        ):
            result = await agent.handle_work(work)
        data = result.payload["data"]
        self.assertEqual(llm.await_count, 3)
        self.assertIn("pages", data)
        self.assertEqual(len(data["pages"]), 2)
        self.assertEqual(data["summary"], "Unified cross-site summary")

    async def test_crawl_empty_returns_error(self) -> None:
        agent = ParseUrlAgent()
        work = MessageEnvelope(
            event=PipelineEvent.PARSE_REQUEST,
            project_id=3,
            pipeline_id=1,
            payload={"urls": ["https://example.com"]},
        )
        with patch(
            "pandora_workers.agents.parse_url.crawl_urls",
            new_callable=AsyncMock,
            return_value=[],
        ):
            result = await agent.handle_work(work)
        self.assertEqual(result.payload["error"], "crawl_empty")


class ImageAnalysisTests(unittest.TestCase):
    def test_analyze_tiny_png(self) -> None:
        data = analyze_image_bytes(_TINY_PNG)
        self.assertIn("palette", data)
        self.assertEqual(data["extraction_method"], "pill_heuristic")


class ParseImageAgentTests(unittest.IsolatedAsyncioTestCase):
    async def test_fetches_and_analyzes(self) -> None:
        agent = ParseImageAgent()
        work = MessageEnvelope(
            event=PipelineEvent.PARSE_REQUEST,
            project_id=4,
            pipeline_id=1,
            payload={"image_urls": ["http://minio:9000/pandora/test.png"]},
        )
        mock_response = AsyncMock()
        mock_response.raise_for_status = lambda: None
        mock_response.content = _TINY_PNG
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("pandora_workers.agents.parse_image.httpx.AsyncClient", return_value=mock_client):
            result = await agent.handle_work(work)
        self.assertEqual(result.payload["source"], "image")
        self.assertIn("palette", result.payload["data"])


if __name__ == "__main__":
    unittest.main()
