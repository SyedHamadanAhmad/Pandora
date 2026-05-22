"""RabbitMQ message envelope and idempotency helpers (Tech Spec §3b, §7.5)."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
from pydantic import BaseModel, Field

from pandora_shared.payloads import PARSE_SOURCES, ParseResultPayload, ParseSource

_PARSE_RESULTS_PREFIX = "pandora.parse.results:"


class PipelineEvent(StrEnum):
    """Canonical ``MessageEnvelope.event`` values."""

    PARSE_REQUEST = "pandora.parse.request"
    PARSE_RESULTS = "pandora.parse.results"
    BRIEF_REQUEST = "pandora.brief.request"
    BRIEF_READY = "pandora.brief.ready"
    SCHEMA_REQUEST = "pandora.schema.request"
    SCHEMA_READY = "pandora.schema.ready"
    COMPONENT_GENERATED = "pandora.component.generated"
    COMPONENT_VALIDATED = "pandora.component.validated"
    COMPONENT_FAILED = "pandora.component.failed"
    VERIFICATION_COMPLETE = "pandora.verification.complete"


# Backward-compatible aliases (prefer PipelineEvent in new code)
PARSE_REQUEST_EVENT = PipelineEvent.PARSE_REQUEST
PARSE_RESULTS_EVENT = PipelineEvent.PARSE_RESULTS
BRIEF_REQUEST_EVENT = PipelineEvent.BRIEF_REQUEST
BRIEF_READY_EVENT = PipelineEvent.BRIEF_READY
SCHEMA_REQUEST_EVENT = PipelineEvent.SCHEMA_REQUEST
SCHEMA_READY_EVENT = PipelineEvent.SCHEMA_READY


class Attempt(BaseModel):
    """Feedback retry pass + verification revision cycle."""

    retry_count: int = 0
    revision_round: int = 0


class MessageEnvelope(BaseModel):
    """Standard envelope for all agent and consumer messages."""

    event: str
    project_id: int
    pipeline_id: int
    component_id: int | None = None
    attempt: Attempt | None = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    payload: dict[str, Any] = Field(default_factory=dict)


def build_idempotency_key(
    pipeline_id: int,
    event: str,
    *,
    component_id: int | None = None,
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


def parse_results_idempotency_event(source: str) -> str:
    """Event segment for idempotency keys (includes parse source)."""
    if source not in PARSE_SOURCES:
        raise ValueError(f"Invalid parse source: {source}")
    return f"{_PARSE_RESULTS_PREFIX}{source}"


def parse_source_from_envelope(envelope: MessageEnvelope) -> ParseSource:
    """Resolve parse modality from ``event=pandora.parse.results`` and ``payload.source``."""
    if envelope.event != PipelineEvent.PARSE_RESULTS:
        raise ValueError(f"Expected event {PipelineEvent.PARSE_RESULTS}, got {envelope.event!r}")
    return ParseResultPayload.model_validate(envelope.payload).source
