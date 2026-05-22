"""In-memory pipeline run coordination (Tech Spec §15.4 POC)."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session
from app.models.component import Component
from app.models.design_brief import DesignBrief
from app.models.design_schema import DesignSchema
from app.models.project import Project
from app.models.thread_message import ThreadMessage
from pandora_shared.enums import ComponentStatus, ProjectStatus
from pandora_shared.payloads import ParseResultPayload

logger = logging.getLogger(__name__)

# Default watchdog for text/image (seconds).
PARSE_TIMEOUT_SECONDS = 150

# URL parse often exceeds a flat ceiling: crawl + one LLM per URL + optional multi-URL synthesis
# in ``ParseUrlAgent`` — see ``_parse_timeout_watch`` / ``_parse_timeout_delay``.
PARSE_URL_TIMEOUT_FLOOR = 120
PARSE_URL_TIMEOUT_PER_URL = 100
PARSE_URL_TIMEOUT_SYNTHESIS = 90

ParseSource = str  # "text" | "image" | "url"

PARSE_SOURCES: frozenset[ParseSource] = frozenset({"text", "image", "url"})

OnParsesComplete = Callable[["PipelineState"], Awaitable[None]]


class PipelineStateNotFoundError(KeyError):
    """Raised when no in-memory state exists for a pipeline_id."""


@dataclass
class PipelineState:
    project_id: int
    pipeline_id: UUID
    # len(thread URLs); scales URL parse watchdog (crawl + LLM per URL + synthesis).
    url_count: int = 0
    expected_components: int = 0
    resolved_components: int = 0
    parse_results: dict[str, dict[str, Any]] = field(default_factory=dict)
    parse_expected: int = 0
    parse_received: int = 0
    parse_pending: set[str] = field(default_factory=set)
    revision_round: int = 0
    # Set when holism verification finishes (post-revision); storybook regen skips holism gates.
    run_complete: bool = False
    _timeout_tasks: list[asyncio.Task[None]] = field(default_factory=list, repr=False, compare=False)
    _on_parses_complete: OnParsesComplete | None = field(default=None, repr=False, compare=False)


pipeline_states: dict[UUID, PipelineState] = {}


def modalities_from_message(message: ThreadMessage) -> set[ParseSource]:
    """Derive which parse workers to run from thread message inputs."""
    sources: set[ParseSource] = set()
    if message.content and message.content.strip():
        sources.add("text")
    if message.input_image_urls:
        sources.add("image")
    if message.input_urls:
        sources.add("url")
    return sources


def get_state(pipeline_id: UUID) -> PipelineState:
    """Return in-memory state for a pipeline run."""
    try:
        return pipeline_states[pipeline_id]
    except KeyError as exc:
        raise PipelineStateNotFoundError(pipeline_id) from exc


def remove_state(pipeline_id: UUID) -> None:
    """Drop in-memory state (explicit cleanup only; not called on pipeline complete)."""
    state = pipeline_states.pop(pipeline_id, None)
    if state is not None:
        for task in state._timeout_tasks:
            if not task.done():
                task.cancel()


def init_state_from_thread(
    project_id: int,
    pipeline_id: UUID,
    message: ThreadMessage,
    *,
    on_parses_complete: OnParsesComplete | None = None,
) -> PipelineState:
    """
    Seed counters from thread inputs and schedule per-source parse timeouts.

    ``on_parses_complete`` is invoked when ``parse_received >= parse_expected``
    (including synthetic timeout results). Wired by the pipeline consumer in Step 5.
    """
    sources = modalities_from_message(message)
    url_count = len(message.input_urls or [])
    state = PipelineState(
        project_id=project_id,
        pipeline_id=pipeline_id,
        url_count=url_count,
        parse_expected=len(sources),
        parse_pending=set(sources),
        _on_parses_complete=on_parses_complete,
    )
    pipeline_states[pipeline_id] = state
    return state


def schedule_parse_timeouts(pipeline_id: UUID) -> None:
    """Start per-source parse watchdog tasks (requires running event loop)."""
    state = get_state(pipeline_id)
    for source in list(state.parse_pending):
        task = asyncio.create_task(
            _parse_timeout_watch(pipeline_id, source),
            name=f"parse-timeout-{pipeline_id}-{source}",
        )
        state._timeout_tasks.append(task)


def record_parse_result(
    pipeline_id: UUID,
    source: ParseSource,
    payload: dict[str, Any],
) -> bool:
    """
    Store one parse result and bump counters.

    Returns True when all expected parses are in (ready for brief trigger).
    """
    state = get_state(pipeline_id)
    if source not in PARSE_SOURCES:
        raise ValueError(f"Invalid parse source: {source}")
    if source not in state.parse_pending:
        return state.parse_received >= state.parse_expected

    state.parse_results[source] = payload
    state.parse_received += 1
    state.parse_pending.discard(source)
    return state.parse_received >= state.parse_expected


def synthetic_timeout_payload(source: ParseSource) -> dict[str, Any]:
    return ParseResultPayload(source=source, data=None, error="timeout").model_dump()


async def apply_parse_timeout(pipeline_id: UUID, source: ParseSource) -> bool:
    """Inject a synthetic timeout result if the source is still pending."""
    state = pipeline_states.get(pipeline_id)
    if state is None or source not in state.parse_pending:
        return False

    complete = record_parse_result(pipeline_id, source, synthetic_timeout_payload(source))
    if complete and state._on_parses_complete is not None:
        await state._on_parses_complete(state)
    return complete


def _parse_timeout_delay_seconds(pipeline_id: UUID, source: ParseSource) -> float:
    """Wall-clock budget before synthetic timeout for this modality."""
    if source != "url":
        return float(PARSE_TIMEOUT_SECONDS)
    state = get_state(pipeline_id)
    n = max(1, state.url_count)
    # One crawl+LLM budget per URL; extra pass when multi-URL rollup synthesizes.
    url_budget = float(PARSE_URL_TIMEOUT_FLOOR + PARSE_URL_TIMEOUT_PER_URL * n)
    if n > 1:
        url_budget += float(PARSE_URL_TIMEOUT_SYNTHESIS)
    return max(float(PARSE_TIMEOUT_SECONDS), url_budget)


async def _parse_timeout_watch(pipeline_id: UUID, source: ParseSource) -> None:
    try:
        delay = _parse_timeout_delay_seconds(pipeline_id, source)
        await asyncio.sleep(delay)
        await apply_parse_timeout(pipeline_id, source)
    except asyncio.CancelledError:
        raise


async def notify_parses_complete_if_ready(pipeline_id: UUID) -> None:
    """Call the registered parses-complete hook when counters are satisfied."""
    state = pipeline_states.get(pipeline_id)
    if state is None:
        return
    if state.parse_received >= state.parse_expected and state._on_parses_complete is not None:
        await state._on_parses_complete(state)


async def recover_running_projects() -> None:
    """
    Best-effort rebuild of in-memory state for projects left ``running`` after API restart.

    Cannot restore interim ``parse_results`` blobs; parse phase is marked complete if a
    brief already exists, otherwise pending sources are re-armed with timeout watchers.
    """
    async with async_session() as db:
        result = await db.execute(
            select(Project).where(Project.status == ProjectStatus.running)
        )
        projects = result.scalars().all()
        for project in projects:
            await _recover_project(db, project)


async def _recover_project(db: AsyncSession, project: Project) -> None:
    message = await _latest_pipeline_message(db, project.id)
    if message is None or message.pipeline_id is None:
        logger.warning(
            "running project %s has no thread message with pipeline_id; skipping recovery",
            project.id,
        )
        return

    pipeline_id = message.pipeline_id
    if pipeline_id in pipeline_states:
        return

    sources = modalities_from_message(message)
    url_count = len(message.input_urls or [])
    state = PipelineState(
        project_id=project.id,
        pipeline_id=pipeline_id,
        url_count=url_count,
        parse_expected=len(sources),
    )

    brief = await db.scalar(
        select(DesignBrief).where(DesignBrief.project_id == project.id)
    )
    if brief is not None:
        state.parse_received = state.parse_expected
        state.parse_pending = set()
    else:
        state.parse_pending = set(sources)

    schema = await db.scalar(
        select(DesignSchema)
        .where(DesignSchema.project_id == project.id)
        .order_by(DesignSchema.created_at.desc())
        .limit(1)
    )
    components = (
        await db.scalars(select(Component).where(Component.project_id == project.id))
    ).all()

    if components:
        state.expected_components = len(components)
        state.resolved_components = sum(
            1
            for component in components
            if component.status in (ComponentStatus.validated, ComponentStatus.failed)
        )
        state.revision_round = max((c.revision_round for c in components), default=0)
    elif schema is not None and schema.component_specs:
        state.expected_components = len(schema.component_specs)

    pipeline_states[pipeline_id] = state
    if state.parse_pending:
        schedule_parse_timeouts(pipeline_id)
    logger.info(
        "recovered pipeline state project_id=%s pipeline_id=%s parse=%s/%s components=%s/%s",
        project.id,
        pipeline_id,
        state.parse_received,
        state.parse_expected,
        state.resolved_components,
        state.expected_components,
    )


async def _latest_pipeline_message(
    db: AsyncSession,
    project_id: int,
) -> ThreadMessage | None:
    result = await db.execute(
        select(ThreadMessage)
        .where(
            ThreadMessage.project_id == project_id,
            ThreadMessage.pipeline_id.isnot(None),
        )
        .order_by(ThreadMessage.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()
