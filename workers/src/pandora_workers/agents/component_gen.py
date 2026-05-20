"""ComponentGen agent — ``pandora.component.generate`` → ``pandora.component.generated``."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from pandora_shared.events import MessageEnvelope, PipelineEvent
from pandora_shared.payloads import (
    ComponentGenerateWorkPayload,
    ComponentGeneratedPayload,
)
from pandora_shared.queues import COMPONENT_GENERATED, COMPONENT_GENERATE

from pandora_workers.base_agent import BaseAgent
from pandora_workers.envelopes import build_result
from pandora_workers.llm import complete_json
from pandora_workers.prompts.loader import render_prompt

logger = logging.getLogger(__name__)

_MAX_PROMPT_CHARS = 24_000
_MAX_TSX_CHARS = 32_000


def _safe_component_name(raw: str | None) -> str:
    name = str(raw or "Component").strip()
    name = re.sub(r"[^A-Za-z0-9_]", "", name.replace(" ", ""))
    if not name:
        return "Component"
    if not name[0].isalpha():
        name = f"C{name}"
    return name[:80]


def _json_for_prompt(obj: Any, *, max_chars: int = _MAX_PROMPT_CHARS) -> str:
    raw = json.dumps(obj if obj is not None else {}, ensure_ascii=False, separators=(",", ":"))
    if len(raw) <= max_chars:
        return raw
    return raw[:max_chars] + '"…[truncated]"'


def _normalize_variants(spec: dict[str, Any], llm: dict[str, Any]) -> list[str]:
    variants = llm.get("variants")
    if isinstance(variants, list):
        clean = [str(v).strip() for v in variants if isinstance(v, str) and str(v).strip()]
        if clean:
            return clean[:8]
    spec_variants = spec.get("variants")
    if isinstance(spec_variants, list):
        clean = [str(v).strip() for v in spec_variants if isinstance(v, str) and str(v).strip()]
        if clean:
            return clean[:8]
    return ["default"]


def _fallback_component(
    spec: dict[str, Any],
    *,
    design_tokens: dict[str, Any] | None,
) -> dict[str, Any]:
    name = _safe_component_name(spec.get("name"))
    lower = name.lower()
    primary = "#2563eb"
    if isinstance(design_tokens, dict):
        raw = design_tokens.get("primary")
        if isinstance(raw, str) and raw.strip():
            primary = raw.strip()
    variants = _normalize_variants(spec, {})
    return {
        "tsx_code": (
            f"import type {{ ReactNode }} from 'react';\n\n"
            f"export type {name}Props = {{\n"
            f"  label?: string;\n"
            f"  children?: ReactNode;\n"
            f"}};\n\n"
            f"export function {name}({{ label = 'Click', children }}: {name}Props) {{\n"
            f"  return (\n"
            f"    <button type=\"button\" className=\"pandora-{lower}\">\n"
            f"      {{children ?? label}}\n"
            f"    </button>\n"
            f"  );\n"
            f"}}\n"
        ),
        "css_code": (
            f".pandora-{lower} {{\n"
            f"  padding: 8px 16px;\n"
            f"  background: {primary};\n"
            f"  color: #fff;\n"
            f"  border: none;\n"
            f"  border-radius: 8px;\n"
            f"  cursor: pointer;\n"
            f"}}\n"
        ),
        "props": {"label": "Click"},
        "variants": variants,
    }


def _merge_llm_component(
    llm: dict[str, Any],
    *,
    spec: dict[str, Any],
    design_tokens: dict[str, Any] | None,
) -> dict[str, Any]:
    name = _safe_component_name(spec.get("name"))
    tsx = llm.get("tsx_code")
    if not isinstance(tsx, str) or not tsx.strip():
        return _fallback_component(spec, design_tokens=design_tokens)
    tsx = tsx.strip()
    if len(tsx) > _MAX_TSX_CHARS:
        tsx = tsx[:_MAX_TSX_CHARS]

    css = llm.get("css_code")
    if css is not None and not isinstance(css, str):
        css = str(css)
    if isinstance(css, str) and not css.strip():
        css = None

    props = llm.get("props")
    if props is not None and not isinstance(props, dict):
        props = None

    return {
        "tsx_code": tsx,
        "css_code": css,
        "props": props,
        "variants": _normalize_variants(spec, llm),
    }


class ComponentGenAgent(BaseAgent):
    work_queue = COMPONENT_GENERATE
    result_queue = COMPONENT_GENERATED

    async def handle_work(self, work: MessageEnvelope) -> MessageEnvelope:
        if work.component_id is None:
            raise ValueError("component.generate missing component_id")

        work_payload = ComponentGenerateWorkPayload.model_validate(work.payload)
        spec = dict(work_payload.spec) if work_payload.spec else {}
        design_tokens = work_payload.design_tokens
        global_config = work_payload.global_config or {}
        revision = work_payload.revision_instruction

        name = _safe_component_name(spec.get("name"))
        system = render_prompt("json_system.jinja2")
        user = render_prompt(
            "component_gen_user.jinja2",
            spec_json=_json_for_prompt(spec),
            design_tokens_json=_json_for_prompt(design_tokens or {}),
            global_config_json=_json_for_prompt(global_config),
            revision_instruction=revision,
            component_name=name,
            component_name_lower=name.lower(),
        )

        merged: dict[str, Any]
        try:
            raw = await complete_json(system, user)
            if isinstance(raw, dict):
                merged = _merge_llm_component(
                    raw,
                    spec=spec,
                    design_tokens=design_tokens if isinstance(design_tokens, dict) else None,
                )
            else:
                merged = _fallback_component(
                    spec,
                    design_tokens=design_tokens if isinstance(design_tokens, dict) else None,
                )
        except Exception as exc:
            logger.warning(
                "component_gen LLM failed project_id=%s component_id=%s: %s",
                work.project_id,
                work.component_id,
                exc,
            )
            merged = _fallback_component(
                spec,
                design_tokens=design_tokens if isinstance(design_tokens, dict) else None,
            )

        try:
            validated = ComponentGeneratedPayload.model_validate(merged)
        except Exception as exc:
            logger.warning(
                "component_gen payload validation failed component_id=%s: %s",
                work.component_id,
                exc,
            )
            validated = ComponentGeneratedPayload.model_validate(
                _fallback_component(
                    spec,
                    design_tokens=design_tokens if isinstance(design_tokens, dict) else None,
                )
            )

        return build_result(
            work,
            event=PipelineEvent.COMPONENT_GENERATED,
            payload=validated.model_dump(),
            component_id=work.component_id,
        )
