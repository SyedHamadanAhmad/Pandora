"""Project CRUD routes (Tech Spec §8)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.session_auth import get_current_user_id
from app.models.project import Project
from app.schemas.component import ComponentListResponse
from app.schemas.project import (
    CreateProjectRequest,
    ProjectListResponse,
    ProjectResponse,
)
from app.schemas.showcase import ShowcaseListResponse
from pandora_shared.enums import ProjectStatus

router = APIRouter(prefix="/api/projects", tags=["projects"])


async def _get_project_for_user(
    db: AsyncSession,
    project_id: int,
    user_id: int,
) -> Project:
    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )
    if project.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden",
        )
    return project


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
    await _get_project_for_user(db, project_id, user_id)
    return ComponentListResponse(components=[])


@router.get("/{project_id}/showcase", response_model=ShowcaseListResponse)
async def list_showcase_scenes(
    project_id: int,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> ShowcaseListResponse:
    await _get_project_for_user(db, project_id, user_id)
    return ShowcaseListResponse(scenes=[])


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(
    project_id: int,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> ProjectResponse:
    project = await _get_project_for_user(db, project_id, user_id)
    return ProjectResponse.model_validate(project)
