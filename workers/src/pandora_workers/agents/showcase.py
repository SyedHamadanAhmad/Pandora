"""Showcase agent — ``pandora.showcase.generate`` → ``pandora.showcase.ready``."""

from __future__ import annotations

import json
import logging
from typing import Any

from pandora_shared.events import MessageEnvelope, PipelineEvent
from pandora_shared.payloads import ShowcaseGenerateWorkPayload, ShowcaseReadyPayload
from pandora_shared.queues import SHOWCASE_GENERATE, SHOWCASE_READY

from pandora_workers.base_agent import BaseAgent
from pandora_workers.envelopes import build_result
from pandora_workers.llm import complete_json
from pandora_workers.prompts.loader import render_prompt

logger = logging.getLogger(__name__)

_MAX_PROMPT_CHARS = 28_000
_MAX_SCENES = 3


def _json_for_prompt(obj: Any, *, max_chars: int = _MAX_PROMPT_CHARS) -> str:
    raw = json.dumps(obj if obj is not None else {}, ensure_ascii=False, separators=(",", ":"))
    if len(raw) <= max_chars:
        return raw
    return raw[:max_chars] + '"…[truncated]"'


def _normalize_scene(raw: dict[str, Any], *, index: int) -> dict[str, Any]:
    name = str(raw.get("scene_name") or f"Scene {index + 1}").strip()[:120]
    tsx = raw.get("scene_tsx_code")
    if not isinstance(tsx, str) or not tsx.strip():
        tsx = f'<div className="scene-{index}">Scene {index + 1}</div>'
    css = raw.get("scene_css_code")
    if css is not None and not isinstance(css, str):
        css = str(css)
    used = raw.get("components_used")
    if not isinstance(used, list):
        used = []
    clean_used = [str(u).strip() for u in used if isinstance(u, str) and str(u).strip()][:20]
    return {
        "scene_index": int(raw.get("scene_index", index)),
        "scene_name": name,
        "scene_tsx_code": tsx.strip()[:12_000],
        "scene_css_code": css.strip()[:8000] if isinstance(css, str) and css.strip() else None,
        "components_used": clean_used,
    }


def _fallback_showcase(work: dict[str, Any]) -> dict[str, Any]:
    names = [
        str(c.get("name")).strip()
        for c in (work.get("components") or [])
        if isinstance(c, dict) and c.get("name")
    ]
    used = names[:5] or ["Component"]
    label = ", ".join(used)
    return {
        "scenes": [
            {
                "scene_index": 0,
                "scene_name": "Showcase",
                "scene_tsx_code": (
                    f'<div className="pandora-showcase">'
                    f"<h1>Design system showcase</h1>"
                    f"<p>Components: {label}</p>"
                    f"</div>"
                ),
                "scene_css_code": (
                    ".pandora-showcase { padding: 48px; max-width: 960px; margin: 0 auto; }"
                ),
                "components_used": used,
            }
        ]
    }


def _merge_showcase(llm: dict[str, Any], *, work: dict[str, Any]) -> dict[str, Any]:
    raw_scenes = llm.get("scenes")
    normalized: list[dict[str, Any]] = []
    if isinstance(raw_scenes, list):
        for index, item in enumerate(raw_scenes):
            if isinstance(item, dict):
                normalized.append(_normalize_scene(item, index=index))
            if len(normalized) >= _MAX_SCENES:
                break
    if normalized:
        return {"scenes": normalized}
    return _fallback_showcase(work)


class ShowcaseAgent(BaseAgent):
    work_queue = SHOWCASE_GENERATE
    result_queue = SHOWCASE_READY

    async def handle_work(self, work: MessageEnvelope) -> MessageEnvelope:
        work_payload = ShowcaseGenerateWorkPayload.model_validate(work.payload)
        work_dict = work_payload.model_dump()

        system = render_prompt("json_system.jinja2")
        user = render_prompt(
            "showcase_user.jinja2",
            design_tokens_json=_json_for_prompt(work_payload.design_tokens or {}),
            global_config_json=_json_for_prompt(work_payload.global_config or {}),
            components_json=_json_for_prompt(work_payload.components),
        )

        merged: dict[str, Any]
        try:
            raw = await complete_json(system, user)
            if isinstance(raw, dict):
                merged = _merge_showcase(raw, work=work_dict)
            else:
                merged = _fallback_showcase(work_dict)
        except Exception as exc:
            logger.warning("showcase LLM failed project_id=%s: %s", work.project_id, exc)
            merged = _fallback_showcase(work_dict)

        try:
            validated = ShowcaseReadyPayload.model_validate(merged)
        except Exception as exc:
            logger.warning("showcase payload validation failed: %s", exc)
            validated = ShowcaseReadyPayload.model_validate(_fallback_showcase(work_dict))

        return build_result(
            work,
            event=PipelineEvent.SHOWCASE_READY,
            payload=validated.model_dump(),
        )
