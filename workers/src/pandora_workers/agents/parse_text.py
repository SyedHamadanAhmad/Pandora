"""Text parse agent — ``pandora.parse.text`` → ``pandora.parse.results``."""

from __future__ import annotations

import logging

from pandora_shared.events import MessageEnvelope
from pandora_shared.payloads import ParseTextWorkPayload
from pandora_shared.queues import PARSE_RESULTS, PARSE_TEXT

from pandora_workers.agents.parse_results import parse_result_envelope
from pandora_workers.base_agent import BaseAgent
from pandora_workers.llm import complete_json
from pandora_workers.prompts.loader import render_prompt

logger = logging.getLogger(__name__)


class ParseTextAgent(BaseAgent):
    work_queue = PARSE_TEXT
    result_queue = PARSE_RESULTS

    async def handle_work(self, work: MessageEnvelope) -> MessageEnvelope:
        work_payload = ParseTextWorkPayload.model_validate(work.payload)
        content = work_payload.content.strip()
        if not content:
            return parse_result_envelope(
                work,
                source="text",
                error="empty_content",
            )

        system = render_prompt("json_system.jinja2")
        user = render_prompt("parse_text_user.jinja2", content=content)
        try:
            data = await complete_json(system, user)
        except Exception as exc:
            logger.exception("text parse LLM failed project_id=%s", work.project_id)
            return parse_result_envelope(work, source="text", error=str(exc)[:200])

        data.setdefault("content", content)
        return parse_result_envelope(work, source="text", data=data)
