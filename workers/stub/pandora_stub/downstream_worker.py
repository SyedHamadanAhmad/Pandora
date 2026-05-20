"""Stub downstream agents — brief, schema, component, verification, showcase."""

from __future__ import annotations

import asyncio
import os

from aio_pika.abc import AbstractChannel, AbstractIncomingMessage

from pandora_shared.events import Attempt, MessageEnvelope, PipelineEvent
from pandora_shared.queues import (
    BRIEF_READY,
    BRIEF_REQUEST,
    COMPONENT_GENERATE,
    COMPONENT_VALIDATED,
    SCHEMA_READY,
    SCHEMA_REQUEST,
    SHOWCASE_GENERATE,
    SHOWCASE_READY,
    VERIFICATION_COMPLETE,
    VERIFICATION_START,
)

from pandora_stub.runtime import (
    configure_logging,
    connect,
    declare_topology,
    decode_envelope,
    publish,
    run_consumers,
)

logger = __import__("logging").getLogger(__name__)

COMPONENT_GENERATE_EVENT = "pandora.component.generate"
SHOWCASE_GENERATE_EVENT = "pandora.showcase.generate"


def _brief_ready_payload(work: MessageEnvelope) -> dict:
    merged = work.payload
    return {
        "color_tokens": {"primary": "#2563eb", "secondary": "#64748b"},
        "typography_scale": {"base": "16px", "heading": "24px"},
        "spacing_system": {"unit": 4},
        "design_flavour": "modern-saas",
        "tone": "professional",
        "component_list": ["Button", "Card"],
        "input_gaps": merged.get("input_gaps") or [],
    }


def _schema_ready_payload(_work: MessageEnvelope) -> dict:
    return {
        "design_tokens": {"primary": "#2563eb", "radius": "8px"},
        "global_config": {"theme": "light"},
        "component_specs": [
            {"name": "Button", "type": "button", "variants": ["primary", "secondary"]},
            {"name": "Card", "type": "card", "layout": "vertical"},
        ],
    }


def _component_validated_payload(work: MessageEnvelope) -> dict:
    spec = work.payload.get("spec") or {}
    name = spec.get("name") or "Component"
    return {
        "tsx_code": f"export function {name}() {{ return <button className='stub'>Stub</button>; }}",
        "css_code": ".stub { padding: 8px 16px; }",
        "props": {"label": "Click me"},
        "variants": spec.get("variants") or ["default"],
    }


def _verification_complete_payload(_work: MessageEnvelope) -> dict:
    return {"issues": [], "approved": True}


def _showcase_ready_payload(_work: MessageEnvelope) -> dict:
    return {
        "scenes": [
            {
                "scene_index": 0,
                "scene_name": "Hero",
                "scene_tsx_code": "<motion.div className='hero'>Stub showcase</motion.div>",
                "scene_css_code": ".hero { min-height: 100vh; }",
                "components_used": ["Button", "Card"],
            }
        ]
    }


async def _handle_brief_request(message: AbstractIncomingMessage, channel: AbstractChannel) -> None:
    work = decode_envelope(message.body)
    result = MessageEnvelope(
        event=PipelineEvent.BRIEF_READY,
        project_id=work.project_id,
        pipeline_id=work.pipeline_id,
        payload=_brief_ready_payload(work),
    )
    await publish(channel, BRIEF_READY, result)
    await message.ack()
    logger.info("stub brief.ready project_id=%s", work.project_id)


async def _handle_schema_request(message: AbstractIncomingMessage, channel: AbstractChannel) -> None:
    work = decode_envelope(message.body)
    result = MessageEnvelope(
        event=PipelineEvent.SCHEMA_READY,
        project_id=work.project_id,
        pipeline_id=work.pipeline_id,
        payload=_schema_ready_payload(work),
    )
    await publish(channel, SCHEMA_READY, result)
    await message.ack()
    logger.info("stub schema.ready project_id=%s", work.project_id)


async def _handle_component_generate(
    message: AbstractIncomingMessage,
    channel: AbstractChannel,
) -> None:
    work = decode_envelope(message.body)
    if work.component_id is None:
        await message.nack(requeue=False)
        return
    result = MessageEnvelope(
        event=PipelineEvent.COMPONENT_VALIDATED,
        project_id=work.project_id,
        pipeline_id=work.pipeline_id,
        component_id=work.component_id,
        attempt=work.attempt or Attempt(retry_count=0, revision_round=0),
        payload=_component_validated_payload(work),
    )
    await publish(channel, COMPONENT_VALIDATED, result)
    await message.ack()
    logger.info(
        "stub component.validated project_id=%s component_id=%s",
        work.project_id,
        work.component_id,
    )


async def _handle_verification_start(
    message: AbstractIncomingMessage,
    channel: AbstractChannel,
) -> None:
    work = decode_envelope(message.body)
    result = MessageEnvelope(
        event=PipelineEvent.VERIFICATION_COMPLETE,
        project_id=work.project_id,
        pipeline_id=work.pipeline_id,
        payload=_verification_complete_payload(work),
    )
    await publish(channel, VERIFICATION_COMPLETE, result)
    await message.ack()
    logger.info("stub verification.complete project_id=%s", work.project_id)


async def _handle_showcase_generate(
    message: AbstractIncomingMessage,
    channel: AbstractChannel,
) -> None:
    work = decode_envelope(message.body)
    result = MessageEnvelope(
        event=PipelineEvent.SHOWCASE_READY,
        project_id=work.project_id,
        pipeline_id=work.pipeline_id,
        payload=_showcase_ready_payload(work),
    )
    await publish(channel, SHOWCASE_READY, result)
    await message.ack()
    logger.info("stub showcase.ready project_id=%s", work.project_id)


def _truthy_env(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


async def main() -> None:
    configure_logging("pandora_stub.downstream")
    connection = await connect()
    declare_channel = await connection.channel()
    await declare_topology(declare_channel)
    await declare_channel.close()

    bindings: list[tuple[str, object]] = []
    if not _truthy_env("STUB_SKIP_BRIEF"):
        bindings.append((BRIEF_REQUEST, _handle_brief_request))
    else:
        logger.info("STUB_SKIP_BRIEF set — not consuming pandora.brief.request (use worker-brief)")
    if not _truthy_env("STUB_SKIP_SCHEMA"):
        bindings.append((SCHEMA_REQUEST, _handle_schema_request))
    else:
        logger.info("STUB_SKIP_SCHEMA set — not consuming pandora.schema.request (use worker-schema)")
    if not _truthy_env("STUB_SKIP_COMPONENT"):
        bindings.append((COMPONENT_GENERATE, _handle_component_generate))
    else:
        logger.info(
            "STUB_SKIP_COMPONENT set — not consuming pandora.component.generate "
            "(use worker-component-gen + worker-feedback)"
        )
    bindings.extend(
        [
            (VERIFICATION_START, _handle_verification_start),
            (SHOWCASE_GENERATE, _handle_showcase_generate),
        ]
    )
    logger.info(
        "stub downstream worker listening on %s",
        ", ".join(queue for queue, _ in bindings),
    )
    await run_consumers(connection, bindings)


if __name__ == "__main__":
    asyncio.run(main())
