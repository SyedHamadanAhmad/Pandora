"""Storybook read routes (Phase 1a / 1c)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.session_auth import get_current_user_id
from app.schemas.storybook import ComponentDetailResponse, StorybookOverviewResponse
from app.services.project_access import get_project_for_user
from app.services.storybook_service import build_component_detail, build_storybook_overview

router = APIRouter(prefix="/api/projects", tags=["storybook"])


@router.get("/{project_id}/storybook", response_model=StorybookOverviewResponse)
async def get_storybook_overview(
    project_id: int,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> StorybookOverviewResponse:
    project = await get_project_for_user(db, project_id, user_id)
    return await build_storybook_overview(db, project)


@router.get(
    "/{project_id}/components/{component_id}",
    response_model=ComponentDetailResponse,
)
async def get_component_detail(
    project_id: int,
    component_id: int,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> ComponentDetailResponse:
    project = await get_project_for_user(db, project_id, user_id)
    return await build_component_detail(db, project, component_id)
