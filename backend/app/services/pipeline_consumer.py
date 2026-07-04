"""Pipeline Event Consumer — Phase 3 Step 5 (slices A–G)."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

import aio_pika
from aio_pika.abc import AbstractIncomingMessage, AbstractRobustConnection
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session
from app.models.component import Component
from app.models.design_brief import DesignBrief
from app.models.design_schema import DesignSchema
from app.models.pipeline_run import PipelineRun
from app.models.project import Project
from app.services.outbox import enqueue_outbox
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
    mark_brief_requested,
    notify_parses_complete_if_ready,
    persist_state,
    pipeline_states,
    record_parse_result,
)
from app.services import sse_service
from pandora_shared.enums import ComponentStatus, ProjectStatus
from pandora_shared.sse_events import (
    COMPONENTS_READY,
    PIPELINE_COMPLETE,
    REVISION_RUNNING,
    VERIFICATION_RUNNING,
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
    VERIFICATION_COMPLETE,
    VERIFICATION_START,
)

logger = logging.getLogger(__name__)

PREFETCH_COUNT = 10
MAX_REVISION_ROUNDS = 2

VERIFICATION_START_EVENT = "pandora.verification.start"
COMPONENT_GENERATE_EVENT = "pandora.component.generate"

Handler = Callable[[AbstractIncomingMessage, MessageBroker], Awaitable[None]]

_pipeline_locks: dict[int, asyncio.Lock] = {}


async def _nack_poison(message: AbstractIncomingMessage) -> None:
    await message.nack(requeue=False)


async def _nack_retry(message: AbstractIncomingMessage) -> None:
    await message.nack(requeue=True)


def make_parses_complete_callback() -> OnParsesComplete:
    """Build callback for ``init_state_from_thread`` / recovered pipelines."""

    async def callback(state: PipelineState) -> None:
        await trigger_brief_work(state)

    return callback


def wire_parses_complete_callbacks() -> None:
    """Attach brief trigger to recovered states that are still in parse phase."""
    callback = make_parses_complete_callback()
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


async def trigger_brief_work(state: PipelineState) -> None:
    """Enqueue brief work when all parses are collected (Slice A)."""
    if state.brief_requested:
        return

    envelope = MessageEnvelope(
        event=PipelineEvent.BRIEF_REQUEST,
        project_id=state.project_id,
        pipeline_id=state.pipeline_id,
        payload=merge_parse_results(state),
    )
    key = build_idempotency_key(state.pipeline_id, PipelineEvent.BRIEF_REQUEST)

    async with async_session() as db:
        await mark_brief_requested(state, db)
        inserted = await enqueue_outbox(
            db,
            BRIEF_REQUEST,
            envelope,
            project_id=state.project_id,
            idempotency_key=key,
        )
        await db.commit()

    if inserted:
        logger.info(
            "enqueued brief work project_id=%s pipeline_run_id=%s",
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

        await get_state(envelope.pipeline_id)
        source = parse_source_from_envelope(envelope)
        key = parse_results_idempotency_key(envelope.pipeline_id, source)

        async def _apply_parse(session: AsyncSession) -> bool:
            return await record_parse_result(
                session,
                envelope.pipeline_id,
                source,
                envelope.payload,
            )

        async with async_session() as db:
            status, complete = await run_idempotent(
                db,
                idempotency_key=key,
                project_id=envelope.project_id,
                handler=_apply_parse,
            )

        if status == IdempotencyStatus.DUPLICATE:
            await message.ack()
            return

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

        await get_state(envelope.pipeline_id)
        key = idempotency_key_for_envelope(envelope)

        async with async_session() as db:
            status, _ = await run_idempotent(
                db,
                idempotency_key=key,
                project_id=envelope.project_id,
                handler=lambda session: _apply_brief_ready(session, envelope),
            )

        if status == IdempotencyStatus.DUPLICATE:
            await message.ack()
            return

        _emit_project_event(
            envelope.project_id,
            _design_brief_ready_sse_payload(envelope),
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

        await get_state(envelope.pipeline_id)
        key = idempotency_key_for_envelope(envelope)

        async with async_session() as db:
            status, component_count = await run_idempotent(
                db,
                idempotency_key=key,
                project_id=envelope.project_id,
                handler=lambda session: _apply_schema_ready(session, envelope),
            )

        if status == IdempotencyStatus.DUPLICATE:
            await message.ack()
            return

        async with async_session() as db:
            state = await get_state(envelope.pipeline_id, session=db)
            state.expected_components = component_count
            state.resolved_components = 0
            await persist_state(state, db)
            await db.commit()

        schema_payload = envelope.payload if isinstance(envelope.payload, dict) else {}
        component_names = _component_names_from_specs(
            schema_payload.get("component_specs") or [],
        )
        _emit_project_event(
            envelope.project_id,
            {
                "type": "schema_ready",
                "projectId": envelope.project_id,
                "pipelineId": str(envelope.pipeline_id),
                "componentCount": component_count,
                "components": component_names,
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
        if state is None:
            try:
                state = await get_state(envelope.pipeline_id)
            except PipelineStateNotFoundError:
                state = None
        if state is None or state.run_complete:
            # Post-pipeline storybook regen, or run finished (``run_complete``).
            if status != IdempotencyStatus.DUPLICATE:
                _emit_project_event(
                    envelope.project_id,
                    _component_outcome_sse_payload(
                        envelope,
                        sse_type=sse_type,
                        component_name=component_name,
                    ),
                )
                if state is not None:
                    batch_done = await _increment_storybook_batch_and_check(state)
                    if batch_done:
                        await _maybe_emit_components_ready(
                            state,
                            source="storybook_regen",
                        )
                        await _clear_storybook_batch(state)
            await message.ack()
            return

        if status == IdempotencyStatus.DUPLICATE:
            await _maybe_emit_components_ready(state, source="pipeline")
            await _ensure_verification_if_gate_open(state)
            await message.ack()
            return

        gate_open = await _increment_resolved_and_check_gate(state)
        _emit_project_event(
            envelope.project_id,
            _component_outcome_sse_payload(
                envelope,
                sse_type=sse_type,
                component_name=component_name,
            ),
        )
        if gate_open:
            await _maybe_emit_components_ready(state, source="pipeline")
            await _ensure_verification_if_gate_open(state)
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

        state = await get_state(envelope.pipeline_id)
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
                await _fanout_revision_generates(db, envelope, state)
                lock = _pipeline_locks.setdefault(state.pipeline_id, asyncio.Lock())
                async with lock:
                    state.resolved_components = 0
                await persist_state(state, db)
                await db.commit()
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
                    handler=lambda session: _apply_pipeline_complete(session, envelope),
                )
            if status == IdempotencyStatus.DUPLICATE:
                state.run_complete = True
                async with async_session() as db:
                    await persist_state(state, db)
                    await db.commit()
                await message.ack()
                return

            await _finalize_pipeline_run(state, envelope.project_id, envelope.pipeline_id)
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


async def _ensure_verification_if_gate_open(state: PipelineState) -> None:
    """Start verification when DB shows all components resolved (survives redelivery/restart)."""
    async with async_session() as db:
        resolved = await _resolved_component_count(db, state.project_id)
        expected = await _expected_component_count(db, state.project_id, state)
    if expected <= 0 or resolved < expected:
        return
    await _start_verification(state)


async def _start_verification(state: PipelineState) -> None:
    """Slice E — enqueue verification work once all components are resolved."""
    key = build_idempotency_key(
        state.pipeline_id,
        VERIFICATION_START_EVENT,
        attempt=Attempt(revision_round=state.revision_round),
    )

    async def _enqueue(session: AsyncSession) -> None:
        work_payload = await _build_verification_work_payload(session, state.project_id)
        envelope = MessageEnvelope(
            event=VERIFICATION_START_EVENT,
            project_id=state.project_id,
            pipeline_id=state.pipeline_id,
            payload=work_payload,
        )
        await enqueue_outbox(
            session,
            VERIFICATION_START,
            envelope,
            project_id=state.project_id,
            idempotency_key=key,
        )

    async with async_session() as db:
        status, _ = await run_idempotent(
            db,
            idempotency_key=key,
            project_id=state.project_id,
            handler=_enqueue,
        )

    if status == IdempotencyStatus.DUPLICATE:
        return

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
        gate_open = state.resolved_components >= state.expected_components
    async with async_session() as db:
        await persist_state(state, db)
        await db.commit()
    return gate_open


async def _increment_storybook_batch_and_check(state: PipelineState) -> bool:
    if state.storybook_batch_expected <= 0:
        return False
    lock = _pipeline_locks.setdefault(state.pipeline_id, asyncio.Lock())
    async with lock:
        state.storybook_batch_resolved += 1
        return state.storybook_batch_resolved >= state.storybook_batch_expected


async def _clear_storybook_batch(state: PipelineState) -> None:
    state.storybook_batch_expected = 0
    state.storybook_batch_resolved = 0
    async with async_session() as db:
        await persist_state(state, db)
        await db.commit()


async def _components_ready_gate_open(
    session: AsyncSession,
    state: PipelineState,
) -> tuple[bool, int]:
    resolved = await _resolved_component_count(session, state.project_id)
    expected = await _expected_component_count(session, state.project_id, state)
    return expected > 0 and resolved >= expected, expected


async def _maybe_emit_components_ready(
    state: PipelineState,
    *,
    source: str,
    skip_revision_dedupe: bool = False,
) -> None:
    """Emit ``components_ready`` when the component library batch is terminal."""
    if source == "storybook_regen":
        if state.storybook_batch_expected <= 0:
            return
        _emit_components_ready_event(
            state,
            source=source,
            component_count=state.storybook_batch_expected,
        )
        return

    async with async_session() as db:
        gate_open, expected = await _components_ready_gate_open(db, state)
    if not gate_open:
        return
    if (
        source == "pipeline"
        and not skip_revision_dedupe
        and state.components_ready_at_revision >= state.revision_round
    ):
        return

    if source == "pipeline":
        state.components_ready_at_revision = state.revision_round
        async with async_session() as db:
            await persist_state(state, db)
            await db.commit()

    _emit_components_ready_event(state, source=source, component_count=expected)


def _emit_components_ready_event(
    state: PipelineState,
    *,
    source: str,
    component_count: int,
) -> None:
    _emit_project_event(
        state.project_id,
        {
            "type": COMPONENTS_READY,
            "projectId": state.project_id,
            "pipelineId": str(state.pipeline_id),
            "componentCount": component_count,
            "revisionRound": state.revision_round,
            "source": source,
        },
    )


async def _apply_pipeline_complete(
    session: AsyncSession,
    envelope: MessageEnvelope,
) -> None:
    """Mark project completed when holism verification finishes (Phase -1)."""
    project = await session.get(Project, envelope.project_id)
    if project is None:
        raise RuntimeError(f"project missing id={envelope.project_id}")
    project.status = ProjectStatus.completed
    await session.flush()


async def _finalize_pipeline_run(
    state: PipelineState,
    project_id: int,
    pipeline_run_id: int,
) -> None:
    """Persist ``run_complete`` and emit ``pipeline_complete`` after verification pass."""
    state.run_complete = True
    async with async_session() as db:
        await persist_state(state, db)
        await db.commit()
    await _maybe_emit_components_ready(
        state,
        source="pipeline_complete",
        skip_revision_dedupe=True,
    )
    _emit_project_event(
        project_id,
        {
            "type": PIPELINE_COMPLETE,
            "projectId": project_id,
            "pipelineId": str(pipeline_run_id),
        },
    )


async def _apply_brief_ready(
    session: AsyncSession,
    envelope: MessageEnvelope,
) -> None:
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

    schema_envelope = MessageEnvelope(
        event=PipelineEvent.SCHEMA_REQUEST,
        project_id=envelope.project_id,
        pipeline_id=envelope.pipeline_id,
        payload=dict(payload),
    )
    schema_key = build_idempotency_key(envelope.pipeline_id, PipelineEvent.SCHEMA_REQUEST)
    await enqueue_outbox(
        session,
        SCHEMA_REQUEST,
        schema_envelope,
        project_id=envelope.project_id,
        idempotency_key=schema_key,
    )


async def _apply_schema_ready(
    session: AsyncSession,
    envelope: MessageEnvelope,
) -> int:
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

    component_count = 0
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
        work = MessageEnvelope(
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
        outbox_key = build_idempotency_key(
            envelope.pipeline_id,
            COMPONENT_GENERATE_EVENT,
            component_id=component.id,
            attempt=Attempt(retry_count=0, revision_round=0),
        )
        await enqueue_outbox(
            session,
            COMPONENT_GENERATE,
            work,
            project_id=envelope.project_id,
            idempotency_key=outbox_key,
        )
        component_count += 1

    run = await session.get(PipelineRun, envelope.pipeline_id)
    if run is not None:
        run.expected_components = component_count
        run.resolved_components = 0
    await session.flush()
    return component_count


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
    await persist_state(state, session)

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
        outbox_key = build_idempotency_key(
            envelope.pipeline_id,
            COMPONENT_GENERATE_EVENT,
            component_id=component.id,
            attempt=work.attempt,
        )
        await enqueue_outbox(
            session,
            COMPONENT_GENERATE,
            work,
            project_id=envelope.project_id,
            idempotency_key=outbox_key,
        )

    await session.flush()


def _component_names_from_specs(specs: list[dict[str, Any]]) -> list[str]:
    names: list[str] = []
    for index, spec in enumerate(specs):
        name = spec.get("name") if isinstance(spec, dict) else None
        names.append(name if isinstance(name, str) and name.strip() else f"component-{index}")
    return names


def _component_outcome_sse_payload(
    envelope: MessageEnvelope,
    *,
    sse_type: str,
    component_name: str,
) -> dict[str, Any]:
    revision_round = 0
    if envelope.attempt is not None:
        revision_round = envelope.attempt.revision_round

    payload = envelope.payload if isinstance(envelope.payload, dict) else {}
    if revision_round > 0 or payload.get("storybook_ad_hoc"):
        source = "storybook_revise"
    else:
        source = "pipeline"

    event: dict[str, Any] = {
        "type": sse_type,
        "projectId": envelope.project_id,
        "pipelineId": str(envelope.pipeline_id),
        "componentId": str(envelope.component_id),
        "componentName": component_name,
        "revisionRound": revision_round,
        "source": source,
    }
    if sse_type == "component_failed":
        err = payload.get("error_reason") or payload.get("error")
        if err:
            event["error"] = _truncate_text(str(err), limit=280)
    return event


def _design_brief_ready_sse_payload(envelope: MessageEnvelope) -> dict[str, Any]:
    """SSE body for ``design_brief_ready`` (camelCase for API consumers)."""
    payload = envelope.payload if isinstance(envelope.payload, dict) else {}
    return {
        "type": "design_brief_ready",
        "projectId": envelope.project_id,
        "pipelineId": str(envelope.pipeline_id),
        "colorTokens": payload.get("color_tokens") or {},
        "typographyScale": payload.get("typography_scale") or {},
        "spacingSystem": payload.get("spacing_system") or {},
        "tone": payload.get("tone"),
        "componentList": payload.get("component_list") or [],
        "inputGaps": payload.get("input_gaps") or [],
    }


def _emit_project_event(project_id: int, event: dict[str, Any]) -> None:
    sse_service.emit(project_id, event)
