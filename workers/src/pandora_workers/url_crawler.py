"""Fetch page content for URL parse agent (Crawl4AI)."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from pandora_workers.url_extract import (
    extract_colors,
    extract_fonts,
    infer_component_candidates,
)

logger = logging.getLogger(__name__)

MAX_MARKDOWN_CHARS = 12_000
MAX_HTML_CHARS = 80_000


@dataclass
class CrawlPageResult:
    url: str
    markdown: str
    title: str | None = None
    extracted_colors: list[str] = field(default_factory=list)
    extracted_fonts: list[str] = field(default_factory=list)
    component_candidates: list[str] = field(default_factory=list)


async def crawl_urls(urls: list[str]) -> list[CrawlPageResult]:
    """Crawl each URL; skip failures and return successful pages only."""
    if not urls:
        return []

    from crawl4ai import AsyncWebCrawler

    results: list[CrawlPageResult] = []
    async with AsyncWebCrawler(verbose=False) as crawler:
        for url in urls:
            try:
                from pandora_shared.url_validation import assert_safe_http_url

                assert_safe_http_url(url)
            except ValueError:
                logger.warning("blocked unsafe crawl url=%s", url)
                continue
            try:
                page = await crawler.arun(url=url)
            except Exception:
                logger.exception("crawl failed url=%s", url)
                continue
            if not page.success:
                logger.warning(
                    "crawl unsuccessful url=%s error=%s",
                    url,
                    getattr(page, "error_message", None),
                )
                continue
            html = (
                getattr(page, "cleaned_html", None)
                or getattr(page, "html", None)
                or ""
            )
            markdown = (page.markdown or "").strip()
            if not markdown and html:
                markdown = html.strip()[:MAX_MARKDOWN_CHARS]
            if not markdown:
                logger.warning("crawl returned empty content url=%s", url)
                continue
            title = None
            metadata = getattr(page, "metadata", None)
            if isinstance(metadata, dict):
                title = metadata.get("title")
            html_sample = html[:MAX_HTML_CHARS] if html else ""
            colors = extract_colors(html_sample)
            fonts = extract_fonts(html_sample)
            components = infer_component_candidates(markdown, title or "")
            results.append(
                CrawlPageResult(
                    url=url,
                    markdown=markdown[:MAX_MARKDOWN_CHARS],
                    title=title,
                    extracted_colors=colors,
                    extracted_fonts=fonts,
                    component_candidates=components,
                )
            )
    return results
