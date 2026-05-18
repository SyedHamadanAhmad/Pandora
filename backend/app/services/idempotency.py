"""Idempotency for the Pipeline Event Consumer (Tech Spec §3b)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from enum import Enum
from typing import TypeVar
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.processed_event import ProcessedEvent
from pandora_shared.events import (
    Attempt,
    MessageEnvelope,
    PipelineEvent,
    build_idempotency_key,
    parse_results_idempotency_event,
    parse_source_from_envelope,
)

T = TypeVar("T")


class IdempotencyStatus(str, Enum):
    """Whether a handler ran for this idempotency key."""

    APPLIED = "applied"
    DUPLICATE = "duplicate"


def idempotency_key_for_envelope(
    envelope: MessageEnvelope,
    *,
    event: str | None = None,
) -> str:
    """Build an idempotency key from a message envelope."""
    event_name = event or envelope.event
    if event_name == PipelineEvent.PARSE_RESULTS:
        source = parse_source_from_envelope(envelope)
        return parse_results_idempotency_key(envelope.pipeline_id, source)
    return build_idempotency_key(
        envelope.pipeline_id,
        event_name,
        component_id=envelope.component_id,
        attempt=envelope.attempt,
    )


def parse_results_idempotency_key(pipeline_id: UUID, source: str) -> str:
    """Idempotency key for a single parser result (text | image | url)."""
    return build_idempotency_key(pipeline_id, parse_results_idempotency_event(source))


async def run_idempotent(
    session: AsyncSession,
    *,
    idempotency_key: str,
    project_id: int,
    handler: Callable[[AsyncSession], Awaitable[T]],
) -> tuple[IdempotencyStatus, T | None]:
    """
    Claim an idempotency key and run ``handler`` in one transaction.

    - On first sight of ``idempotency_key``: insert ``processed_events``, run handler, commit.
    - On duplicate key: rollback and return ``DUPLICATE`` without calling handler.
    - On handler error: rollback (including the claim row) and re-raise.
    """
    session.add(
        ProcessedEvent(
            idempotency_key=idempotency_key,
            project_id=project_id,
        )
    )
    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        return IdempotencyStatus.DUPLICATE, None

    try:
        result = await handler(session)
        await session.commit()
        return IdempotencyStatus.APPLIED, result
    except Exception:
        await session.rollback()
        raise
