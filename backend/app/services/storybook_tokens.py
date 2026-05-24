"""Storybook design token merge, validation, suggest, and apply (Phase 1b)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.design_schema import DesignSchema
from app.models.project import Project
from app.schemas.storybook import (
    ApplyTokensResponse,
    SuggestTokensResponse,
    TokenPatchResponse,
)
from app.services import sse_service
from app.services.design_data import components_for_project, latest_schema_for_project
from app.services.pipeline_state import register_storybook_batch
from app.services.storybook_publish import (
    TOKEN_REGEN_REVISION_INSTRUCTION,
    fanout_token_regeneration,
    resolve_latest_pipeline_run_id,
)
from pandora_shared.design_color import enrich_semantic_color_tokens
from pandora_shared.enums import ComponentStatus
from pandora_shared.sse_events import TOKEN_REGENERATION_STARTED
from pandora_shared.token_schema import EDITABLE_TOKEN_KEYS

_MAX_SUGGEST_MESSAGE_LEN = 4096
_HEX_COLOR_RE = re.compile(r"^#([0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$")
_CAMEL_BOUNDARY = re.compile(r"(?<!^)(?=[A-Z])")

_BUSY_COMPONENT_STATUSES = frozenset(
    {
        ComponentStatus.generating,
        ComponentStatus.validating,
        ComponentStatus.revised,
    }
)

_PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "token_suggest_system.txt"


def enriched_design_tokens(raw: dict[str, Any] | None) -> dict[str, Any]:
    return enrich_semantic_color_tokens(dict(raw or {}))


def _snake_to_camel(key: str) -> str:
    if "_" not in key:
        return key
    parts = key.split("_")
    return parts[0] + "".join(part.capitalize() for part in parts[1:])


def design_tokens_for_api(tokens: dict[str, Any]) -> dict[str, Any]:
    """CamelCase nested token keys for JSON (e.g. on_primary → onPrimary)."""
    out: dict[str, Any] = {}
    for key, value in tokens.items():
        api_key = _snake_to_camel(key)
        if isinstance(value, dict):
            out[api_key] = design_tokens_for_api(value)
        else:
            out[api_key] = value
    return out


def _camel_to_snake(key: str) -> str:
    if "_" in key:
        return key.lower()
    return _CAMEL_BOUNDARY.sub("_", key).lower()


def _normalize_patch_keys(patch: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in patch.items():
        if not isinstance(key, str):
            continue
        out[_camel_to_snake(key)] = value
    return out


def _validate_token_value(key: str, value: Any) -> None:
    if not isinstance(value, str) or not value.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Token '{key}' must be a non-empty string",
        )
    text = value.strip()
    if key in ("primary", "secondary", "accent", "surface", "text", "text_muted"):
        if not _HEX_COLOR_RE.match(text) and not text.startswith("rgb"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Token '{key}' must be a hex color or rgb() value",
            )
    if key == "radius" and not re.search(r"\d", text):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Token 'radius' must be a CSS length (e.g. 8px)",
        )


def validate_and_filter_patch(patch: dict[str, Any]) -> dict[str, Any]:
    """Keep only editable keys; reject unknown keys (400)."""
    normalized = _normalize_patch_keys(patch)
    unknown = [key for key in normalized if key not in EDITABLE_TOKEN_KEYS]
    if unknown:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown token keys: {', '.join(unknown)}",
        )
    filtered: dict[str, Any] = {}
    for key, value in normalized.items():
        _validate_token_value(key, value)
        filtered[key] = value.strip() if isinstance(value, str) else value
    return filtered


def merge_design_tokens(
    current: dict[str, Any] | None,
    patch: dict[str, Any],
) -> dict[str, Any]:
    base = dict(current or {})
    base.update(validate_and_filter_patch(patch))
    return enrich_semantic_color_tokens(base)


async def require_design_schema(
    session: AsyncSession,
    project_id: int,
) -> DesignSchema:
    schema = await latest_schema_for_project(session, project_id)
    if schema is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Design schema not found",
        )
    return schema


async def assert_storybook_idle(session: AsyncSession, project_id: int) -> None:
    components = await components_for_project(session, project_id)
    busy = [c.name for c in components if c.status in _BUSY_COMPONENT_STATUSES]
    if busy:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Library is busy; wait for in-flight work to finish",
        )


def _require_non_empty_patch(patch: dict[str, Any]) -> dict[str, Any]:
    filtered = validate_and_filter_patch(patch)
    if not filtered:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="designTokens must include at least one editable key",
        )
    return filtered


async def patch_design_tokens(
    session: AsyncSession,
    project: Project,
    patch: dict[str, Any],
) -> TokenPatchResponse:
    await assert_storybook_idle(session, project.id)
    schema = await require_design_schema(session, project.id)
    filtered = _require_non_empty_patch(patch)
    merged = merge_design_tokens(schema.design_tokens, filtered)
    schema.design_tokens = merged
    await session.commit()
    return TokenPatchResponse(design_tokens=design_tokens_for_api(merged))


def _token_suggest_system_prompt() -> str:
    return _PROMPT_PATH.read_text(encoding="utf-8")


def _suggest_user_prompt(
    *,
    design_tokens: dict[str, Any],
    global_config: dict[str, Any],
    message: str,
) -> str:
    return (
        f"Current design_tokens:\n{design_tokens}\n\n"
        f"Global config:\n{global_config}\n\n"
        f"User request:\n{message}"
    )


async def suggest_design_tokens(
    session: AsyncSession,
    project: Project,
    message: str,
) -> SuggestTokensResponse:
    await assert_storybook_idle(session, project.id)
    from app.services.openrouter_client import complete_json, llm_configured

    if not llm_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="LLM is not configured (OPENROUTER_API_KEY)",
        )
    text = message.strip()
    if not text:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="message is required",
        )
    if len(text) > _MAX_SUGGEST_MESSAGE_LEN:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"message must be at most {_MAX_SUGGEST_MESSAGE_LEN} characters",
        )

    schema = await require_design_schema(session, project.id)
    current = enriched_design_tokens(schema.design_tokens)
    global_config = dict(schema.global_config) if schema.global_config else {}

    raw = await complete_json(
        _token_suggest_system_prompt(),
        _suggest_user_prompt(
            design_tokens=current,
            global_config=global_config,
            message=text,
        ),
    )
    proposed_raw = raw.get("design_tokens") or raw.get("designTokens") or {}
    if not isinstance(proposed_raw, dict):
        proposed_raw = {}
    proposed = validate_and_filter_patch(proposed_raw)
    merged = merge_design_tokens(schema.design_tokens, proposed)
    explanation = raw.get("explanation")
    if not isinstance(explanation, str):
        explanation = "Updated tokens per your request."
    return SuggestTokensResponse(
        proposed_tokens=design_tokens_for_api(proposed),
        design_tokens=design_tokens_for_api(merged),
        explanation=explanation.strip(),
    )


async def apply_design_tokens(
    session: AsyncSession,
    project: Project,
    patch: dict[str, Any],
    *,
    regenerate_components: bool,
) -> ApplyTokensResponse:
    if regenerate_components:
        await assert_storybook_idle(session, project.id)

    schema = await require_design_schema(session, project.id)
    filtered = _require_non_empty_patch(patch)
    merged = merge_design_tokens(schema.design_tokens, filtered)
    schema.design_tokens = merged

    queued = 0
    pipeline_run_id: int | None = None
    if regenerate_components:
        pipeline_run_id = await resolve_latest_pipeline_run_id(session, project.id)
        queued = await fanout_token_regeneration(
            session,
            project_id=project.id,
            schema=schema,
            design_tokens=merged,
        )
        sse_service.emit(
            project.id,
            {
                "type": TOKEN_REGENERATION_STARTED,
                "projectId": project.id,
                "total": queued,
            },
        )

    await session.commit()

    if regenerate_components and queued > 0 and pipeline_run_id is not None:
        await register_storybook_batch(pipeline_run_id, queued)

    status_label = "token_apply_running" if regenerate_components and queued > 0 else "applied"
    return ApplyTokensResponse(
        design_tokens=design_tokens_for_api(merged),
        regenerate_queued=queued,
        status=status_label,
    )
