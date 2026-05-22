"""Pipeline Event Consumer — Phase 3 Step 5 (slices A–G)."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any
from uuid import UUID

import aio_pika
from aio_pika.abc import AbstractIncomingMessage, AbstractRobustConnection
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session
from app.models.component import Component
from app.models.design_brief import DesignBrief
from app.models.design_schema import DesignSchema
from app.models.project import Project
from app.models.showcase_scene import ShowcaseScene
from app.services import pipeline_state
from app.services.idempotency import (
    IdempotencyStatus,
    idempotency_key_for_envelope,
    parse_results_idempotency_key,
    run_idempotent,
)
from app.services.message_broker import MessageBroker, decode_envelope
from app.services.storybook_publish import build_component_generate_envelope
from app.services.pipeline_state import (
    OnParsesComplete,
    PipelineState,
    PipelineStateNotFoundError,
    get_state,
    notify_parses_complete_if_ready,
    pipeline_states,
    record_parse_result,
)
from app.services import sse_service
from pandora_shared.enums import ComponentStatus, ProjectStatus
from pandora_shared.sse_events import (
    PIPELINE_COMPLETE,
    REVISION_RUNNING,
    VERIFICATION_RUNNING,
)
from pandora_shared.showcase_bundle import (
    build_module_manifest,
    build_showcase_bundle,
    components_for_bundle_from_db,
)
from pandora_shared.events import (
    Attempt,
    MessageEnvelope,
    PipelineEvent,
    build_idempotency_key,
    parse_source_from_envelope,
)
from pandora_shared.queues import (
    BRIEF_READY,
    BRIEF_REQUEST,
    COMPONENT_FAILED,
    COMPONENT_GENERATE,
    COMPONENT_VALIDATED,
    PARSE_RESULTS,
    SCHEMA_READY,
    SCHEMA_REQUEST,
    SHOWCASE_GENERATE,
    SHOWCASE_READY,
    VERIFICATION_COMPLETE,
    VERIFICATION_START,
)

logger = logging.getLogger(__name__)

PREFETCH_COUNT = 10
MAX_REVISION_ROUNDS = 2

VERIFICATION_START_EVENT = "pandora.verification.start"
COMPONENT_GENERATE_EVENT = "pandora.component.generate"
SHOWCASE_GENERATE_EVENT = "pandora.showcase.generate"

Handler = Callable[[AbstractIncomingMessage, MessageBroker], Awaitable[None]]

_pipeline_locks: dict[UUID, asyncio.Lock] = {}


async def _nack_poison(message: AbstractIncomingMessage) -> None:
    await message.nack(requeue=False)


async def _nack_retry(message: AbstractIncomingMessage) -> None:
    await message.nack(requeue=True)


def make_parses_complete_callback(
    broker: MessageBroker,
) -> OnParsesComplete:
    """Build callback for ``init_state_from_thread`` / recovered pipelines."""

    async def callback(state: PipelineState) -> None:
        await trigger_brief_work(state, broker)

    return callback


def wire_parses_complete_callbacks(broker: MessageBroker) -> None:
    """Attach brief trigger to recovered states that are still in parse phase."""
    callback = make_parses_complete_callback(broker)
    for state in pipeline_states.values():
        if state.parse_pending and state._on_parses_complete is None:
            state._on_parses_complete = callback


def merge_parse_results(state: PipelineState) -> dict[str, Any]:
    """Combine parse payloads and collect input gaps for the brief agent."""
    merged: dict[str, Any] = {"sources": {}, "input_gaps": []}
    for source, payload in state.parse_results.items():
        merged["sources"][source] = payload
        error = payload.get("error")
        if error == "timeout":
            merged["input_gaps"].append(f"{source}:timeout")
        elif error:
            merged["input_gaps"].append(f"{source}:{error}")
    return merged


async def trigger_brief_work(state: PipelineState, broker: MessageBroker) -> None:
    """Publish one brief work message when all parses are collected (Slice A)."""
    envelope = MessageEnvelope(
        event=PipelineEvent.BRIEF_REQUEST,
        project_id=state.project_id,
        pipeline_id=state.pipeline_id,
        payload=merge_parse_results(state),
    )
    await broker.publish(BRIEF_REQUEST, envelope)
    logger.info(
        "published brief work project_id=%s pipeline_id=%s",
        state.project_id,
        state.pipeline_id,
    )


async def _consume_queue(
    channel: aio_pika.abc.AbstractChannel,
    broker: MessageBroker,
    queue_name: str,
    handler: Handler,
) -> None:
    queue = await channel.declare_queue(queue_name, passive=True)
    async with queue.iterator() as queue_iter:
        async for message in queue_iter:
            try:
                await handler(message, broker)
            except Exception:
                logger.exception("unhandled error on queue %s", queue_name)
                await message.nack(requeue=True)


async def _handle_parse_results(
    message: AbstractIncomingMessage,
    broker: MessageBroker,
) -> None:
    _ = broker
    try:
        envelope = decode_envelope(message.body)
        if envelope.event != PipelineEvent.PARSE_RESULTS:
            await message.ack()
            return

        get_state(envelope.pipeline_id)
        source = parse_source_from_envelope(envelope)
        key = parse_results_idempotency_key(envelope.pipeline_id, source)

        async with async_session() as db:
            status, _ = await run_idempotent(
                db,
                idempotency_key=key,
                project_id=envelope.project_id,
                handler=_noop_handler,
            )

        if status == IdempotencyStatus.DUPLICATE:
            await message.ack()
            return

        complete = record_parse_result(envelope.pipeline_id, source, envelope.payload)
        if complete:
            await notify_parses_complete_if_ready(envelope.pipeline_id)

        await message.ack()
    except PipelineStateNotFoundError:
        logger.error("parse result for unknown pipeline_id")
        await _nack_poison(message)
    except ValueError:
        logger.warning("invalid parse result payload")
        await _nack_poison(message)
    except ValidationError:
        logger.warning("invalid parse result message; dropping")
        await _nack_poison(message)
    except Exception:
        logger.exception("parse result handler failed")
        await _nack_retry(message)


async def _handle_brief_ready(
    message: AbstractIncomingMessage,
    broker: MessageBroker,
) -> None:
    try:
        envelope = decode_envelope(message.body)
        if envelope.event != PipelineEvent.BRIEF_READY:
            await message.ack()
            return

        get_state(envelope.pipeline_id)
        key = idempotency_key_for_envelope(envelope)

        async with async_session() as db:
            status, brief_payload = await run_idempotent(
                db,
                idempotency_key=key,
                project_id=envelope.project_id,
                handler=lambda session: _apply_brief_ready(session, envelope),
            )

        if status == IdempotencyStatus.DUPLICATE:
            await message.ack()
            return

        schema_envelope = MessageEnvelope(
            event=PipelineEvent.SCHEMA_REQUEST,
            project_id=envelope.project_id,
            pipeline_id=envelope.pipeline_id,
            payload=brief_payload,
        )
        await broker.publish(SCHEMA_REQUEST, schema_envelope)
        _emit_project_event(
            envelope.project_id,
            {
                "type": "design_brief_ready",
                "projectId": envelope.project_id,
                "pipelineId": str(envelope.pipeline_id),
            },
        )
        await message.ack()
    except PipelineStateNotFoundError:
        logger.error("brief ready for unknown pipeline_id")
        await _nack_poison(message)
    except ValidationError:
        logger.warning("invalid brief ready message; dropping")
        await _nack_poison(message)
    except Exception:
        logger.exception("brief ready handler failed")
        await _nack_retry(message)


async def _handle_schema_ready(
    message: AbstractIncomingMessage,
    broker: MessageBroker,
) -> None:
    try:
        envelope = decode_envelope(message.body)
        if envelope.event != PipelineEvent.SCHEMA_READY:
            await message.ack()
            return

        get_state(envelope.pipeline_id)
        key = idempotency_key_for_envelope(envelope)

        async with async_session() as db:
            status, fanout = await run_idempotent(
                db,
                idempotency_key=key,
                project_id=envelope.project_id,
                handler=lambda session: _apply_schema_ready(session, envelope),
            )

        if status == IdempotencyStatus.DUPLICATE:
            await message.ack()
            return

        state = get_state(envelope.pipeline_id)
        state.expected_components = len(fanout)
        state.resolved_components = 0

        for work in fanout:
            await broker.publish(COMPONENT_GENERATE, work)

        _emit_project_event(
            envelope.project_id,
            {
                "type": "schema_ready",
                "projectId": envelope.project_id,
                "pipelineId": str(envelope.pipeline_id),
                "componentCount": len(fanout),
            },
        )
        await message.ack()
    except PipelineStateNotFoundError:
        logger.error("schema ready for unknown pipeline_id")
        await _nack_poison(message)
    except ValidationError:
        logger.warning("invalid schema ready message; dropping")
        await _nack_poison(message)
    except Exception:
        logger.exception("schema ready handler failed")
        await _nack_retry(message)


async def _handle_component_validated(
    message: AbstractIncomingMessage,
    broker: MessageBroker,
) -> None:
    await _handle_component_outcome(
        message,
        broker,
        expected_event=PipelineEvent.COMPONENT_VALIDATED,
        sse_type="component_validated",
    )


async def _handle_component_failed(
    message: AbstractIncomingMessage,
    broker: MessageBroker,
) -> None:
    await _handle_component_outcome(
        message,
        broker,
        expected_event=PipelineEvent.COMPONENT_FAILED,
        sse_type="component_failed",
    )


async def _handle_component_outcome(
    message: AbstractIncomingMessage,
    broker: MessageBroker,
    *,
    expected_event: PipelineEvent,
    sse_type: str,
) -> None:
    try:
        envelope = decode_envelope(message.body)
        if envelope.event != expected_event:
            await message.ack()
            return
        if envelope.component_id is None:
            logger.warning("component outcome missing component_id")
            await _nack_poison(message)
            return

        key = idempotency_key_for_envelope(envelope)

        async with async_session() as db:
            status, component_name = await run_idempotent(
                db,
                idempotency_key=key,
                project_id=envelope.project_id,
                handler=lambda session: _apply_component_outcome(
                    session, envelope, validated=expected_event == PipelineEvent.COMPONENT_VALIDATED
                ),
            )

        state = pipeline_states.get(envelope.pipeline_id)
        if state is None or state.run_complete:
            # Post-pipeline (storybook regen) or state lost after API restart (Redis later).
            if status != IdempotencyStatus.DUPLICATE:
                _emit_project_event(
                    envelope.project_id,
                    {
                        "type": sse_type,
                        "projectId": envelope.project_id,
                        "pipelineId": str(envelope.pipeline_id),
                        "componentId": str(envelope.component_id),
                        "componentName": component_name,
                    },
                )
            await message.ack()
            return

        if status == IdempotencyStatus.DUPLICATE:
            await _ensure_verification_if_gate_open(state, broker)
            await message.ack()
            return

        gate_open = await _increment_resolved_and_check_gate(state)
        _emit_project_event(
            envelope.project_id,
            {
                "type": sse_type,
                "projectId": envelope.project_id,
                "pipelineId": str(envelope.pipeline_id),
                "componentId": str(envelope.component_id),
                "componentName": component_name,
            },
        )
        if gate_open:
            await _ensure_verification_if_gate_open(state, broker)
        await message.ack()
    except ValidationError:
        logger.warning("invalid component outcome message; dropping")
        await _nack_poison(message)
    except Exception:
        logger.exception("component outcome handler failed event=%s", expected_event)
        await _nack_retry(message)


async def _handle_verification_complete(
    message: AbstractIncomingMessage,
    broker: MessageBroker,
) -> None:
    try:
        envelope = decode_envelope(message.body)
        if envelope.event != PipelineEvent.VERIFICATION_COMPLETE:
            await message.ack()
            return

        state = get_state(envelope.pipeline_id)
        verification_pass = state.revision_round
        key = build_idempotency_key(
            envelope.pipeline_id,
            envelope.event,
            attempt=Attempt(revision_round=verification_pass),
        )
        payload = envelope.payload
        issues = payload.get("issues") or []
        has_blocking = any(issue.get("priority") in ("P1", "P2") for issue in issues)

        if has_blocking and state.revision_round < MAX_REVISION_ROUNDS:
            async with async_session() as db:
                status, _ = await run_idempotent(
                    db,
                    idempotency_key=key,
                    project_id=envelope.project_id,
                    handler=lambda session: _apply_verification_revisions(session, envelope),
                )
            if status == IdempotencyStatus.DUPLICATE:
                await message.ack()
                return

            state.revision_round += 1
            async with async_session() as db:
                await _fanout_revision_generates(db, envelope, state, broker)
                await db.commit()
            lock = _pipeline_locks.setdefault(state.pipeline_id, asyncio.Lock())
            async with lock:
                state.resolved_components = 0
            _emit_project_event(
                envelope.project_id,
                {
                    "type": REVISION_RUNNING,
                    "projectId": envelope.project_id,
                    "pipelineId": str(envelope.pipeline_id),
                    "revisionRound": state.revision_round,
                },
            )
        else:
            async with async_session() as db:
                status, _ = await run_idempotent(
                    db,
                    idempotency_key=key,
                    project_id=envelope.project_id,
                    handler=_noop_handler,
                )
            if status == IdempotencyStatus.DUPLICATE:
                await message.ack()
                return

            async with async_session() as db:
                showcase_payload = await _build_showcase_work_payload(db, envelope.project_id)
            showcase_envelope = MessageEnvelope(
                event=SHOWCASE_GENERATE_EVENT,
                project_id=state.project_id,
                pipeline_id=state.pipeline_id,
                payload=showcase_payload,
            )
            await broker.publish(SHOWCASE_GENERATE, showcase_envelope)
            _emit_project_event(
                envelope.project_id,
                {
                    "type": "showcase_running",
                    "projectId": envelope.project_id,
                    "pipelineId": str(envelope.pipeline_id),
                },
            )
        await message.ack()
    except PipelineStateNotFoundError:
        logger.error("verification complete for unknown pipeline_id")
        await _nack_poison(message)
    except ValidationError:
        logger.warning("invalid verification complete message; dropping")
        await _nack_poison(message)
    except Exception:
        logger.exception("verification complete handler failed")
        await _nack_retry(message)


async def _handle_showcase_ready(
    message: AbstractIncomingMessage,
    broker: MessageBroker,
) -> None:
    _ = broker
    try:
        envelope = decode_envelope(message.body)
        if envelope.event != PipelineEvent.SHOWCASE_READY:
            await message.ack()
            return

        key = idempotency_key_for_envelope(envelope)

        async with async_session() as db:
            status, _ = await run_idempotent(
                db,
                idempotency_key=key,
                project_id=envelope.project_id,
                handler=lambda session: _apply_showcase_ready(session, envelope),
            )

        if status == IdempotencyStatus.DUPLICATE:
            await message.ack()
            return

        state = pipeline_states.get(envelope.pipeline_id)
        if state is not None:
            state.run_complete = True

        _emit_project_event(
            envelope.project_id,
            {
                "type": PIPELINE_COMPLETE,
                "projectId": envelope.project_id,
                "pipelineId": str(envelope.pipeline_id),
            },
        )
        await message.ack()
    except ValidationError:
        logger.warning("invalid showcase ready message; dropping")
        await _nack_poison(message)
    except Exception:
        logger.exception("showcase ready handler failed")
        await _nack_retry(message)


_RESOLVED_COMPONENT_STATUSES = (ComponentStatus.validated, ComponentStatus.failed)


async def _resolved_component_count(session: AsyncSession, project_id: int) -> int:
    result = await session.scalar(
        select(func.count())
        .select_from(Component)
        .where(
            Component.project_id == project_id,
            Component.status.in_(_RESOLVED_COMPONENT_STATUSES),
        )
    )
    return int(result or 0)


async def _expected_component_count(
    session: AsyncSession,
    project_id: int,
    state: PipelineState,
) -> int:
    if state.expected_components > 0:
        return state.expected_components
    result = await session.scalar(
        select(func.count())
        .select_from(Component)
        .where(Component.project_id == project_id)
    )
    return int(result or 0)


async def _ensure_verification_if_gate_open(
    state: PipelineState,
    broker: MessageBroker,
) -> None:
    """Start verification when DB shows all components resolved (survives redelivery/restart)."""
    async with async_session() as db:
        resolved = await _resolved_component_count(db, state.project_id)
        expected = await _expected_component_count(db, state.project_id, state)
    if expected <= 0 or resolved < expected:
        return
    await _start_verification(state, broker)


async def _start_verification(state: PipelineState, broker: MessageBroker) -> None:
    """Slice E — publish verification work once all components are resolved."""
    key = build_idempotency_key(
        state.pipeline_id,
        VERIFICATION_START_EVENT,
        attempt=Attempt(revision_round=state.revision_round),
    )
    work_payload: dict[str, Any] = {}
    async with async_session() as db:
        status, _ = await run_idempotent(
            db,
            idempotency_key=key,
            project_id=state.project_id,
            handler=_noop_handler,
        )
        if status != IdempotencyStatus.DUPLICATE:
            work_payload = await _build_verification_work_payload(db, state.project_id)

    if status == IdempotencyStatus.DUPLICATE:
        return

    envelope = MessageEnvelope(
        event=VERIFICATION_START_EVENT,
        project_id=state.project_id,
        pipeline_id=state.pipeline_id,
        payload=work_payload,
    )
    await broker.publish(VERIFICATION_START, envelope)
    _emit_project_event(
        state.project_id,
        {
            "type": VERIFICATION_RUNNING,
            "projectId": state.project_id,
            "pipelineId": str(state.pipeline_id),
        },
    )


def _result_handlers() -> list[tuple[str, Handler]]:
    return [
        (PARSE_RESULTS, _handle_parse_results),
        (BRIEF_READY, _handle_brief_ready),
        (SCHEMA_READY, _handle_schema_ready),
        (COMPONENT_VALIDATED, _handle_component_validated),
        (COMPONENT_FAILED, _handle_component_failed),
        (VERIFICATION_COMPLETE, _handle_verification_complete),
        (SHOWCASE_READY, _handle_showcase_ready),
    ]


async def run_forever(
    connection: AbstractRobustConnection,
    broker: MessageBroker,
) -> None:
    """Start one consume loop per result queue until cancelled."""
    channel = await connection.channel()
    await channel.set_qos(prefetch_count=PREFETCH_COUNT)
    tasks = [
        asyncio.create_task(
            _consume_queue(channel, broker, queue_name, handler),
            name=f"pipeline-consumer-{queue_name}",
        )
        for queue_name, handler in _result_handlers()
    ]
    try:
        await asyncio.gather(*tasks)
    except asyncio.CancelledError:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        raise


async def _increment_resolved_and_check_gate(state: PipelineState) -> bool:
    lock = _pipeline_locks.setdefault(state.pipeline_id, asyncio.Lock())
    async with lock:
        state.resolved_components += 1
        return state.resolved_components >= state.expected_components


async def _noop_handler(_session: AsyncSession) -> None:
    return None


async def _apply_brief_ready(
    session: AsyncSession,
    envelope: MessageEnvelope,
) -> dict[str, Any]:
    payload = envelope.payload
    brief = DesignBrief(
        project_id=envelope.project_id,
        color_tokens=payload.get("color_tokens"),
        typography_scale=payload.get("typography_scale"),
        spacing_system=payload.get("spacing_system"),
        design_flavour=payload.get("design_flavour"),
        tone=payload.get("tone"),
        component_list=payload.get("component_list"),
        input_gaps=payload.get("input_gaps"),
    )
    session.add(brief)
    await session.flush()
    return dict(payload)


async def _apply_schema_ready(
    session: AsyncSession,
    envelope: MessageEnvelope,
) -> list[MessageEnvelope]:
    payload = envelope.payload
    brief = await session.scalar(
        select(DesignBrief).where(DesignBrief.project_id == envelope.project_id)
    )
    if brief is None:
        raise RuntimeError(f"design brief missing for project_id={envelope.project_id}")

    specs: list[dict[str, Any]] = payload.get("component_specs") or []
    schema = DesignSchema(
        project_id=envelope.project_id,
        brief_id=brief.id,
        design_tokens=payload.get("design_tokens"),
        global_config=payload.get("global_config"),
        component_specs=specs,
        component_count=len(specs),
    )
    session.add(schema)
    await session.flush()

    work_envelopes: list[MessageEnvelope] = []
    for index, spec in enumerate(specs):
        name = spec.get("name") or f"component-{index}"
        component = Component(
            project_id=envelope.project_id,
            schema_id=schema.id,
            spec_index=index,
            name=name,
            status=ComponentStatus.generating,
        )
        session.add(component)
        await session.flush()
        work_envelopes.append(
            MessageEnvelope(
                event=COMPONENT_GENERATE_EVENT,
                project_id=envelope.project_id,
                pipeline_id=envelope.pipeline_id,
                component_id=component.id,
                attempt=Attempt(retry_count=0, revision_round=0),
                payload={
                    "spec": spec,
                    "spec_index": index,
                    "design_tokens": payload.get("design_tokens"),
                    "global_config": payload.get("global_config"),
                },
            )
        )
    await session.flush()
    return work_envelopes


async def _apply_component_outcome(
    session: AsyncSession,
    envelope: MessageEnvelope,
    *,
    validated: bool,
) -> str:
    component = await session.scalar(
        select(Component).where(Component.id == envelope.component_id)
    )
    if component is None:
        raise RuntimeError(f"component not found id={envelope.component_id}")

    payload = envelope.payload
    if validated:
        component.status = ComponentStatus.validated
        component.tsx_code = payload.get("tsx_code")
        component.css_code = payload.get("css_code")
        component.props = payload.get("props")
        component.variants = payload.get("variants")
        component.error_reason = None
    else:
        component.status = ComponentStatus.failed
        component.error_reason = payload.get("error_reason") or payload.get("error") or "failed"

    if envelope.attempt is not None:
        component.retry_count = envelope.attempt.retry_count
        component.revision_round = envelope.attempt.revision_round

    await session.flush()
    return component.name


def _truncate_text(value: str | None, *, limit: int) -> str | None:
    if value is None:
        return None
    text = value.strip()
    if not text:
        return None
    if len(text) <= limit:
        return text
    return text[:limit] + "…[truncated]"


async def _latest_schema_for_project(
    session: AsyncSession,
    project_id: int,
) -> DesignSchema | None:
    return await session.scalar(
        select(DesignSchema)
        .where(DesignSchema.project_id == project_id)
        .order_by(DesignSchema.id.desc())
        .limit(1)
    )


def _spec_for_component(schema: DesignSchema | None, spec_index: int) -> dict[str, Any]:
    if schema is None or not schema.component_specs:
        return {}
    specs = schema.component_specs
    if 0 <= spec_index < len(specs) and isinstance(specs[spec_index], dict):
        return dict(specs[spec_index])
    return {}


async def _build_verification_work_payload(
    session: AsyncSession,
    project_id: int,
) -> dict[str, Any]:
    schema = await _latest_schema_for_project(session, project_id)
    result = await session.execute(
        select(Component)
        .where(Component.project_id == project_id)
        .order_by(Component.spec_index.asc())
    )
    components = result.scalars().all()
    summaries: list[dict[str, Any]] = []
    for component in components:
        summaries.append(
            {
                "id": component.id,
                "name": component.name,
                "status": component.status.value,
                "spec": _spec_for_component(schema, component.spec_index),
                "tsx_preview": _truncate_text(component.tsx_code, limit=2000),
                "css_preview": _truncate_text(component.css_code, limit=1000),
                "error_reason": component.error_reason,
            }
        )
    return {
        "design_tokens": schema.design_tokens if schema else {},
        "global_config": schema.global_config if schema else {},
        "components": summaries,
    }


async def _build_showcase_work_payload(
    session: AsyncSession,
    project_id: int,
) -> dict[str, Any]:
    schema = await _latest_schema_for_project(session, project_id)
    result = await session.execute(
        select(Component)
        .where(
            Component.project_id == project_id,
            Component.status == ComponentStatus.validated,
        )
        .order_by(Component.spec_index.asc())
    )
    components = result.scalars().all()
    library: list[dict[str, Any]] = []
    for component in components:
        spec = _spec_for_component(schema, component.spec_index)
        library.append(
            {
                "id": component.id,
                "name": component.name,
                "type": spec.get("type"),
                "tsx_code": _truncate_text(component.tsx_code, limit=4000),
                "css_code": _truncate_text(component.css_code, limit=2000),
                "variants": component.variants,
                "props": component.props,
            }
        )
    manifest = build_module_manifest(library)
    return {
        "design_tokens": schema.design_tokens if schema else {},
        "global_config": schema.global_config if schema else {},
        "components": library,
        "module_manifest": manifest,
    }


async def _apply_verification_revisions(
    session: AsyncSession,
    envelope: MessageEnvelope,
) -> None:
    """Persist revision instructions from blocking verification issues."""
    seen: set[int] = set()
    for item in envelope.payload.get("revisions") or []:
        raw_id = item.get("component_id")
        if raw_id is None:
            continue
        component_id = int(raw_id)
        if component_id in seen:
            continue
        seen.add(component_id)
        component = await session.scalar(
            select(Component).where(Component.id == component_id)
        )
        if component is None:
            continue
        instruction = item.get("revision_instruction") or item.get("message")
        if isinstance(instruction, str) and instruction.strip():
            component.revision_instruction = instruction.strip()
            component.status = ComponentStatus.revised

    for issue in envelope.payload.get("issues") or []:
        if issue.get("priority") not in ("P1", "P2"):
            continue
        raw_id = issue.get("component_id")
        if raw_id is None:
            continue
        component_id = int(raw_id)
        if component_id in seen:
            continue
        seen.add(component_id)
        component = await session.scalar(
            select(Component).where(Component.id == component_id)
        )
        if component is None:
            continue
        message = issue.get("message")
        if isinstance(message, str) and message.strip():
            component.revision_instruction = message.strip()
            component.status = ComponentStatus.revised

    await session.flush()


async def _fanout_revision_generates(
    session: AsyncSession,
    envelope: MessageEnvelope,
    state: PipelineState,
    broker: MessageBroker,
) -> None:
    """Re-queue component.generate for components marked revised."""
    schema = await _latest_schema_for_project(session, envelope.project_id)
    result = await session.execute(
        select(Component)
        .where(
            Component.project_id == envelope.project_id,
            Component.status == ComponentStatus.revised,
        )
        .order_by(Component.spec_index.asc())
    )
    components = result.scalars().all()
    if not components:
        return

    revision_round = state.revision_round
    state.expected_components = len(components)
    state.resolved_components = 0

    if schema is None:
        return

    for component in components:
        component.status = ComponentStatus.generating
        work = build_component_generate_envelope(
            project_id=envelope.project_id,
            pipeline_id=envelope.pipeline_id,
            component=component,
            schema=schema,
            design_tokens=schema.design_tokens,
            global_config=schema.global_config,
            revision_instruction=component.revision_instruction,
            revision_round=revision_round,
            storybook_ad_hoc=False,
        )
        await broker.publish(COMPONENT_GENERATE, work)

    await session.flush()


async def _apply_showcase_ready(
    session: AsyncSession,
    envelope: MessageEnvelope,
) -> None:
    schema = await _latest_schema_for_project(session, envelope.project_id)
    result = await session.execute(
        select(Component)
        .where(
            Component.project_id == envelope.project_id,
            Component.status == ComponentStatus.validated,
        )
        .order_by(Component.spec_index.asc())
    )
    component_rows = result.scalars().all()
    bundle_components = components_for_bundle_from_db(component_rows)
    design_tokens = schema.design_tokens if schema and schema.design_tokens else {}

    scenes = envelope.payload.get("scenes") or []
    for scene in scenes:
        scene_tsx = scene.get("scene_tsx_code") or ""
        scene_css = scene.get("scene_css_code")
        scene_index = int(scene.get("scene_index", 0))
        showcase_bundle = build_showcase_bundle(
            design_tokens=design_tokens,
            components=bundle_components,
            scene_tsx=scene_tsx,
            scene_css=scene_css if isinstance(scene_css, str) else None,
            scene_index=scene_index,
        )
        session.add(
            ShowcaseScene(
                project_id=envelope.project_id,
                scene_index=scene_index,
                scene_name=scene.get("scene_name"),
                scene_tsx_code=scene_tsx,
                scene_css_code=scene_css,
                components_used=scene.get("components_used"),
                variant_selections=scene.get("variant_selections"),
                showcase_bundle=showcase_bundle,
            )
        )

    project = await session.get(Project, envelope.project_id)
    if project is None:
        raise RuntimeError(f"project missing id={envelope.project_id}")
    project.status = ProjectStatus.completed
    await session.flush()


def _emit_project_event(project_id: int, event: dict[str, Any]) -> None:
    sse_service.emit(project_id, event)
