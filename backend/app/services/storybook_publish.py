"""Publish storybook component regeneration work to RabbitMQ."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.component import Component
from app.models.design_schema import DesignSchema
from app.models.thread_message import ThreadMessage
from app.services.design_data import spec_for_component
from app.services.message_broker import MessageBroker
from pandora_shared.enums import ComponentStatus
from pandora_shared.events import Attempt, MessageEnvelope
from pandora_shared.queues import COMPONENT_GENERATE

COMPONENT_GENERATE_EVENT = "pandora.component.generate"

TOKEN_REGEN_REVISION_INSTRUCTION = (
    "Regenerate using updated design tokens; preserve component API and variants."
)


async def resolve_latest_pipeline_id(session: AsyncSession, project_id: int) -> UUID:
    row = await session.scalar(
        select(ThreadMessage.pipeline_id)
        .where(
            ThreadMessage.project_id == project_id,
            ThreadMessage.pipeline_id.is_not(None),
        )
        .order_by(ThreadMessage.id.desc())
        .limit(1)
    )
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No pipeline_id on thread messages for this project",
        )
    return row


def build_component_generate_envelope(
    *,
    project_id: int,
    pipeline_id: UUID,
    component: Component,
    schema: DesignSchema,
    design_tokens: dict[str, Any] | None,
    global_config: dict[str, Any] | None,
    revision_instruction: str | None,
    revision_round: int,
) -> MessageEnvelope:
    spec = spec_for_component(schema, component.spec_index)
    return MessageEnvelope(
        event=COMPONENT_GENERATE_EVENT,
        project_id=project_id,
        pipeline_id=pipeline_id,
        component_id=component.id,
        attempt=Attempt(
            retry_count=component.retry_count,
            revision_round=revision_round,
        ),
        payload={
            "spec": spec,
            "spec_index": component.spec_index,
            "design_tokens": design_tokens,
            "global_config": global_config,
            "revision_instruction": revision_instruction,
            "storybook_ad_hoc": True,
        },
    )


async def fanout_token_regeneration(
    session: AsyncSession,
    *,
    project_id: int,
    schema: DesignSchema,
    broker: MessageBroker,
    design_tokens: dict[str, Any],
) -> int:
    """Re-queue component.generate for all validated components (token apply)."""
    pipeline_id = await resolve_latest_pipeline_id(session, project_id)
    result = await session.execute(
        select(Component)
        .where(
            Component.project_id == project_id,
            Component.status == ComponentStatus.validated,
        )
        .order_by(Component.spec_index.asc())
    )
    components = list(result.scalars().all())
    if not components:
        return 0

    global_config = schema.global_config if schema.global_config else {}
    for component in components:
        component.status = ComponentStatus.generating
        component.revision_instruction = TOKEN_REGEN_REVISION_INSTRUCTION
        component.revision_round = component.revision_round + 1
        envelope = build_component_generate_envelope(
            project_id=project_id,
            pipeline_id=pipeline_id,
            component=component,
            schema=schema,
            design_tokens=design_tokens,
            global_config=global_config,
            revision_instruction=TOKEN_REGEN_REVISION_INSTRUCTION,
            revision_round=component.revision_round,
        )
        await broker.publish(COMPONENT_GENERATE, envelope)

    await session.flush()
    return len(components)
