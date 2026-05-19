"""Helpers to build result envelopes from work messages."""

from __future__ import annotations

from typing import Any

from pandora_shared.events import Attempt, MessageEnvelope


def build_result(
    work: MessageEnvelope,
    *,
    event: str,
    payload: dict[str, Any],
    component_id: int | None = None,
    attempt: Attempt | None = None,
) -> MessageEnvelope:
    return MessageEnvelope(
        event=event,
        project_id=work.project_id,
        pipeline_id=work.pipeline_id,
        component_id=component_id if component_id is not None else work.component_id,
        attempt=attempt if attempt is not None else work.attempt,
        payload=payload,
    )
