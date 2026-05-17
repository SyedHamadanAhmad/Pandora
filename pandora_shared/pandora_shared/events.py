"""RabbitMQ message envelope and idempotency helpers (Tech Spec v1.7 §3b, §7.5)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class Attempt(BaseModel):
    """Feedback retry pass + verification revision cycle."""

    retry_count: int = 0
    revision_round: int = 0


class MessageEnvelope(BaseModel):
    """Standard envelope for all agent and consumer messages."""

    event: str
    project_id: int
    pipeline_id: UUID
    component_id: UUID | None = None
    attempt: Attempt | None = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    payload: dict[str, Any] = Field(default_factory=dict)


def build_idempotency_key(
    pipeline_id: UUID,
    event: str,
    *,
    component_id: UUID | None = None,
    attempt: Attempt | None = None,
) -> str:
    """
    Build idempotency key per Tech Spec §3b.1.

    Examples:
        {pipeline_id}:pandora.brief.ready
        {pipeline_id}:pandora.parse.results:text
        {pipeline_id}:pandora.component.validated:{component_id}:0.1
    """
    key = f"{pipeline_id}:{event}"
    if component_id is not None:
        key = f"{key}:{component_id}"
        if attempt is not None:
            key = f"{key}:{attempt.retry_count}.{attempt.revision_round}"
    return key


def parse_results_event(source: str) -> str:
    """Event name for a parser result (text | image | url)."""
    return f"pandora.parse.results:{source}"


# Work vs result event names (queue routing uses pandora_shared.queues constants)
PARSE_REQUEST_EVENT = "pandora.parse.request"
BRIEF_REQUEST_EVENT = "pandora.brief.request"
BRIEF_READY_EVENT = "pandora.brief.ready"
SCHEMA_REQUEST_EVENT = "pandora.schema.request"
SCHEMA_READY_EVENT = "pandora.schema.ready"
