"""Shared design schema / component lookups for API and pipeline."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.component import Component
from app.models.design_schema import DesignSchema


def truncate_text(value: str | None, *, limit: int) -> str | None:
    if value is None:
        return None
    text = value.strip()
    if not text:
        return None
    if len(text) <= limit:
        return text
    return text[:limit] + "…[truncated]"


async def latest_schema_for_project(
    session: AsyncSession,
    project_id: int,
) -> DesignSchema | None:
    return await session.scalar(
        select(DesignSchema)
        .where(DesignSchema.project_id == project_id)
        .order_by(DesignSchema.id.desc())
        .limit(1)
    )


def spec_for_component(schema: DesignSchema | None, spec_index: int) -> dict[str, Any]:
    if schema is None or not schema.component_specs:
        return {}
    specs = schema.component_specs
    if 0 <= spec_index < len(specs) and isinstance(specs[spec_index], dict):
        return dict(specs[spec_index])
    return {}


async def components_for_project(
    session: AsyncSession,
    project_id: int,
) -> list[Component]:
    result = await session.execute(
        select(Component)
        .where(Component.project_id == project_id)
        .order_by(Component.spec_index.asc())
    )
    return list(result.scalars().all())
