"""Storybook read-model builders (Phase 1a / 1c)."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.component import Component
from app.models.project import Project
from app.schemas.component import ComponentResponse
from app.schemas.storybook import (
    ComponentDetailResponse,
    ComponentSpecSummary,
    StorybookComponentSummary,
    StorybookOverviewResponse,
    StorybookSummary,
    TokenSchemaResponse,
)
from app.services.design_data import (
    components_for_project,
    latest_schema_for_project,
    schema_for_component,
    spec_for_component,
    truncate_text,
)
from app.services.storybook_tokens import design_tokens_for_api, enriched_design_tokens
from app.services.variant_normalize import variants_for_api
from pandora_shared.enums import ComponentStatus
from pandora_shared.token_schema import storybook_token_schema


def _summary_counts(components: list[Component]) -> StorybookSummary:
    counts: dict[ComponentStatus, int] = {status: 0 for status in ComponentStatus}
    for component in components:
        counts[component.status] = counts.get(component.status, 0) + 1
    return StorybookSummary(
        total=len(components),
        validated=counts.get(ComponentStatus.validated, 0),
        failed=counts.get(ComponentStatus.failed, 0),
        generating=counts.get(ComponentStatus.generating, 0),
        validating=counts.get(ComponentStatus.validating, 0),
        revised=counts.get(ComponentStatus.revised, 0),
    )


def _token_schema_response() -> TokenSchemaResponse:
    raw = storybook_token_schema()
    return TokenSchemaResponse.model_validate(raw)


def _component_spec_summaries(specs: list[dict[str, Any]] | None) -> list[ComponentSpecSummary]:
    if not specs:
        return []
    out: list[ComponentSpecSummary] = []
    for item in specs:
        if not isinstance(item, dict):
            continue
        variants = item.get("variants")
        if not isinstance(variants, list):
            variants = []
        out.append(
            ComponentSpecSummary(
                name=str(item.get("name") or ""),
                type=item.get("type") if isinstance(item.get("type"), str) else None,
                variants=[str(v) for v in variants],
                props=item.get("props"),
            )
        )
    return out


async def build_storybook_overview(
    session: AsyncSession,
    project: Project,
) -> StorybookOverviewResponse:
    schema = await latest_schema_for_project(session, project.id)
    components = await components_for_project(session, project.id)
    design_tokens = design_tokens_for_api(
        enriched_design_tokens(schema.design_tokens if schema else None)
    )
    global_config = dict(schema.global_config) if schema and schema.global_config else {}
    specs_raw = list(schema.component_specs) if schema and schema.component_specs else []

    summaries: list[StorybookComponentSummary] = []
    for component in components:
        tsx = component.tsx_code
        summaries.append(
            StorybookComponentSummary(
                id=component.id,
                name=component.name,
                status=component.status,
                spec_index=component.spec_index,
                variants=variants_for_api(component.variants),
                props=component.props,
                preview_available=bool(tsx and tsx.strip()),
                tsx_preview=truncate_text(tsx, limit=2000),
                css_preview=truncate_text(component.css_code, limit=1000),
                error_reason=component.error_reason,
            )
        )

    return StorybookOverviewResponse(
        project_id=project.id,
        project_status=project.status,
        design_tokens=design_tokens,
        token_schema=_token_schema_response(),
        global_config=global_config,
        component_specs=_component_spec_summaries(specs_raw),
        components=summaries,
        summary=_summary_counts(components),
    )


async def build_component_detail(
    session: AsyncSession,
    project: Project,
    component_id: int,
) -> ComponentDetailResponse:
    component = await session.get(Component, component_id)
    if component is None or component.project_id != project.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Component not found",
        )

    schema = await schema_for_component(session, component)
    if schema is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Design schema not found",
        )

    return ComponentDetailResponse(
        project_id=project.id,
        component=ComponentResponse.model_validate(component),
        spec=spec_for_component(schema, component.spec_index),
        design_tokens=design_tokens_for_api(enriched_design_tokens(schema.design_tokens)),
        global_config=dict(schema.global_config) if schema.global_config else {},
    )
