"""Schema agent — ``pandora.schema.request`` → ``pandora.schema.ready``."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from pandora_shared.events import MessageEnvelope, PipelineEvent
from pandora_shared.payloads import SchemaReadyPayload, SchemaRequestWorkPayload
from pandora_shared.queues import SCHEMA_READY, SCHEMA_REQUEST

from pandora_shared.design_color import enrich_semantic_color_tokens

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
        return "hero"
    if "section" in key or "layout" in key or "page" in key or "container" in key:
        return "layout"
    # Dropdowns, toggles, accordions, tables, tooltips, etc. are generic.
    return "generic"


def _extract_variant_name(v: Any) -> str | None:
    """Accept both plain strings and {name, style_hint} variant objects."""
    if isinstance(v, str) and v.strip():
        return v.strip()
    if isinstance(v, dict):
        n = v.get("name")
        if isinstance(n, str) and n.strip():
            return n.strip()
    return None


def _normalize_spec(raw: dict[str, Any]) -> dict[str, Any]:
    name = str(raw.get("name") or "").strip() or "Component"
    name = re.sub(r"\s+", "", name)
    if not name[0].isalpha():
        name = f"C{name}" if name else "Component"
    raw_variants = raw.get("variants") or ["default"]
    if not isinstance(raw_variants, list):
        raw_variants = ["default"]
    clean_variants: list[str] = []
    for v in raw_variants:
        extracted = _extract_variant_name(v)
        if extracted and extracted not in clean_variants:
            clean_variants.append(extracted)
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

    # Build style_hints map from variant objects so component_gen can use them.
    style_hints: dict[str, str] = {}
    for v in raw_variants:
        if isinstance(v, dict):
            vname = _extract_variant_name(v)
            hint = v.get("style_hint") or v.get("styleHint")
            if vname and isinstance(hint, str) and hint.strip():
                style_hints[vname] = hint.strip()[:200]

    out: dict[str, Any] = {
        "name": name[:120],
        "type": typ.strip()[:64],
        "variants": clean_variants,
    }
    if layout is not None:
        out["layout"] = layout.strip()[:120] or None
    if style_hints:
        out["variant_style_hints"] = style_hints
    # Forward any prop defaults the schema agent produced.
    spec_props = raw.get("props")
    if isinstance(spec_props, dict) and spec_props:
        out["props"] = spec_props
    return out


_DEFAULT_SPACING: dict[str, Any] = {"unit": 4}


def _brief_snapshot(work: dict[str, Any]) -> dict[str, Any]:
    """Small brief slice for downstream agents (no full parse blobs)."""
    keys = (
        "design_flavour",
        "tone",
        "color_tokens",
        "typography_scale",
        "spacing_system",
        "component_list",
    )
    return {k: work[k] for k in keys if k in work}


def _enrich_design_tokens(brief: dict[str, Any], llm_tokens: dict[str, Any]) -> dict[str, Any]:
    """Merge brief colors + LLM tokens; always attach typography, spacing, and elevation (W-03)."""
    colors = brief.get("color_tokens") if isinstance(brief.get("color_tokens"), dict) else {}
    typo = brief.get("typography_scale") if isinstance(brief.get("typography_scale"), dict) else {}
    spacing = (
        brief.get("spacing_system")
        if isinstance(brief.get("spacing_system"), dict)
        else dict(_DEFAULT_SPACING)
    )
    out: dict[str, Any] = {**colors, **llm_tokens}
    if typo:
        out.setdefault("typography", typo)

    # Normalised spacing with named steps always present.
    if not out.get("spacing") or not isinstance(out.get("spacing"), dict):
        unit = int(spacing.get("unit") or 4)
        out["spacing"] = {
            "unit": unit,
            "xs": f"{unit}px",
            "sm": f"{unit * 2}px",
            "md": f"{unit * 4}px",
            "lg": f"{unit * 6}px",
            "xl": f"{unit * 8}px",
            "2xl": f"{unit * 12}px",
        }

    # Border radius family.
    if not out.get("radius"):
        radius = llm_tokens.get("radius") if isinstance(llm_tokens.get("radius"), str) else None
        out["radius"] = radius or "8px"
    out.setdefault("radius_sm", "4px")
    out.setdefault("radius_lg", "12px")
    out.setdefault("radius_full", "9999px")

    # Elevation shadows — always present so CSS can reference var(--shadow-sm) etc.
    out.setdefault(
        "shadow_sm",
        "0 1px 3px 0 rgba(0,0,0,0.10), 0 1px 2px -1px rgba(0,0,0,0.10)",
    )
    out.setdefault(
        "shadow_md",
        "0 4px 12px 0 rgba(0,0,0,0.12), 0 2px 4px -2px rgba(0,0,0,0.08)",
    )
    out.setdefault(
        "shadow_lg",
        "0 10px 40px -4px rgba(0,0,0,0.18), 0 4px 12px -4px rgba(0,0,0,0.10)",
    )

    # Border token.
    out.setdefault("border_color", "rgba(0,0,0,0.08)")

    # Primary color + semantic palette.
    if not out.get("primary") and isinstance(colors.get("primary"), str):
        out["primary"] = colors["primary"]
    if not out.get("primary"):
        out.setdefault("primary", "#2563eb")

    return enrich_semantic_color_tokens(out)


def _fallback_schema(work: dict[str, Any]) -> dict[str, Any]:
    colors = work.get("color_tokens") if isinstance(work.get("color_tokens"), dict) else {}
    base_tokens: dict[str, Any] = {**colors} if colors else {"primary": "#2563eb", "radius": "8px"}
    design_tokens = _enrich_design_tokens(work, base_tokens)
    flavour = work.get("design_flavour") if isinstance(work.get("design_flavour"), str) else None
    global_config: dict[str, Any] = {"theme": "light", "brief": _brief_snapshot(work)}
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
    raw_tokens = llm.get("design_tokens")
    if not isinstance(raw_tokens, dict) or not raw_tokens:
        fb = work.get("color_tokens") if isinstance(work.get("color_tokens"), dict) else {}
        raw_tokens = dict(fb) if fb else {"primary": "#2563eb", "radius": "8px"}
    design_tokens = _enrich_design_tokens(work, raw_tokens)

    global_config = llm.get("global_config")
    if not isinstance(global_config, dict):
        global_config = {}
    flavour = work.get("design_flavour")
    if isinstance(flavour, str) and flavour.strip() and "design_flavour" not in global_config:
        global_config = {**global_config, "design_flavour": flavour.strip()}
    if "theme" not in global_config:
        global_config = {**global_config, "theme": "light"}
    if "brief" not in global_config:
        global_config = {**global_config, "brief": _brief_snapshot(work)}

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
