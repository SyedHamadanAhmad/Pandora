"""Thread message routes — multipart input (Tech Spec §8, §10)."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.session_auth import get_current_user_id
from app.models.thread_message import ThreadMessage
from app.services.project_access import get_project_for_user
from app.schemas.thread import (
    CreateThreadResponse,
    ThreadListResponse,
    ThreadMessageResponse,
)
from app.services.pipeline_service import trigger_pipeline_run
from app.services.storage_service import (
    StorageValidationError,
    upload_thread_image,
    validate_image_count,
)
from app.services.url_validation import assert_safe_http_url
from pandora_shared.enums import MessageRole, ProjectStatus

MAX_REFERENCE_URLS = 3

router = APIRouter(
    prefix="/api/projects/{project_id}/thread",
    tags=["thread"],
)


def _parse_urls_field(urls: str | None) -> list[str] | None:
    if urls is None or not urls.strip():
        return None
    try:
        parsed = json.loads(urls)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="urls must be a JSON array of strings",
        ) from exc
    if not isinstance(parsed, list) or not all(isinstance(item, str) for item in parsed):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="urls must be a JSON array of strings",
        )
    return parsed


@router.post(
    "/",
    response_model=CreateThreadResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_thread_message(
    project_id: int,
    content: str | None = Form(default=None),
    urls: str | None = Form(default=None),
    images: list[UploadFile] = File(default=[]),
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> CreateThreadResponse:
    project = await get_project_for_user(db, project_id, user_id)

    if project.status == ProjectStatus.running:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Pipeline already running for this project",
        )
    if project.status == ProjectStatus.completed:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Project already has a design library; create a new project to re-run",
        )

    input_urls = _parse_urls_field(urls)
    image_files = images or []

    if input_urls is not None and len(input_urls) > MAX_REFERENCE_URLS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"At most {MAX_REFERENCE_URLS} reference URLs allowed",
        )

    if input_urls:
        for url in input_urls:
            try:
                assert_safe_http_url(url)
            except ValueError as exc:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=str(exc),
                ) from exc

    try:
        validate_image_count(image_files)
    except StorageValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    has_content = bool(content and content.strip())
    has_urls = bool(input_urls)
    has_images = len(image_files) > 0
    if not (has_content or has_urls or has_images):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one of content, urls, or images is required",
        )

    message = ThreadMessage(
        project_id=project_id,
        user_id=user_id,
        role=MessageRole.user,
        content=content.strip() if has_content else None,
        input_urls=input_urls,
    )
    db.add(message)
    await db.flush()

    image_urls: list[str] = []
    for image in image_files:
        try:
            url = await upload_thread_image(project_id, message.id, image)
        except StorageValidationError as exc:
            await db.rollback()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(exc),
            ) from exc
        image_urls.append(url)

    if image_urls:
        message.input_image_urls = image_urls

    trigger = await trigger_pipeline_run(db, project, message)

    return CreateThreadResponse(
        message_id=message.id,
        created_at=message.created_at,
        pipeline_id=trigger.pipeline_id,
        status=trigger.status,
    )


@router.get("/", response_model=ThreadListResponse)
async def list_thread_messages(
    project_id: int,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> ThreadListResponse:
    await get_project_for_user(db, project_id, user_id)

    result = await db.execute(
        select(ThreadMessage)
        .where(ThreadMessage.project_id == project_id)
        .order_by(ThreadMessage.created_at.asc())
    )
    messages = result.scalars().all()
    return ThreadListResponse(
        messages=[ThreadMessageResponse.model_validate(m) for m in messages]
    )
