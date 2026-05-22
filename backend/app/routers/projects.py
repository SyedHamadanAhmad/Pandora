"""Project CRUD routes (Tech Spec §8)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.session_auth import get_current_user_id
from app.models.component import Component
from app.models.project import Project
from app.models.showcase_scene import ShowcaseScene
from app.services.project_access import get_project_for_user
from app.schemas.component import ComponentListResponse
from app.schemas.project import (
    CreateProjectRequest,
    ProjectListResponse,
    ProjectResponse,
)
from app.schemas.component import ComponentResponse
from app.schemas.showcase import ShowcaseListResponse, ShowcaseSceneResponse
from pandora_shared.enums import ProjectStatus

router = APIRouter(prefix="/api/projects", tags=["projects"])


@router.post(
    "/",
    response_model=ProjectResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_project(
    body: CreateProjectRequest,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> ProjectResponse:
    project = Project(
        user_id=user_id,
        name=body.name,
        status=ProjectStatus.pending,
    )
    db.add(project)
    await db.commit()
    await db.refresh(project)
    return ProjectResponse.model_validate(project)


@router.get("/", response_model=ProjectListResponse)
async def list_projects(
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> ProjectListResponse:
    result = await db.execute(
        select(Project)
        .where(Project.user_id == user_id)
        .order_by(Project.created_at.desc())
    )
    projects = result.scalars().all()
    return ProjectListResponse(
        projects=[ProjectResponse.model_validate(p) for p in projects]
    )


@router.get("/{project_id}/components", response_model=ComponentListResponse)
async def list_components(
    project_id: int,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> ComponentListResponse:
    await get_project_for_user(db, project_id, user_id)
    result = await db.execute(
        select(Component)
        .where(Component.project_id == project_id)
        .order_by(Component.spec_index.asc())
    )
    components = result.scalars().all()
    return ComponentListResponse(
        components=[ComponentResponse.model_validate(c) for c in components]
    )


@router.get("/{project_id}/showcase", response_model=ShowcaseListResponse)
async def list_showcase_scenes(
    project_id: int,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> ShowcaseListResponse:
    await get_project_for_user(db, project_id, user_id)
    result = await db.execute(
        select(ShowcaseScene)
        .where(ShowcaseScene.project_id == project_id)
        .order_by(ShowcaseScene.scene_index.asc())
    )
    scenes = result.scalars().all()
    return ShowcaseListResponse(
        scenes=[ShowcaseSceneResponse.model_validate(s) for s in scenes]
    )


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(
    project_id: int,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> ProjectResponse:
    project = await get_project_for_user(db, project_id, user_id)
    return ProjectResponse.model_validate(project)
