"""Per-component storybook revision (Phase 4)."""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.component import Component
from app.models.project import Project
from app.schemas.storybook import ReviseComponentResponse
from app.services import sse_service
from app.services.message_broker import MessageBroker
from app.services.storybook_publish import (
    build_component_generate_envelope,
    resolve_latest_pipeline_id,
)
from app.services.storybook_tokens import assert_storybook_idle, require_design_schema
from pandora_shared.enums import ComponentStatus
from pandora_shared.queues import COMPONENT_GENERATE

_MAX_REVISE_MESSAGE_LEN = 4096


async def revise_component(
    session: AsyncSession,
    project: Project,
    component_id: int,
    message: str,
    broker: MessageBroker,
) -> ReviseComponentResponse:
    await assert_storybook_idle(session, project.id)

    text = message.strip()
    if not text:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="message is required",
        )
    if len(text) > _MAX_REVISE_MESSAGE_LEN:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"message must be at most {_MAX_REVISE_MESSAGE_LEN} characters",
        )

    component = await session.get(Component, component_id)
    if component is None or component.project_id != project.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Component not found",
        )

    if component.status == ComponentStatus.generating:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Component is already being revised",
        )
    if component.status == ComponentStatus.validating:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Component is validating; wait before revising",
        )

    schema = await require_design_schema(session, project.id)
    pipeline_id = await resolve_latest_pipeline_id(session, project.id)

    component.revision_instruction = text
    component.status = ComponentStatus.generating
    component.revision_round = component.revision_round + 1

    envelope = build_component_generate_envelope(
        project_id=project.id,
        pipeline_id=pipeline_id,
        component=component,
        schema=schema,
        design_tokens=schema.design_tokens,
        global_config=schema.global_config if schema.global_config else {},
        revision_instruction=component.revision_instruction,
        revision_round=component.revision_round,
    )
    await broker.publish(COMPONENT_GENERATE, envelope)
    await session.commit()

    sse_service.emit(
        project.id,
        {
            "type": "component_revision_started",
            "projectId": project.id,
            "componentId": str(component.id),
            "componentName": component.name,
        },
    )

    return ReviseComponentResponse(
        component_id=component.id,
        status=ComponentStatus.generating,
    )
