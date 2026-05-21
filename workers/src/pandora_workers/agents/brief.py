"""Design brief agent — ``pandora.brief.request`` → ``pandora.brief.ready``."""

from __future__ import annotations

import json
import logging
from typing import Any

from pandora_shared.events import MessageEnvelope, PipelineEvent
from pandora_shared.payloads import BriefReadyPayload, BriefRequestWorkPayload
from pandora_shared.queues import BRIEF_READY, BRIEF_REQUEST

from pandora_workers.base_agent import BaseAgent
from pandora_workers.envelopes import build_result
from pandora_workers.llm import complete_json
from pandora_workers.prompts.loader import render_prompt

logger = logging.getLogger(__name__)

_BRIEF_LLM_KEYS = (
    "color_tokens",
    "typography_scale",
    "spacing_system",
    "design_flavour",
    "tone",
    "component_list",
)

_DEFAULT_SPACING: dict[str, Any] = {"unit": 4}
_MAX_COMPONENT_NAMES = 15
_MAX_PROMPT_CHARS = 28_000


def _truncate_for_prompt(obj: Any, *, max_str: int = 1800, max_list: int = 40, depth: int = 0) -> Any:
    """Shrink nested parse blobs so URL markdown does not blow the context window."""
    if depth > 14:
        return "[truncated-depth]"
    if isinstance(obj, str):
        if len(obj) <= max_str:
            return obj
        return obj[:max_str] + "…[truncated]"
    if isinstance(obj, dict):
        return {str(k): _truncate_for_prompt(v, max_str=max_str, max_list=max_list, depth=depth + 1) for k, v in obj.items()}
    if isinstance(obj, list):
        clipped = obj[:max_list]
        return [_truncate_for_prompt(v, max_str=max_str, max_list=max_list, depth=depth + 1) for v in clipped]
    return obj


def _sources_json_for_prompt(sources: dict[str, Any]) -> str:
    trimmed = _truncate_for_prompt(dict(sources))
    raw = json.dumps(trimmed, ensure_ascii=False, separators=(",", ":"))
    if len(raw) <= _MAX_PROMPT_CHARS:
        return raw
    return raw[: _MAX_PROMPT_CHARS] + '"…[truncated]"'


def _parse_block(sources: dict[str, Any], key: str) -> dict[str, Any] | None:
    block = sources.get(key)
    if not isinstance(block, dict):
        return None
    if block.get("error"):
        return None
    data = block.get("data")
    return data if isinstance(data, dict) else None


def _heuristic_defaults(sources: dict[str, Any]) -> dict[str, Any]:
    """Deterministic fallbacks when the LLM omits fields or fails."""
    out: dict[str, Any] = {
        "color_tokens": None,
        "typography_scale": None,
        "spacing_system": dict(_DEFAULT_SPACING),
        "design_flavour": "modern-saas",
        "tone": "professional",
        "component_list": None,
    }

    url = _parse_block(sources, "url")
    if url:
        colors = [c for c in (url.get("colors") or []) if isinstance(c, str) and c.strip()]
        if colors:
            tokens: dict[str, str] = {"primary": colors[0]}
            if len(colors) > 1:
                tokens["secondary"] = colors[1]
            if len(colors) > 2:
                tokens["accent"] = colors[2]
            out["color_tokens"] = tokens
        fonts = [f for f in (url.get("fonts") or []) if isinstance(f, str) and f.strip()]
        if fonts:
            out["typography_scale"] = {
                "base": "16px",
                "heading": "24px",
                "font_sans": fonts[0],
            }
        comps = [c for c in (url.get("component_candidates") or []) if isinstance(c, str) and c.strip()]
        if comps:
            seen: set[str] = set()
            deduped: list[str] = []
            for name in comps:
                if name not in seen:
                    seen.add(name)
                    deduped.append(name)
                if len(deduped) >= _MAX_COMPONENT_NAMES:
                    break
            out["component_list"] = deduped
        tone = url.get("tone_hints")
        if isinstance(tone, str) and tone.strip():
            out["tone"] = tone.strip()[:200]

    image = _parse_block(sources, "image")
    if image and out["color_tokens"] is None:
        palette = image.get("palette") or []
        roles = image.get("color_roles") or {}
        if isinstance(roles, dict) and roles:
            out["color_tokens"] = {
                str(k): str(v) for k, v in roles.items() if v is not None and str(v).strip()
            }
        elif isinstance(palette, list) and palette:
            colors = [str(c) for c in palette if c][:3]
            if colors:
                out["color_tokens"] = {"primary": colors[0]}
                if len(colors) > 1:
                    out["color_tokens"]["secondary"] = colors[1]

    text = _parse_block(sources, "text")
    if text:
        th = text.get("tone_hints")
        if isinstance(th, str) and th.strip():
            out["tone"] = th.strip()[:200]
        if out["component_list"] is None:
            reqs = text.get("requirements") or []
            if isinstance(reqs, list):
                names = [str(r).strip() for r in reqs if str(r).strip()][:5]
                if names:
                    out["component_list"] = names

    return out


def _dedupe_components(names: object) -> list[str] | None:
    if not isinstance(names, list):
        return None
    seen_lower: set[str] = set()
    out: list[str] = []
    for raw in names:
        if not isinstance(raw, str):
            continue
        name = raw.strip()
        if not name:
            continue
        key = name.lower()
        if key in seen_lower:
            continue
        seen_lower.add(key)
        out.append(name)
        if len(out) >= _MAX_COMPONENT_NAMES:
            break
    return out or None


def _merge_brief_dict(
    llm: dict[str, Any],
    *,
    input_gaps: list[str],
    heuristic: dict[str, Any],
) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for key in _BRIEF_LLM_KEYS:
        val = llm.get(key)
        if val is None or (key == "component_list" and val in ([], None)):
            val = heuristic.get(key)
        if key == "component_list" and val is not None:
            val = _dedupe_components(val)
        merged[key] = val

    if merged.get("spacing_system") is None:
        merged["spacing_system"] = dict(_DEFAULT_SPACING)

    merged["input_gaps"] = list(input_gaps)
    return merged


class BriefAgent(BaseAgent):
    work_queue = BRIEF_REQUEST
    result_queue = BRIEF_READY

    async def handle_work(self, work: MessageEnvelope) -> MessageEnvelope:
        work_payload = BriefRequestWorkPayload.model_validate(work.payload)
        gaps = list(work_payload.input_gaps)
        heuristic = _heuristic_defaults(work_payload.sources)

        system = render_prompt("design_system_lead_system.jinja2")
        user = render_prompt(
            "brief_user.jinja2",
            sources_json=_sources_json_for_prompt(work_payload.sources),
            input_gaps=gaps,
        )

        llm_slice: dict[str, Any] = {k: None for k in _BRIEF_LLM_KEYS}
        try:
            raw = await complete_json(system, user)
            if isinstance(raw, dict):
                llm_slice = {key: raw.get(key) for key in _BRIEF_LLM_KEYS}
        except Exception as exc:
            logger.warning("brief LLM failed project_id=%s: %s", work.project_id, exc)

        merged = _merge_brief_dict(llm_slice, input_gaps=gaps, heuristic=heuristic)
        try:
            validated = BriefReadyPayload.model_validate(merged)
        except Exception as exc:
            logger.warning("brief payload validation failed, using heuristics only: %s", exc)
            validated = BriefReadyPayload.model_validate(
                _merge_brief_dict({k: None for k in _BRIEF_LLM_KEYS}, input_gaps=gaps, heuristic=heuristic)
            )

        return build_result(
            work,
            event=PipelineEvent.BRIEF_READY,
            payload=validated.model_dump(),
        )
