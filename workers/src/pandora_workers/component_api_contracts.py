"""Per-type component API contracts for prompts, fallbacks, and validation."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ComponentApiContract:
    """Predictable props and usage for one component ``type``."""

    type_key: str
    required_props: tuple[str, ...]
    optional_props: tuple[str, ...]
    forbidden_patterns: tuple[str, ...]
    default_props: dict[str, Any]
    prompt_rules: tuple[str, ...]


_CONTRACTS: dict[str, ComponentApiContract] = {
    "button": ComponentApiContract(
        type_key="button",
        required_props=("label",),
        optional_props=("onClick", "variant", "disabled"),
        forbidden_patterns=(
            r"children\s*:\s*ReactNode",
            r"children\s*:\s*React\.ReactNode",
            r"children\s*\?",
            r"\{\s*children\s*\}",
        ),
        default_props={"label": "Continue", "variant": "primary"},
        prompt_rules=(
            "Props: `label: string` (required). Optional: `onClick?: () => void`, `variant`, `disabled`.",
            "Do NOT use `children` — label-only API, not composition.",
            "Render `<button type=\"button\" onClick={onClick}>{label}</button>`.",
            "Usage: `<Button label=\"Save\" onClick={() => {}} />` — pass `label` and `onClick`, not child nodes.",
        ),
    ),
    "card": ComponentApiContract(
        type_key="card",
        required_props=("title",),
        optional_props=("children",),
        forbidden_patterns=(r"title\?\s*:\s*string",),
        default_props={"title": "Card title", "children": "Card body content"},
        prompt_rules=(
            "Props: `title: string` (required). Optional: `children?: React.ReactNode` for body.",
            "Always render a visible header bound to `title`.",
            "Root: `<article>` — not `<button>`.",
        ),
    ),
    "badge": ComponentApiContract(
        type_key="badge",
        required_props=("text",),
        optional_props=("variant",),
        forbidden_patterns=(
            r"text\?\s*:\s*string",
            r"label\?\s*:\s*string",
        ),
        default_props={"text": "New", "variant": "default"},
        prompt_rules=(
            "Props: `text: string` (required). Optional: `variant`.",
            "Render badge copy from `text` — never an empty badge.",
            "Use `<span>` (or similar), not `<button>`.",
        ),
    ),
    "input": ComponentApiContract(
        type_key="input",
        required_props=("label",),
        optional_props=("placeholder", "error", "disabled"),
        forbidden_patterns=(r"label\?\s*:\s*string",),
        default_props={"label": "Label", "placeholder": "Enter text"},
        prompt_rules=(
            "Props: `label: string` (required). Optional: `placeholder`, `error`, `disabled`.",
            "Associate `<label htmlFor=...>` with `<input id=...>`.",
        ),
    ),
    "navigation": ComponentApiContract(
        type_key="navigation",
        required_props=("items",),
        optional_props=("activeIndex",),
        forbidden_patterns=(r"items\?\s*:\s*string\[\]",),
        default_props={"items": ["Home", "Products", "About"], "activeIndex": 0},
        prompt_rules=(
            "Props: `items: string[]` (required, non-empty). Optional: `activeIndex`.",
            "Use `<nav>` with list semantics.",
        ),
    ),
    "modal": ComponentApiContract(
        type_key="modal",
        required_props=("title",),
        optional_props=("children", "open"),
        forbidden_patterns=(r"title\?\s*:\s*string",),
        default_props={"title": "Dialog title", "children": "Dialog content", "open": True},
        prompt_rules=(
            "Props: `title: string` (required). Optional: `children`, `open`.",
            "Use dialog semantics (`role=\"dialog\"`, labelled title).",
        ),
    ),
    "hero": ComponentApiContract(
        type_key="hero",
        required_props=("title",),
        optional_props=("subtitle", "children"),
        forbidden_patterns=(r"title\?\s*:\s*string",),
        default_props={"title": "Hero headline", "subtitle": "Supporting line"},
        prompt_rules=(
            "Props: `title: string` (required). Optional: `subtitle`, `children`.",
            "Use `<section>` layout — not a button root.",
        ),
    ),
    "layout": ComponentApiContract(
        type_key="layout",
        required_props=("title",),
        optional_props=("children",),
        forbidden_patterns=(r"title\?\s*:\s*string",),
        default_props={"title": "Section", "children": None},
        prompt_rules=(
            "Props: `title: string` (required). Optional: `children`.",
            "Use semantic section layout.",
        ),
    ),
    # Generic type: no required props, use whatever makes sense for the component.
    # Unknown/exotic components (Dropdown, Toggle, Accordion, etc.) map here to avoid
    # the layout contract forcing an irrelevant `title: string`.
    "generic": ComponentApiContract(
        type_key="generic",
        required_props=(),
        optional_props=(),
        forbidden_patterns=(),
        default_props={},
        prompt_rules=(
            "No fixed required props — design the props that best fit the component's purpose.",
            "Use semantic HTML appropriate to the component type.",
            "Include variant classes in CSS for each variant in the spec.",
        ),
    ),
}


_KNOWN_TYPES = frozenset(
    {"button", "card", "badge", "input", "navigation", "modal", "hero", "layout", "generic"}
)


def infer_spec_type(spec: dict[str, Any]) -> str:
    """Resolve semantic type from spec ``type`` or component ``name``."""
    raw = spec.get("type")
    if isinstance(raw, str) and raw.strip():
        candidate = raw.strip().lower()
        # Return any recognised type as-is; unknown types become generic.
        return candidate if candidate in _KNOWN_TYPES else "generic"
    name = str(spec.get("name") or "").lower()
    if "button" in name or "cta" in name:
        return "button"
    if "badge" in name or "chip" in name or "tag" in name:
        return "badge"
    if "card" in name or "tile" in name:
        return "card"
    if "nav" in name or "menu" in name or "tab" in name:
        return "navigation"
    if "input" in name or "field" in name or "search" in name:
        return "input"
    if "modal" in name or "dialog" in name:
        return "modal"
    if "hero" in name or "banner" in name:
        return "hero"
    if "section" in name or "layout" in name or "page" in name or "container" in name:
        return "layout"
    # Everything else (Dropdown, Toggle, Accordion, DataTable, etc.) is generic.
    return "generic"


def contract_for_type(spec_type: str) -> ComponentApiContract:
    key = (spec_type or "layout").strip().lower()
    return _CONTRACTS.get(key, _CONTRACTS["layout"])


def default_props_for_type(spec_type: str) -> dict[str, Any]:
    return dict(contract_for_type(spec_type).default_props)


def prompt_context_for_type(spec_type: str) -> dict[str, str]:
    contract = contract_for_type(spec_type)
    return {
        "api_contract_rules": "\n".join(contract.prompt_rules),
        "required_props_list": ", ".join(contract.required_props) or "(none)",
        "optional_props_list": ", ".join(contract.optional_props) or "(none)",
    }


def check_api_contract(tsx_code: str, spec_type: str) -> list[str]:
    """Return violations; empty if TSX matches contract."""
    contract = contract_for_type(spec_type)
    errors: list[str] = []

    for prop in contract.required_props:
        if prop == "items":
            if not re.search(r"items\s*:\s*string\[\]", tsx_code):
                errors.append(f"{contract.type_key}: missing required `items: string[]`")
            if re.search(r"items\s*\?", tsx_code):
                errors.append(f"{contract.type_key}: `items` must be required, not optional")
        else:
            if not re.search(rf"{re.escape(prop)}\s*:\s*string", tsx_code):
                errors.append(f"{contract.type_key}: missing required `{prop}: string`")
            if re.search(rf"{re.escape(prop)}\s*\?\s*:", tsx_code):
                errors.append(f"{contract.type_key}: `{prop}` must be required, not optional")

    for pattern in contract.forbidden_patterns:
        if re.search(pattern, tsx_code):
            errors.append(f"{contract.type_key}: forbidden API pattern")

    if contract.type_key == "button":
        if not re.search(r"onClick\s*\??\s*:", tsx_code):
            errors.append(f"{contract.type_key}: missing `onClick` handler in props")
        if not re.search(r"onClick\s*=\s*\{", tsx_code):
            errors.append(f"{contract.type_key}: must wire `onClick` on `<button>`")

    return errors
