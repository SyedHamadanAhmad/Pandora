"""Feedback agent — ``pandora.component.generated`` → validated | failed."""

from __future__ import annotations

import logging
import os

from pandora_shared.events import MessageEnvelope, PipelineEvent
from pandora_shared.payloads import (
    ComponentFailedPayload,
    ComponentGeneratedPayload,
    ComponentValidatedPayload,
)
from pandora_shared.queues import (
    COMPONENT_FAILED,
    COMPONENT_GENERATED,
    COMPONENT_VALIDATED,
)

from aio_pika.abc import AbstractChannel, AbstractIncomingMessage

from pandora_workers.base_agent import BaseAgent
from pandora_workers.envelopes import build_result
from pandora_workers.runtime import decode_envelope, publish
from pandora_workers.validation.feedback import run_tsc_and_eslint

logger = logging.getLogger(__name__)


def _skip_validation() -> bool:
    return os.environ.get("FEEDBACK_SKIP_VALIDATION", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _log_feedback(
    work: MessageEnvelope,
    *,
    ok: bool,
    errors: list[str],
    skipped: bool,
) -> None:
    """Emit human-readable feedback to worker logs (docker compose logs worker-feedback)."""
    cid = work.component_id
    pid = work.project_id
    if skipped:
        logger.info(
            "feedback SKIP validation → validated | project_id=%s component_id=%s",
            pid,
            cid,
        )
        return
    if ok:
        logger.info(
            "feedback PASS (tsc OK) → validated | project_id=%s component_id=%s",
            pid,
            cid,
        )
        return
    logger.warning(
        "feedback FAIL → component.failed | project_id=%s component_id=%s (%s issue(s))",
        pid,
        cid,
        len(errors),
    )
    for index, err in enumerate(errors, start=1):
        snippet = err if len(err) <= 4000 else err[:4000] + "\n…[truncated]"
        logger.warning(
            "feedback detail [%s/%s] component_id=%s:\n%s",
            index,
            len(errors),
            cid,
            snippet,
        )


class FeedbackAgent(BaseAgent):
    work_queue = COMPONENT_GENERATED
    result_queue = COMPONENT_VALIDATED

    async def handle_message(
        self,
        message: AbstractIncomingMessage,
        channel: AbstractChannel,
    ) -> None:
        try:
            work = decode_envelope(message.body)
            result = await self.handle_work(work)
            out_queue = (
                COMPONENT_VALIDATED
                if result.event == PipelineEvent.COMPONENT_VALIDATED
                else COMPONENT_FAILED
            )
            await publish(channel, out_queue, result)
            await message.ack()
            logger.info(
                "agent ok work=%s result=%s project_id=%s component_id=%s",
                self.work_queue,
                out_queue,
                work.project_id,
                work.component_id,
            )
        except Exception:
            logger.exception("agent failed queue=%s", self.work_queue)
            await message.nack(requeue=True)

    async def handle_work(self, work: MessageEnvelope) -> MessageEnvelope:
        if work.component_id is None:
            raise ValueError("component.generated missing component_id")

        generated = ComponentGeneratedPayload.model_validate(work.payload)
        skipped = _skip_validation()

        if skipped:
            ok, errors = True, []
        else:
            ok, errors = await run_tsc_and_eslint(
                generated.tsx_code,
                generated.css_code,
            )

        _log_feedback(work, ok=ok, errors=errors, skipped=skipped)

        if ok:
            validated = ComponentValidatedPayload.model_validate(generated.model_dump())
            return build_result(
                work,
                event=PipelineEvent.COMPONENT_VALIDATED,
                payload=validated.model_dump(),
                component_id=work.component_id,
            )

        reason = "; ".join(errors[:3]) if errors else "validation failed"
        failed = ComponentFailedPayload(error_reason=reason[:2000])
        return build_result(
            work,
            event=PipelineEvent.COMPONENT_FAILED,
            payload=failed.model_dump(),
            component_id=work.component_id,
        )
