"""Schema agent — ``pandora.schema.request`` → ``pandora.schema.ready``."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from pandora_shared.events import MessageEnvelope, PipelineEvent
from pandora_shared.payloads import SchemaReadyPayload, SchemaRequestWorkPayload
from pandora_shared.queues import SCHEMA_READY, SCHEMA_REQUEST

from pandora_workers.base_agent import BaseAgent
from pandora_workers.envelopes import build_result
from pandora_workers.llm import complete_json
from pandora_workers.prompts.loader import render_prompt

logger = logging.getLogger(__name__)

_MAX_SPECS = 15
_MAX_VARIANTS = 8
_MAX_PROMPT_CHARS = 28_000


def _truncate_for_prompt(obj: Any, *, max_str: int = 2000, max_list: int = 50, depth: int = 0) -> Any:
    if depth > 14:
        return "[truncated-depth]"
    if isinstance(obj, str):
        if len(obj) <= max_str:
            return obj
        return obj[:max_str] + "…[truncated]"
    if isinstance(obj, dict):
        return {str(k): _truncate_for_prompt(v, max_str=max_str, max_list=max_list, depth=depth + 1) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_truncate_for_prompt(v, max_str=max_str, max_list=max_list, depth=depth + 1) for v in obj[:max_list]]
    return obj


def _brief_json_for_prompt(work: dict[str, Any]) -> str:
    trimmed = _truncate_for_prompt(dict(work))
    raw = json.dumps(trimmed, ensure_ascii=False, separators=(",", ":"))
    if len(raw) <= _MAX_PROMPT_CHARS:
        return raw
    return raw[:_MAX_PROMPT_CHARS] + '"…[truncated]"'


def _guess_component_type(name: str) -> str:
    key = name.lower()
    if "button" in key or "cta" in key:
        return "button"
    if "badge" in key or "chip" in key or "tag" in key:
        return "badge"
    if "input" in key or "field" in key or "search" in key:
        return "input"
    if "card" in key or "tile" in key:
        return "card"
    if "nav" in key or "menu" in key or "tab" in key:
        return "navigation"
    if "modal" in key or "dialog" in key:
        return "modal"
    if "hero" in key or "banner" in key:
        return "layout"
    if "list" in key or "grid" in key:
        return "layout"
    return "layout"


def _normalize_spec(raw: dict[str, Any]) -> dict[str, Any]:
    name = str(raw.get("name") or "").strip() or "Component"
    name = re.sub(r"\s+", "", name)
    if not name[0].isalpha():
        name = f"C{name}" if name else "Component"
    variants = raw.get("variants") or ["default"]
    if not isinstance(variants, list):
        variants = ["default"]
    clean_variants: list[str] = []
    for v in variants:
        if isinstance(v, str) and v.strip() and v.strip() not in clean_variants:
            clean_variants.append(v.strip())
        if len(clean_variants) >= _MAX_VARIANTS:
            break
    if not clean_variants:
        clean_variants = ["default"]
    typ = raw.get("type")
    if not isinstance(typ, str) or not typ.strip():
        typ = _guess_component_type(name)
    layout = raw.get("layout")
    if layout is not None and not isinstance(layout, str):
        layout = str(layout)
    out: dict[str, Any] = {
        "name": name[:120],
        "type": typ.strip()[:64],
        "variants": clean_variants,
    }
    if layout is not None:
        out["layout"] = layout.strip()[:120] or None
    return out


def _fallback_schema(work: dict[str, Any]) -> dict[str, Any]:
    colors = work.get("color_tokens") if isinstance(work.get("color_tokens"), dict) else {}
    design_tokens: dict[str, Any] = {**colors} if colors else {"primary": "#2563eb", "radius": "8px"}
    flavour = work.get("design_flavour") if isinstance(work.get("design_flavour"), str) else None
    global_config: dict[str, Any] = {"theme": "light"}
    if flavour:
        global_config["design_flavour"] = flavour
    names = work.get("component_list")
    if not isinstance(names, list):
        names = []
    specs: list[dict[str, Any]] = []
    for raw in names[:_MAX_SPECS]:
        if not isinstance(raw, str) or not raw.strip():
            continue
        n = raw.strip()
        specs.append(
            {
                "name": n,
                "type": _guess_component_type(n),
                "variants": ["default", "primary"],
                "layout": "vertical",
            }
        )
    if not specs:
        specs = [{"name": "Button", "type": "button", "variants": ["primary"], "layout": None}]
    return {
        "design_tokens": design_tokens,
        "global_config": global_config,
        "component_specs": specs,
    }


def _merge_llm_schema(llm: dict[str, Any], *, work: dict[str, Any]) -> dict[str, Any]:
    design_tokens = llm.get("design_tokens")
    if not isinstance(design_tokens, dict) or not design_tokens:
        fb = work.get("color_tokens") if isinstance(work.get("color_tokens"), dict) else {}
        design_tokens = dict(fb) if fb else {"primary": "#2563eb", "radius": "8px"}

    global_config = llm.get("global_config")
    if not isinstance(global_config, dict):
        global_config = {}
    flavour = work.get("design_flavour")
    if isinstance(flavour, str) and flavour.strip() and "design_flavour" not in global_config:
        global_config = {**global_config, "design_flavour": flavour.strip()}
    if "theme" not in global_config:
        global_config = {**global_config, "theme": "light"}

    raw_specs = llm.get("component_specs")
    normalized: list[dict[str, Any]] = []
    if isinstance(raw_specs, list):
        for item in raw_specs:
            if isinstance(item, dict) and item.get("name"):
                normalized.append(_normalize_spec(item))
            if len(normalized) >= _MAX_SPECS:
                break

    if len(normalized) < 1:
        return _fallback_schema(work)

    return {
        "design_tokens": design_tokens,
        "global_config": global_config,
        "component_specs": normalized[:_MAX_SPECS],
    }


class SchemaAgent(BaseAgent):
    work_queue = SCHEMA_REQUEST
    result_queue = SCHEMA_READY

    async def handle_work(self, work: MessageEnvelope) -> MessageEnvelope:
        SchemaRequestWorkPayload.model_validate(work.payload)
        brief_dict: dict[str, Any] = dict(work.payload)

        system = render_prompt("design_system_lead_system.jinja2")
        user = render_prompt(
            "schema_user.jinja2",
            brief_json=_brief_json_for_prompt(brief_dict),
        )

        merged: dict[str, Any]
        try:
            raw = await complete_json(system, user)
            if isinstance(raw, dict):
                merged = _merge_llm_schema(raw, work=brief_dict)
            else:
                merged = _fallback_schema(brief_dict)
        except Exception as exc:
            logger.warning("schema LLM failed project_id=%s: %s", work.project_id, exc)
            merged = _fallback_schema(brief_dict)

        try:
            validated = SchemaReadyPayload.model_validate(merged)
        except Exception as exc:
            logger.warning("schema payload validation failed, using fallback: %s", exc)
            validated = SchemaReadyPayload.model_validate(_fallback_schema(brief_dict))

        return build_result(
            work,
            event=PipelineEvent.SCHEMA_READY,
            payload=validated.model_dump(),
        )
