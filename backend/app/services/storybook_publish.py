"""Publish storybook component regeneration work via transactional outbox."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.component import Component
from app.models.design_schema import DesignSchema
from app.models.thread_message import ThreadMessage
from app.services.design_data import spec_for_component
from app.services.outbox import enqueue_outbox
from pandora_shared.enums import ComponentStatus
from pandora_shared.events import Attempt, MessageEnvelope, build_idempotency_key
from pandora_shared.queues import COMPONENT_GENERATE

COMPONENT_GENERATE_EVENT = "pandora.component.generate"

TOKEN_REGEN_REVISION_INSTRUCTION = (
    "Regenerate using updated design tokens; preserve component API and variants."
)


async def resolve_latest_pipeline_run_id(session: AsyncSession, project_id: int) -> int:
    row = await session.scalar(
        select(ThreadMessage.pipeline_run_id)
        .where(
            ThreadMessage.project_id == project_id,
            ThreadMessage.pipeline_run_id.is_not(None),
        )
        .order_by(ThreadMessage.id.desc())
        .limit(1)
    )
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No pipeline_run_id on thread messages for this project",
        )
    return row


def build_component_generate_envelope(
    *,
    project_id: int,
    pipeline_id: int,
    component: Component,
    schema: DesignSchema,
    design_tokens: dict[str, Any] | None,
    global_config: dict[str, Any] | None,
    revision_instruction: str | None,
    revision_round: int,
    storybook_ad_hoc: bool = True,
) -> MessageEnvelope:
    spec = spec_for_component(schema, component.spec_index)
    payload: dict[str, Any] = {
        "spec": spec,
        "spec_index": component.spec_index,
        "design_tokens": design_tokens,
        "global_config": global_config,
        "revision_instruction": revision_instruction,
    }
    if storybook_ad_hoc:
        payload["storybook_ad_hoc"] = True
    return MessageEnvelope(
        event=COMPONENT_GENERATE_EVENT,
        project_id=project_id,
        pipeline_id=pipeline_id,
        component_id=component.id,
        attempt=Attempt(
            retry_count=component.retry_count,
            revision_round=revision_round,
        ),
        payload=payload,
    )


def storybook_generate_idempotency_key(envelope: MessageEnvelope) -> str:
    return build_idempotency_key(
        envelope.pipeline_id,
        COMPONENT_GENERATE_EVENT,
        component_id=envelope.component_id,
        attempt=envelope.attempt,
    )


async def fanout_token_regeneration(
    session: AsyncSession,
    *,
    project_id: int,
    schema: DesignSchema,
    design_tokens: dict[str, Any],
) -> int:
    """Enqueue component.generate for all validated components (token apply)."""
    pipeline_run_id = await resolve_latest_pipeline_run_id(session, project_id)
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
            pipeline_id=pipeline_run_id,
            component=component,
            schema=schema,
            design_tokens=design_tokens,
            global_config=global_config,
            revision_instruction=TOKEN_REGEN_REVISION_INSTRUCTION,
            revision_round=component.revision_round,
        )
        await enqueue_outbox(
            session,
            COMPONENT_GENERATE,
            envelope,
            project_id=project_id,
            idempotency_key=storybook_generate_idempotency_key(envelope),
        )

    await session.flush()
    return len(components)
