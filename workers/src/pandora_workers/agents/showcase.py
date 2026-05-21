"""Showcase agent — ``pandora.showcase.generate`` → ``pandora.showcase.ready``."""

from __future__ import annotations

import json
import logging
from typing import Any

from pandora_shared.events import MessageEnvelope, PipelineEvent
from pandora_shared.payloads import ShowcaseGenerateWorkPayload, ShowcaseReadyPayload
from pandora_shared.queues import SHOWCASE_GENERATE, SHOWCASE_READY
from pandora_shared.showcase_bundle import (
    build_fallback_scene_tsx,
    build_module_manifest,
    normalize_scene_entry,
    validate_scene_tsx,
)

from pandora_workers.base_agent import BaseAgent
from pandora_workers.envelopes import build_result
from pandora_workers.llm import complete_json
from pandora_workers.prompts.loader import render_prompt

logger = logging.getLogger(__name__)

_MAX_PROMPT_CHARS = 28_000
_MAX_SCENES = 3
_TSX_PREVIEW_CHARS = 1200


def _json_for_prompt(obj: Any, *, max_chars: int = _MAX_PROMPT_CHARS) -> str:
    raw = json.dumps(obj if obj is not None else {}, ensure_ascii=False, separators=(",", ":"))
    if len(raw) <= max_chars:
        return raw
    return raw[:max_chars] + '"…[truncated]"'


def _components_for_prompt(components: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Trim TSX in work payload so the LLM sees API shape without full file bodies."""
    out: list[dict[str, Any]] = []
    for comp in components:
        if not isinstance(comp, dict):
            continue
        row = dict(comp)
        tsx = row.get("tsx_code")
        if isinstance(tsx, str) and len(tsx) > _TSX_PREVIEW_CHARS:
            row["tsx_code"] = tsx[:_TSX_PREVIEW_CHARS] + "\n/* …truncated for prompt */"
        out.append(row)
    return out


def _manifest_for_work(work: dict[str, Any]) -> dict[str, Any]:
    raw = work.get("module_manifest")
    if isinstance(raw, dict) and raw.get("modules"):
        return raw
    return build_module_manifest(work.get("components") or [])


def _normalize_scene(
    raw: dict[str, Any],
    *,
    index: int,
    manifest: dict[str, Any],
) -> dict[str, Any]:
    name = str(raw.get("scene_name") or f"Scene {index + 1}").strip()[:120]
    tsx = raw.get("scene_tsx_code")
    if not isinstance(tsx, str) or not tsx.strip():
        used = raw.get("components_used") if isinstance(raw.get("components_used"), list) else []
        clean_used = [str(u).strip() for u in used if isinstance(u, str) and str(u).strip()]
        tsx = build_fallback_scene_tsx(manifest, clean_used)
    else:
        tsx = normalize_scene_entry(tsx.strip())
        errors = validate_scene_tsx(tsx, manifest)
        if errors:
            logger.warning("showcase scene %s failed lint: %s", index, "; ".join(errors))
            used = raw.get("components_used") if isinstance(raw.get("components_used"), list) else []
            clean_used = [str(u).strip() for u in used if isinstance(u, str) and str(u).strip()]
            tsx = build_fallback_scene_tsx(manifest, clean_used or None)

    css = raw.get("scene_css_code")
    if css is not None and not isinstance(css, str):
        css = str(css)
    used = raw.get("components_used")
    if not isinstance(used, list):
        used = []
    clean_used = [str(u).strip() for u in used if isinstance(u, str) and str(u).strip()][:20]

    variant_selections = raw.get("variant_selections")
    if not isinstance(variant_selections, dict):
        variant_selections = None
    else:
        variant_selections = {
            str(k): str(v)
            for k, v in variant_selections.items()
            if isinstance(k, str) and isinstance(v, str)
        } or None

    return {
        "scene_index": int(raw.get("scene_index", index)),
        "scene_name": name,
        "scene_tsx_code": tsx[:12_000],
        "scene_css_code": css.strip()[:8000] if isinstance(css, str) and css.strip() else None,
        "components_used": clean_used,
        "variant_selections": variant_selections,
        "entry_path": "/Showcase.tsx",
    }


def _fallback_showcase(work: dict[str, Any]) -> dict[str, Any]:
    manifest = _manifest_for_work(work)
    names = [
        str(c.get("name")).strip()
        for c in (work.get("components") or [])
        if isinstance(c, dict) and c.get("name")
    ]
    used = names[:8] or list(manifest.get("modules", {}).keys())[:8] or ["Component"]
    return {
        "scenes": [
            {
                "scene_index": 0,
                "scene_name": "Showcase",
                "scene_tsx_code": build_fallback_scene_tsx(manifest, used),
                "scene_css_code": (
                    ".pandora-showcase-fallback { padding: 48px; max-width: 960px; margin: 0 auto; "
                    "display: flex; flex-direction: column; gap: 24px; }"
                ),
                "components_used": used,
                "variant_selections": None,
                "entry_path": "/Showcase.tsx",
            }
        ]
    }


def _merge_showcase(llm: dict[str, Any], *, work: dict[str, Any]) -> dict[str, Any]:
    manifest = _manifest_for_work(work)
    raw_scenes = llm.get("scenes")
    normalized: list[dict[str, Any]] = []
    if isinstance(raw_scenes, list):
        for index, item in enumerate(raw_scenes):
            if isinstance(item, dict):
                normalized.append(_normalize_scene(item, index=index, manifest=manifest))
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
        manifest = _manifest_for_work(work_dict)

        system = render_prompt("design_system_lead_system.jinja2")
        user = render_prompt(
            "showcase_user.jinja2",
            design_tokens_json=_json_for_prompt(work_payload.design_tokens or {}),
            global_config_json=_json_for_prompt(work_payload.global_config or {}),
            module_manifest_json=_json_for_prompt(manifest),
            components_json=_json_for_prompt(_components_for_prompt(work_payload.components)),
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
