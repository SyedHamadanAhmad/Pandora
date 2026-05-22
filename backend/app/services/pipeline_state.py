"""Pipeline run coordination — durable Postgres rows + in-process cache (Phase 0)."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session
from app.models.component import Component
from app.models.design_brief import DesignBrief
from app.models.design_schema import DesignSchema
from app.models.pipeline_run import PipelineRun
from app.models.project import Project
from app.models.thread_message import ThreadMessage
from pandora_shared.enums import ComponentStatus, ProjectStatus
from pandora_shared.payloads import ParseResultPayload

logger = logging.getLogger(__name__)

PipelineRunId = int

PARSE_TIMEOUT_SECONDS = 150
PARSE_URL_TIMEOUT_FLOOR = 120
PARSE_URL_TIMEOUT_PER_URL = 100
PARSE_URL_TIMEOUT_SYNTHESIS = 90

ParseSource = str  # "text" | "image" | "url"

PARSE_SOURCES: frozenset[ParseSource] = frozenset({"text", "image", "url"})

OnParsesComplete = Callable[["PipelineState"], Awaitable[None]]


class PipelineStateNotFoundError(KeyError):
    """Raised when no pipeline run exists for the given id."""


@dataclass
class PipelineState:
    """Working view of a row in ``pipeline_runs`` (``pipeline_id`` == ``pipeline_runs.id``)."""

    project_id: int
    pipeline_id: PipelineRunId
    url_count: int = 0
    expected_components: int = 0
    resolved_components: int = 0
    parse_results: dict[str, dict[str, Any]] = field(default_factory=dict)
    parse_expected: int = 0
    parse_received: int = 0
    parse_pending: set[str] = field(default_factory=set)
    revision_round: int = 0
    run_complete: bool = False
    brief_requested: bool = False
    _timeout_tasks: list[asyncio.Task[None]] = field(default_factory=list, repr=False, compare=False)
    _on_parses_complete: OnParsesComplete | None = field(default=None, repr=False, compare=False)


# In-process cache: timeouts, callbacks, and hot-path reads. Source of truth is ``pipeline_runs``.
pipeline_states: dict[PipelineRunId, PipelineState] = {}


def modalities_from_message(message: ThreadMessage) -> set[ParseSource]:
    sources: set[ParseSource] = set()
    if message.content and message.content.strip():
        sources.add("text")
    if message.input_image_urls:
        sources.add("image")
    if message.input_urls:
        sources.add("url")
    return sources


def _state_from_run(
    run: PipelineRun,
    *,
    on_parses_complete: OnParsesComplete | None = None,
) -> PipelineState:
    pending = run.parse_pending
    if isinstance(pending, list):
        pending_set = set(pending)
    else:
        pending_set = set()
    results = run.parse_results if isinstance(run.parse_results, dict) else {}
    return PipelineState(
        project_id=run.project_id,
        pipeline_id=run.id,
        url_count=run.url_count,
        expected_components=run.expected_components,
        resolved_components=run.resolved_components,
        parse_results=dict(results),
        parse_expected=run.parse_expected,
        parse_received=run.parse_received,
        parse_pending=pending_set,
        revision_round=run.revision_round,
        run_complete=run.run_complete,
        brief_requested=run.brief_requested,
        _on_parses_complete=on_parses_complete,
    )


def _apply_state_to_run(run: PipelineRun, state: PipelineState) -> None:
    run.url_count = state.url_count
    run.expected_components = state.expected_components
    run.resolved_components = state.resolved_components
    run.parse_results = dict(state.parse_results)
    run.parse_expected = state.parse_expected
    run.parse_received = state.parse_received
    run.parse_pending = sorted(state.parse_pending)
    run.revision_round = state.revision_round
    run.run_complete = state.run_complete
    run.brief_requested = state.brief_requested


async def _load_into_cache(
    session: AsyncSession,
    pipeline_run_id: PipelineRunId,
    *,
    on_parses_complete: OnParsesComplete | None = None,
) -> PipelineState:
    run = await session.get(PipelineRun, pipeline_run_id)
    if run is None:
        raise PipelineStateNotFoundError(pipeline_run_id)
    existing = pipeline_states.get(pipeline_run_id)
    callback = on_parses_complete
    if callback is None and existing is not None:
        callback = existing._on_parses_complete
    state = _state_from_run(run, on_parses_complete=callback)
    if existing is not None:
        state._timeout_tasks = existing._timeout_tasks
    pipeline_states[pipeline_run_id] = state
    return state


async def get_state(
    pipeline_run_id: PipelineRunId,
    *,
    session: AsyncSession | None = None,
) -> PipelineState:
    cached = pipeline_states.get(pipeline_run_id)
    if cached is not None:
        return cached
    if session is not None:
        return await _load_into_cache(session, pipeline_run_id)
    async with async_session() as db:
        return await _load_into_cache(db, pipeline_run_id)


async def persist_state(state: PipelineState, session: AsyncSession) -> None:
    run = await session.get(PipelineRun, state.pipeline_id)
    if run is None:
        raise PipelineStateNotFoundError(state.pipeline_id)
    _apply_state_to_run(run, state)
    await session.flush()
    pipeline_states[state.pipeline_id] = state


def remove_state(pipeline_run_id: PipelineRunId) -> None:
    state = pipeline_states.pop(pipeline_run_id, None)
    if state is not None:
        for task in state._timeout_tasks:
            if not task.done():
                task.cancel()


async def init_state_from_thread(
    session: AsyncSession,
    project_id: int,
    message: ThreadMessage,
    *,
    on_parses_complete: OnParsesComplete | None = None,
) -> PipelineState:
    """Insert ``pipeline_runs`` row and seed in-memory cache."""
    sources = modalities_from_message(message)
    run = PipelineRun(
        project_id=project_id,
        thread_message_id=message.id,
        url_count=len(message.input_urls or []),
        parse_expected=len(sources),
        parse_received=0,
        parse_pending=sorted(sources),
        parse_results={},
    )
    session.add(run)
    await session.flush()

    message.pipeline_run_id = run.id
    state = _state_from_run(run, on_parses_complete=on_parses_complete)
    pipeline_states[run.id] = state
    return state


def schedule_parse_timeouts(pipeline_run_id: PipelineRunId) -> None:
    state = pipeline_states.get(pipeline_run_id)
    if state is None:
        raise PipelineStateNotFoundError(pipeline_run_id)
    for source in list(state.parse_pending):
        task = asyncio.create_task(
            _parse_timeout_watch(pipeline_run_id, source),
            name=f"parse-timeout-{pipeline_run_id}-{source}",
        )
        state._timeout_tasks.append(task)


async def record_parse_result(
    session: AsyncSession,
    pipeline_run_id: PipelineRunId,
    source: ParseSource,
    payload: dict[str, Any],
) -> bool:
    state = await get_state(pipeline_run_id, session=session)
    if source not in PARSE_SOURCES:
        raise ValueError(f"Invalid parse source: {source}")
    if source not in state.parse_pending:
        return state.parse_received >= state.parse_expected

    state.parse_results[source] = payload
    state.parse_received += 1
    state.parse_pending.discard(source)
    await persist_state(state, session)
    return state.parse_received >= state.parse_expected


def synthetic_timeout_payload(source: ParseSource) -> dict[str, Any]:
    return ParseResultPayload(source=source, data=None, error="timeout").model_dump()


async def apply_parse_timeout(pipeline_run_id: PipelineRunId, source: ParseSource) -> bool:
    state = pipeline_states.get(pipeline_run_id)
    if state is None or source not in state.parse_pending:
        return False

    async with async_session() as db:
        complete = await record_parse_result(
            db,
            pipeline_run_id,
            source,
            synthetic_timeout_payload(source),
        )
        await db.commit()

    if complete and state._on_parses_complete is not None:
        await state._on_parses_complete(state)
    return complete


def _parse_timeout_delay_seconds(pipeline_run_id: PipelineRunId, source: ParseSource) -> float:
    if source != "url":
        return float(PARSE_TIMEOUT_SECONDS)
    state = pipeline_states.get(pipeline_run_id)
    if state is None:
        return float(PARSE_TIMEOUT_SECONDS)
    n = max(1, state.url_count)
    url_budget = float(PARSE_URL_TIMEOUT_FLOOR + PARSE_URL_TIMEOUT_PER_URL * n)
    if n > 1:
        url_budget += float(PARSE_URL_TIMEOUT_SYNTHESIS)
    return max(float(PARSE_TIMEOUT_SECONDS), url_budget)


async def _parse_timeout_watch(pipeline_run_id: PipelineRunId, source: ParseSource) -> None:
    try:
        delay = _parse_timeout_delay_seconds(pipeline_run_id, source)
        await asyncio.sleep(delay)
        await apply_parse_timeout(pipeline_run_id, source)
    except asyncio.CancelledError:
        raise


async def notify_parses_complete_if_ready(pipeline_run_id: PipelineRunId) -> None:
    state = pipeline_states.get(pipeline_run_id)
    if state is None:
        state = await get_state(pipeline_run_id)
    if state.parse_received >= state.parse_expected and state._on_parses_complete is not None:
        await state._on_parses_complete(state)


async def mark_brief_requested(state: PipelineState, session: AsyncSession) -> None:
    state.brief_requested = True
    await persist_state(state, session)


async def update_run_fields(
    session: AsyncSession,
    pipeline_run_id: PipelineRunId,
    **fields: Any,
) -> PipelineState:
    state = await get_state(pipeline_run_id, session=session)
    for key, value in fields.items():
        if hasattr(state, key) and not key.startswith("_"):
            setattr(state, key, value)
    await persist_state(state, session)
    return state


async def recover_running_projects(
    *,
    on_parses_complete: OnParsesComplete | None = None,
    reconcile_brief: Callable[[PipelineState], Awaitable[None]] | None = None,
) -> None:
    """Reload ``pipeline_runs`` for ``running`` projects after API restart."""
    async with async_session() as db:
        result = await db.execute(
            select(PipelineRun)
            .join(Project, PipelineRun.project_id == Project.id)
            .where(Project.status == ProjectStatus.running)
        )
        runs = result.scalars().all()
        for run in runs:
            if run.id in pipeline_states:
                continue
            await _recover_run(
                db,
                run,
                on_parses_complete=on_parses_complete,
                reconcile_brief=reconcile_brief,
            )


async def _recover_run(
    db: AsyncSession,
    run: PipelineRun,
    *,
    on_parses_complete: OnParsesComplete | None,
    reconcile_brief: Callable[[PipelineState], Awaitable[None]] | None,
) -> None:
    message = await db.get(ThreadMessage, run.thread_message_id)
    if message is None:
        logger.warning(
            "pipeline_run %s missing thread_message_id=%s; skipping",
            run.id,
            run.thread_message_id,
        )
        return

    brief = await db.scalar(select(DesignBrief).where(DesignBrief.project_id == run.project_id))
    if brief is not None and run.parse_received < run.parse_expected:
        run.parse_received = run.parse_expected
        run.parse_pending = []
        await db.flush()

    schema = await db.scalar(
        select(DesignSchema)
        .where(DesignSchema.project_id == run.project_id)
        .order_by(DesignSchema.created_at.desc())
        .limit(1)
    )
    components = (
        await db.scalars(select(Component).where(Component.project_id == run.project_id))
    ).all()

    if components:
        run.expected_components = len(components)
        run.resolved_components = sum(
            1
            for c in components
            if c.status in (ComponentStatus.validated, ComponentStatus.failed)
        )
        run.revision_round = max((c.revision_round for c in components), default=0)
    elif schema is not None and schema.component_specs:
        run.expected_components = len(schema.component_specs)

    project_status = await db.scalar(
        select(Project.status).where(Project.id == run.project_id)
    )
    if project_status == ProjectStatus.completed:
        run.run_complete = True

    await db.flush()

    state = _state_from_run(run, on_parses_complete=on_parses_complete)
    pipeline_states[run.id] = state

    if state.parse_pending:
        schedule_parse_timeouts(run.id)

    if (
        reconcile_brief is not None
        and state.parse_received >= state.parse_expected
        and not state.brief_requested
        and brief is None
    ):
        await reconcile_brief(state)

    logger.info(
        "recovered pipeline_run id=%s project_id=%s parse=%s/%s components=%s/%s",
        run.id,
        run.project_id,
        state.parse_received,
        state.parse_expected,
        state.resolved_components,
        state.expected_components,
    )
