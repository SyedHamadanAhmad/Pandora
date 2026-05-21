"""URL parse agent — ``pandora.parse.url`` → ``pandora.parse.results``."""

from __future__ import annotations

import logging
from typing import Any

from pandora_shared.events import MessageEnvelope
from pandora_shared.payloads import ParseUrlWorkPayload
from pandora_shared.queues import PARSE_RESULTS, PARSE_URL

from pandora_workers.agents.parse_results import parse_result_envelope
from pandora_workers.base_agent import BaseAgent
from pandora_workers.llm import complete_json
from pandora_workers.prompts.loader import render_prompt
from pandora_workers.url_crawler import CrawlPageResult, crawl_urls
from pandora_workers.url_extract import filter_font_list
from pandora_workers.url_rollup import (
    apply_synthesized_rollup,
    compact_pages_for_synthesis,
    normalize_page_summary,
    rollup_from_pages,
)

logger = logging.getLogger(__name__)


class ParseUrlAgent(BaseAgent):
    work_queue = PARSE_URL
    result_queue = PARSE_RESULTS

    async def handle_work(self, work: MessageEnvelope) -> MessageEnvelope:
        work_payload = ParseUrlWorkPayload.model_validate(work.payload)
        urls = [u.strip() for u in work_payload.urls if u and u.strip()]
        if not urls:
            return parse_result_envelope(work, source="url", error="no_urls")

        try:
            pages = await crawl_urls(urls)
        except Exception as exc:
            logger.exception("url crawl batch failed project_id=%s", work.project_id)
            return parse_result_envelope(work, source="url", error=f"crawl_failed:{exc}"[:200])

        if not pages:
            return parse_result_envelope(work, source="url", error="crawl_empty")

        normalized_pages = await self._summarize_pages(pages)
        combined = await self._build_rollup(urls, normalized_pages, len(pages))
        return parse_result_envelope(work, source="url", data=combined)

    async def _summarize_pages(self, pages: list[CrawlPageResult]) -> list[dict[str, Any]]:
        system = render_prompt("parse_analyst_system.jinja2")
        normalized: list[dict[str, Any]] = []

        for page in pages:
            user = render_prompt(
                "parse_url_user.jinja2",
                url=page.url,
                title=page.title or "",
                markdown=page.markdown,
                extracted_colors=page.extracted_colors,
                extracted_fonts=page.extracted_fonts,
                component_candidates=page.component_candidates,
            )
            try:
                raw = await complete_json(system, user)
            except Exception as exc:
                logger.warning("url LLM summarize failed url=%s: %s", page.url, exc)
                raw = {
                    "summary": page.markdown[:500],
                    "keywords": [],
                    "fonts": list(page.extracted_fonts),
                    "colors": list(page.extracted_colors),
                    "component_candidates": list(page.component_candidates),
                    "layout_hints": None,
                    "tone_hints": None,
                }
            raw["fonts"] = filter_font_list(
                [*page.extracted_fonts, *(raw.get("fonts") or [])]
            )
            raw["colors"] = [*page.extracted_colors, *(raw.get("colors") or [])]
            raw["component_candidates"] = [
                *page.component_candidates,
                *(raw.get("component_candidates") or []),
            ]
            normalized.append(normalize_page_summary(raw, url=page.url))

        return normalized

    async def _build_rollup(
        self,
        urls: list[str],
        normalized_pages: list[dict[str, Any]],
        crawl_success_count: int,
    ) -> dict[str, Any]:
        if len(normalized_pages) == 1:
            data = rollup_from_pages(normalized_pages)
            data["urls"] = urls
            data["crawl_success_count"] = crawl_success_count
            return data

        system = render_prompt("parse_analyst_system.jinja2")
        user = render_prompt(
            "parse_url_synthesize.jinja2",
            pages_json=compact_pages_for_synthesis(normalized_pages),
        )
        try:
            synthesized = await complete_json(system, user)
        except Exception as exc:
            logger.warning(
                "url rollup synthesis failed, using mechanical merge: %s",
                exc,
            )
            synthesized = _mechanical_multi_rollup(normalized_pages)
        return apply_synthesized_rollup(
            synthesized,
            urls=urls,
            pages=normalized_pages,
            crawl_success_count=crawl_success_count,
        )


def _mechanical_multi_rollup(pages: list[dict[str, Any]]) -> dict[str, Any]:
    """Fallback if synthesis LLM fails — better than pipe-concat of summaries."""
    from pandora_workers.url_rollup import dedupe_strings

    summaries = [p.get("summary") for p in pages if p.get("summary")]
    return {
        "summary": " ".join(summaries)[:2000] if summaries else None,
        "keywords": dedupe_strings(kw for p in pages for kw in (p.get("keywords") or [])),
        "fonts": filter_font_list(f for p in pages for f in (p.get("fonts") or [])),
        "colors": dedupe_strings(c for p in pages for c in (p.get("colors") or [])),
        "component_candidates": dedupe_strings(
            n for p in pages for n in (p.get("component_candidates") or [])
        ),
        "layout_hints": "; ".join(
            p.get("layout_hints") for p in pages if p.get("layout_hints")
        )[:1000]
        or None,
        "tone_hints": pages[0].get("tone_hints") if pages else None,
    }
