"""Shared helpers for parse agents publishing ``pandora.parse.results``."""

from __future__ import annotations

from typing import Any

from pandora_shared.events import MessageEnvelope, PipelineEvent
from pandora_shared.payloads import ParseResultPayload, ParseSource
from pandora_shared.queues import PARSE_RESULTS

from pandora_workers.envelopes import build_result


def parse_result_envelope(
    work: MessageEnvelope,
    *,
    source: ParseSource,
    data: dict[str, Any] | None = None,
    error: str | None = None,
) -> MessageEnvelope:
    payload = ParseResultPayload(source=source, data=data, error=error)
    return build_result(
        work,
        event=PipelineEvent.PARSE_RESULTS,
        payload=payload.model_dump(),
    )


PARSE_RESULTS_QUEUE = PARSE_RESULTS
