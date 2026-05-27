"""ComponentGen agent — ``pandora.component.generate`` → ``pandora.component.generated``."""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Callable
from typing import Any

from pandora_shared.design_color import contrasting_foreground
from pandora_shared.events import MessageEnvelope, PipelineEvent
from pandora_shared.payloads import (
    ComponentGenerateWorkPayload,
    ComponentGeneratedPayload,
)
from pandora_shared.queues import COMPONENT_GENERATED, COMPONENT_GENERATE

from pandora_workers.base_agent import BaseAgent
from pandora_workers.component_api_contracts import (
    check_api_contract,
    default_props_for_type,
    infer_spec_type,
    prompt_context_for_type,
)
from pandora_workers.envelopes import build_result
from pandora_workers.llm import complete_json
from pandora_workers.prompts.loader import render_prompt

logger = logging.getLogger(__name__)

_MAX_PROMPT_CHARS = 24_000
_MAX_TSX_CHARS = 32_000
_DEFAULT_PRIMARY = "#2563eb"
_DEFAULT_SPACING_UNIT = 4


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


def _typography_for_prompt(
    design_tokens: dict[str, Any] | None,
    global_config: dict[str, Any] | None,
) -> dict[str, Any]:
    tokens = design_tokens if isinstance(design_tokens, dict) else {}
    cfg = global_config if isinstance(global_config, dict) else {}
    typo = tokens.get("typography") or tokens.get("typography_scale") or cfg.get("typography_scale")
    return dict(typo) if isinstance(typo, dict) else {}


def _spacing_for_prompt(
    design_tokens: dict[str, Any] | None,
    global_config: dict[str, Any] | None,
) -> dict[str, Any]:
    tokens = design_tokens if isinstance(design_tokens, dict) else {}
    cfg = global_config if isinstance(global_config, dict) else {}
    spacing = tokens.get("spacing") or tokens.get("spacing_system") or cfg.get("spacing_system")
    return dict(spacing) if isinstance(spacing, dict) else {"unit": _DEFAULT_SPACING_UNIT}


def _spacing_unit_px(
    design_tokens: dict[str, Any] | None,
    global_config: dict[str, Any] | None,
) -> int:
    spacing = _spacing_for_prompt(design_tokens, global_config)
    unit = spacing.get("unit") or spacing.get("base_px")
    try:
        value = int(unit)
        return value if value > 0 else _DEFAULT_SPACING_UNIT
    except (TypeError, ValueError):
        return _DEFAULT_SPACING_UNIT


def _primary_color(design_tokens: dict[str, Any] | None) -> str:
    if isinstance(design_tokens, dict):
        raw = design_tokens.get("primary")
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
    return _DEFAULT_PRIMARY


def _on_primary_color(design_tokens: dict[str, Any] | None) -> str:
    if isinstance(design_tokens, dict):
        raw = design_tokens.get("on_primary")
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
    return contrasting_foreground(_primary_color(design_tokens))


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


def _variant_union(variants: list[str]) -> str:
    quoted = " | ".join(repr(v) for v in variants[:4])
    return quoted or "'default'"


def _fallback_button(
    name: str,
    *,
    spec: dict[str, Any],
    design_tokens: dict[str, Any] | None,
    global_config: dict[str, Any] | None,
) -> dict[str, Any]:
    lower = name.lower()
    primary = _primary_color(design_tokens)
    on_primary = _on_primary_color(design_tokens)
    unit = _spacing_unit_px(design_tokens, global_config)
    pad_v = unit * 2
    pad_h = unit * 4
    variants = _normalize_variants(spec, {})
    variant_union = _variant_union(variants)
    defaults = default_props_for_type("button")
    label_default = str(defaults.get("label") or "Continue")
    return {
        "tsx_code": (
            f"export type {name}Props = {{\n"
            f"  label: string;\n"
            f"  onClick?: () => void;\n"
            f"  variant?: {variant_union};\n"
            f"  disabled?: boolean;\n"
            f"}};\n\n"
            f"export function {name}({{\n"
            f"  label = '{label_default}',\n"
            f"  onClick,\n"
            f"  variant = '{variants[0]}',\n"
            f"  disabled,\n"
            f"}}: {name}Props) {{\n"
            f"  return (\n"
            f"    <button\n"
            f"      type=\"button\"\n"
            f"      className={{`pandora-{lower} pandora-{lower}--${{variant}}`}}\n"
            f"      disabled={{disabled}}\n"
            f"      onClick={{onClick}}\n"
            f"    >\n"
            f"      {{label}}\n"
            f"    </button>\n"
            f"  );\n"
            f"}}\n"
        ),
        "css_code": (
            f".pandora-{lower} {{\n"
            f"  padding: {pad_v}px {pad_h}px;\n"
            f"  background: var(--primary, {primary});\n"
            f"  color: var(--on-primary, {on_primary});\n"
            f"  border: none;\n"
            f"  border-radius: {unit}px;\n"
            f"  cursor: pointer;\n"
            f"  font-size: 14px;\n"
            f"}}\n"
            f".pandora-{lower}:focus-visible {{\n"
            f"  outline: 2px solid {primary};\n"
            f"  outline-offset: 2px;\n"
            f"}}\n"
            f".pandora-{lower}:disabled {{\n"
            f"  opacity: 0.5;\n"
            f"  cursor: not-allowed;\n"
            f"}}\n"
            f".pandora-{lower}--secondary {{\n"
            f"  background: transparent;\n"
            f"  color: {primary};\n"
            f"  border: 1px solid {primary};\n"
            f"}}\n"
        ),
        "props": {"label": label_default, "variant": variants[0]},
        "variants": variants,
    }


def _fallback_card(
    name: str,
    *,
    spec: dict[str, Any],
    design_tokens: dict[str, Any] | None,
    global_config: dict[str, Any] | None,
) -> dict[str, Any]:
    lower = name.lower()
    primary = _primary_color(design_tokens)
    unit = _spacing_unit_px(design_tokens, global_config)
    variants = _normalize_variants(spec, {})
    defaults = default_props_for_type("card")
    title_default = str(defaults.get("title") or "Card title")
    return {
        "tsx_code": (
            f"import type {{ ReactNode }} from 'react';\n\n"
            f"export type {name}Props = {{\n"
            f"  title: string;\n"
            f"  children?: ReactNode;\n"
            f"}};\n\n"
            f"export function {name}({{ title = '{title_default}', children }}: {name}Props) {{\n"
            f"  return (\n"
            f"    <article className=\"pandora-{lower}\">\n"
            f"      <header className=\"pandora-{lower}__header\">{{title}}</header>\n"
            f"      <div className=\"pandora-{lower}__body\">{{children ?? null}}</div>\n"
            f"    </article>\n"
            f"  );\n"
            f"}}\n"
        ),
        "css_code": (
            f".pandora-{lower} {{\n"
            f"  border: 1px solid #e2e8f0;\n"
            f"  border-radius: {unit * 2}px;\n"
            f"  background: #fff;\n"
            f"  overflow: hidden;\n"
            f"}}\n"
            f".pandora-{lower}__header {{\n"
            f"  padding: {unit * 3}px {unit * 4}px;\n"
            f"  font-weight: 600;\n"
            f"  font-size: 16px;\n"
            f"  border-bottom: 1px solid #e2e8f0;\n"
            f"  color: {primary};\n"
            f"}}\n"
            f".pandora-{lower}__body {{\n"
            f"  padding: {unit * 4}px;\n"
            f"  font-size: 14px;\n"
            f"  color: #334155;\n"
            f"}}\n"
        ),
        "props": {"title": title_default, "children": defaults.get("children")},
        "variants": variants,
    }


def _fallback_badge(
    name: str,
    *,
    spec: dict[str, Any],
    design_tokens: dict[str, Any] | None,
    global_config: dict[str, Any] | None,
) -> dict[str, Any]:
    lower = name.lower()
    primary = _primary_color(design_tokens)
    on_primary = _on_primary_color(design_tokens)
    unit = _spacing_unit_px(design_tokens, global_config)
    variants = _normalize_variants(spec, {})
    variant_union = _variant_union(variants)
    defaults = default_props_for_type("badge")
    text_default = str(defaults.get("text") or "New")
    return {
        "tsx_code": (
            f"export type {name}Props = {{\n"
            f"  text: string;\n"
            f"  variant?: {variant_union};\n"
            f"}};\n\n"
            f"export function {name}({{ text = '{text_default}', variant = '{variants[0]}' }}: {name}Props) {{\n"
            f"  return (\n"
            f"    <span className={{`pandora-{lower} pandora-{lower}--${{variant}}`}}>{{text}}</span>\n"
            f"  );\n"
            f"}}\n"
        ),
        "css_code": (
            f".pandora-{lower} {{\n"
            f"  display: inline-block;\n"
            f"  padding: {unit}px {unit * 2}px;\n"
            f"  font-size: 12px;\n"
            f"  font-weight: 600;\n"
            f"  border-radius: {unit * 2}px;\n"
            f"  background: var(--primary, {primary});\n"
            f"  color: var(--on-primary, {on_primary});\n"
            f"}}\n"
        ),
        "props": {"text": text_default, "variant": variants[0]},
        "variants": variants,
    }


def _fallback_nav(
    name: str,
    *,
    spec: dict[str, Any],
    design_tokens: dict[str, Any] | None,
    global_config: dict[str, Any] | None,
) -> dict[str, Any]:
    lower = name.lower()
    primary = _primary_color(design_tokens)
    unit = _spacing_unit_px(design_tokens, global_config)
    variants = _normalize_variants(spec, {})
    defaults = default_props_for_type("navigation")
    return {
        "tsx_code": (
            f"export type {name}Props = {{\n"
            f"  items: string[];\n"
            f"  activeIndex?: number;\n"
            f"}};\n\n"
            f"export function {name}({{ items = {defaults.get('items')!r}, activeIndex = 0 }}: {name}Props) {{\n"
            f"  return (\n"
            f"    <nav className=\"pandora-{lower}\" aria-label=\"Main\">\n"
            f"      <ul className=\"pandora-{lower}__list\">\n"
            f"        {{items.map((item, index) => (\n"
            f"          <li key={{item}}>\n"
            f"            <a\n"
            f"              href=\"#\"\n"
            f"              className={{index === activeIndex ? 'pandora-{lower}__link is-active' : 'pandora-{lower}__link'}}\n"
            f"            >\n"
            f"              {{item}}\n"
            f"            </a>\n"
            f"          </li>\n"
            f"        ))}}\n"
            f"      </ul>\n"
            f"    </nav>\n"
            f"  );\n"
            f"}}\n"
        ),
        "css_code": (
            f".pandora-{lower}__list {{\n"
            f"  display: flex;\n"
            f"  gap: {unit * 4}px;\n"
            f"  list-style: none;\n"
            f"  margin: 0;\n"
            f"  padding: {unit * 2}px {unit * 4}px;\n"
            f"}}\n"
            f".pandora-{lower}__link {{\n"
            f"  color: #64748b;\n"
            f"  text-decoration: none;\n"
            f"  font-size: 14px;\n"
            f"}}\n"
            f".pandora-{lower}__link.is-active {{\n"
            f"  color: {primary};\n"
            f"  font-weight: 600;\n"
            f"}}\n"
            f".pandora-{lower}__link:focus-visible {{\n"
            f"  outline: 2px solid {primary};\n"
            f"  outline-offset: 2px;\n"
            f"}}\n"
        ),
        "props": {
            "items": defaults.get("items"),
            "activeIndex": defaults.get("activeIndex", 0),
        },
        "variants": variants,
    }


def _fallback_input(
    name: str,
    *,
    spec: dict[str, Any],
    design_tokens: dict[str, Any] | None,
    global_config: dict[str, Any] | None,
) -> dict[str, Any]:
    lower = name.lower()
    primary = _primary_color(design_tokens)
    unit = _spacing_unit_px(design_tokens, global_config)
    variants = _normalize_variants(spec, {})
    defaults = default_props_for_type("input")
    return {
        "tsx_code": (
            f"export type {name}Props = {{\n"
            f"  label: string;\n"
            f"  placeholder?: string;\n"
            f"  error?: string;\n"
            f"}};\n\n"
            f"export function {name}({{ label = '{defaults.get('label')}', placeholder = 'Enter text', error }}: {name}Props) {{\n"
            f"  const inputId = 'pandora-{lower}-input';\n"
            f"  return (\n"
            f"    <div className=\"pandora-{lower}\">\n"
            f"      <label className=\"pandora-{lower}__label\" htmlFor={{inputId}}>{{label}}</label>\n"
            f"      <input id={{inputId}} className=\"pandora-{lower}__field\" placeholder={{placeholder}} />\n"
            f"      {{error ? <span className=\"pandora-{lower}__error\">{{error}}</span> : null}}\n"
            f"    </div>\n"
            f"  );\n"
            f"}}\n"
        ),
        "css_code": (
            f".pandora-{lower} {{ display: flex; flex-direction: column; gap: {unit}px; }}\n"
            f".pandora-{lower}__label {{ font-size: 14px; color: #334155; }}\n"
            f".pandora-{lower}__field {{\n"
            f"  padding: {unit * 2}px {unit * 3}px;\n"
            f"  border: 1px solid #cbd5e1;\n"
            f"  border-radius: {unit}px;\n"
            f"  font-size: 14px;\n"
            f"}}\n"
            f".pandora-{lower}__field:focus-visible {{\n"
            f"  outline: 2px solid {primary};\n"
            f"  border-color: {primary};\n"
            f"}}\n"
            f".pandora-{lower}__error {{ font-size: 12px; color: #dc2626; }}\n"
        ),
        "props": {
            "label": defaults.get("label"),
            "placeholder": defaults.get("placeholder"),
        },
        "variants": variants,
    }


def _fallback_layout(
    name: str,
    *,
    spec: dict[str, Any],
    design_tokens: dict[str, Any] | None,
    global_config: dict[str, Any] | None,
) -> dict[str, Any]:
    lower = name.lower()
    primary = _primary_color(design_tokens)
    unit = _spacing_unit_px(design_tokens, global_config)
    variants = _normalize_variants(spec, {})
    defaults = default_props_for_type("layout")
    title_default = str(defaults.get("title") or name)
    return {
        "tsx_code": (
            f"import type {{ ReactNode }} from 'react';\n\n"
            f"export type {name}Props = {{\n"
            f"  title: string;\n"
            f"  children?: ReactNode;\n"
            f"}};\n\n"
            f"export function {name}({{ title = '{title_default}', children }}: {name}Props) {{\n"
            f"  return (\n"
            f"    <section className=\"pandora-{lower}\">\n"
            f"      <h2 className=\"pandora-{lower}__title\">{{title}}</h2>\n"
            f"      <div className=\"pandora-{lower}__content\">{{children ?? null}}</div>\n"
            f"    </section>\n"
            f"  );\n"
            f"}}\n"
        ),
        "css_code": (
            f".pandora-{lower} {{\n"
            f"  padding: {unit * 6}px {unit * 4}px;\n"
            f"}}\n"
            f".pandora-{lower}__title {{\n"
            f"  margin: 0 0 {unit * 3}px;\n"
            f"  font-size: 24px;\n"
            f"  color: {primary};\n"
            f"}}\n"
            f".pandora-{lower}__content {{\n"
            f"  font-size: 14px;\n"
            f"  color: #334155;\n"
            f"}}\n"
        ),
        "props": {"title": title_default},
        "variants": variants,
    }


_FALLBACK_BY_TYPE: dict[str, Callable[..., dict[str, Any]]] = {
    "button": _fallback_button,
    "card": _fallback_card,
    "badge": _fallback_badge,
    "navigation": _fallback_nav,
    "input": _fallback_input,
    "modal": _fallback_layout,
    "hero": _fallback_layout,
    "layout": _fallback_layout,
    "generic": _fallback_layout,
}


def _attach_spec_type(payload: dict[str, Any], spec: dict[str, Any]) -> dict[str, Any]:
    out = dict(payload)
    out["spec_type"] = infer_spec_type(spec)
    return out


def _fallback_component(
    spec: dict[str, Any],
    *,
    design_tokens: dict[str, Any] | None,
    global_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    name = _safe_component_name(spec.get("name"))
    typ = infer_spec_type(spec)
    factory = _FALLBACK_BY_TYPE.get(typ, _fallback_layout)
    return _attach_spec_type(
        factory(
            name,
            spec=spec,
            design_tokens=design_tokens,
            global_config=global_config,
        ),
        spec,
    )


def _merge_llm_component(
    llm: dict[str, Any],
    *,
    spec: dict[str, Any],
    design_tokens: dict[str, Any] | None,
    global_config: dict[str, Any] | None,
) -> dict[str, Any]:
    name = _safe_component_name(spec.get("name"))
    tsx = llm.get("tsx_code")
    if not isinstance(tsx, str) or not tsx.strip():
        return _fallback_component(
            spec,
            design_tokens=design_tokens,
            global_config=global_config,
        )
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

    return _attach_spec_type(
        {
            "tsx_code": tsx,
            "css_code": css,
            "props": props,
            "variants": _normalize_variants(spec, llm),
        },
        spec,
    )


def _ensure_api_contract(
    merged: dict[str, Any],
    *,
    spec: dict[str, Any],
    design_tokens: dict[str, Any] | None,
    global_config: dict[str, Any] | None,
) -> dict[str, Any]:
    """Replace output with type fallback when TSX violates API contract."""
    spec_type = infer_spec_type(spec)
    tsx = merged.get("tsx_code")
    if not isinstance(tsx, str):
        return _fallback_component(
            spec,
            design_tokens=design_tokens,
            global_config=global_config,
        )
    violations = check_api_contract(tsx, spec_type)
    if violations:
        logger.warning(
            "component_gen api contract failed type=%s name=%s: %s",
            spec_type,
            spec.get("name"),
            "; ".join(violations[:3]),
        )
        return _fallback_component(
            spec,
            design_tokens=design_tokens,
            global_config=global_config,
        )
    return merged


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
        spec_type = infer_spec_type(spec)
        tokens_dict = design_tokens if isinstance(design_tokens, dict) else None
        api_ctx = prompt_context_for_type(spec_type)

        # Attach variant style hints to the spec JSON sent to the prompt so the
        # LLM can read them in context alongside the variant list.
        spec_for_prompt = dict(spec)
        style_hints: dict[str, str] = {}
        if isinstance(spec.get("variant_style_hints"), dict):
            style_hints = spec["variant_style_hints"]
        if style_hints:
            spec_for_prompt["variant_style_hints"] = style_hints

        system = render_prompt("component_engineer_system.jinja2")
        user = render_prompt(
            "component_gen_user.jinja2",
            spec_json=_json_for_prompt(spec_for_prompt),
            design_tokens_json=_json_for_prompt(design_tokens or {}),
            typography_json=_json_for_prompt(_typography_for_prompt(tokens_dict, global_config)),
            spacing_json=_json_for_prompt(_spacing_for_prompt(tokens_dict, global_config)),
            global_config_json=_json_for_prompt(global_config),
            revision_instruction=revision,
            component_name=name,
            component_name_lower=name.lower(),
            spec_type=spec_type,
            api_contract_rules=api_ctx["api_contract_rules"],
            required_props_list=api_ctx["required_props_list"],
            optional_props_list=api_ctx["optional_props_list"],
        )

        merged: dict[str, Any]
        try:
            raw = await complete_json(system, user)
            if isinstance(raw, dict):
                merged = _merge_llm_component(
                    raw,
                    spec=spec,
                    design_tokens=tokens_dict,
                    global_config=global_config,
                )
            else:
                merged = _fallback_component(
                    spec,
                    design_tokens=tokens_dict,
                    global_config=global_config,
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
                design_tokens=tokens_dict,
                global_config=global_config,
            )

        try:
            merged = _ensure_api_contract(
                merged,
                spec=spec,
                design_tokens=tokens_dict,
                global_config=global_config,
            )
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
                    design_tokens=tokens_dict,
                    global_config=global_config,
                )
            )

        return build_result(
            work,
            event=PipelineEvent.COMPONENT_GENERATED,
            payload=validated.model_dump(),
            component_id=work.component_id,
        )
