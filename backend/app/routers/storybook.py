"""Storybook routes (Phase 1a–1c read, Phase 1b token writes)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_message_broker
from app.middleware.session_auth import get_current_user_id
from app.schemas.storybook import (
    ApplyTokensRequest,
    ApplyTokensResponse,
    ComponentDetailResponse,
    PatchTokensRequest,
    StorybookOverviewResponse,
    SuggestTokensRequest,
    SuggestTokensResponse,
    TokenPatchResponse,
)
from app.services.message_broker import MessageBroker
from app.services.project_access import get_project_for_user
from app.services.storybook_service import build_component_detail, build_storybook_overview
from app.services.storybook_tokens import (
    apply_design_tokens,
    patch_design_tokens,
    suggest_design_tokens,
)

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


@router.patch(
    "/{project_id}/storybook/tokens",
    response_model=TokenPatchResponse,
)
async def patch_storybook_tokens(
    project_id: int,
    body: PatchTokensRequest,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> TokenPatchResponse:
    project = await get_project_for_user(db, project_id, user_id)
    return await patch_design_tokens(db, project, body.design_tokens)


@router.post(
    "/{project_id}/storybook/tokens/suggest",
    response_model=SuggestTokensResponse,
)
async def suggest_storybook_tokens(
    project_id: int,
    body: SuggestTokensRequest,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> SuggestTokensResponse:
    project = await get_project_for_user(db, project_id, user_id)
    return await suggest_design_tokens(db, project, body.message)


@router.post(
    "/{project_id}/storybook/tokens/apply",
    response_model=ApplyTokensResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def apply_storybook_tokens(
    project_id: int,
    body: ApplyTokensRequest,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
    broker: MessageBroker = Depends(get_message_broker),
) -> ApplyTokensResponse:
    project = await get_project_for_user(db, project_id, user_id)
    return await apply_design_tokens(
        db,
        project,
        body.design_tokens,
        regenerate_components=body.regenerate_components,
        broker=broker,
    )
