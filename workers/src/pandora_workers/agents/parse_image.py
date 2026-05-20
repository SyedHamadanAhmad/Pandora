"""Image parse agent — ``pandora.parse.image`` → ``pandora.parse.results``."""

from __future__ import annotations

import logging

import httpx

from pandora_shared.events import MessageEnvelope
from pandora_shared.payloads import ParseImageWorkPayload
from pandora_shared.queues import PARSE_IMAGE, PARSE_RESULTS

from pandora_workers.agents.parse_results import parse_result_envelope
from pandora_workers.base_agent import BaseAgent
from pandora_workers.image_analysis import analyze_image_bytes

logger = logging.getLogger(__name__)

FETCH_TIMEOUT = 30.0


class ParseImageAgent(BaseAgent):
    work_queue = PARSE_IMAGE
    result_queue = PARSE_RESULTS

    async def handle_work(self, work: MessageEnvelope) -> MessageEnvelope:
        work_payload = ParseImageWorkPayload.model_validate(work.payload)
        urls = work_payload.image_urls
        if not urls:
            return parse_result_envelope(work, source="image", error="no_image_urls")

        palettes: list[str] = []
        merged_roles: dict[str, str] = {}
        layout_hints: list[str] = []
        fetched = 0

        async with httpx.AsyncClient(timeout=FETCH_TIMEOUT, follow_redirects=True) as client:
            for url in urls:
                try:
                    response = await client.get(url)
                    response.raise_for_status()
                except Exception:
                    logger.warning("image fetch failed url=%s", url)
                    continue
                try:
                    analysis = analyze_image_bytes(response.content)
                except Exception:
                    logger.exception("image analysis failed url=%s", url)
                    continue
                fetched += 1
                palettes.extend(analysis.get("palette") or [])
                merged_roles.update(analysis.get("color_roles") or {})
                hint = analysis.get("layout_hints")
                if hint:
                    layout_hints.append(str(hint))

        if fetched == 0:
            return parse_result_envelope(work, source="image", error="image_fetch_failed")

        unique_palette = list(dict.fromkeys(palettes))[:8]
        data = {
            "image_urls": urls,
            "palette": unique_palette,
            "color_roles": merged_roles,
            "layout_hints": "; ".join(layout_hints) if layout_hints else None,
            "images_analyzed": fetched,
            "extraction_method": "pill_heuristic",
        }
        return parse_result_envelope(work, source="image", data=data)
