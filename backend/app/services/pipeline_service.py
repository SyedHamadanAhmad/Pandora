"""Start a pipeline run from a thread message (Phase 3 Step 4)."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import Project
from app.models.thread_message import ThreadMessage
from app.services import pipeline_state
from app.services.outbox import enqueue_outbox
from app.services.pipeline_consumer import make_parses_complete_callback
from app.services.storage_service import copy_thread_images_to_pipeline
from pandora_shared.enums import ProjectStatus
from pandora_shared.events import MessageEnvelope, PipelineEvent
from pandora_shared.queues import PARSE_IMAGE, PARSE_TEXT, PARSE_URL


@dataclass(frozen=True)
class TriggerResult:
    pipeline_id: int
    status: ProjectStatus


def parse_request_idempotency_key(pipeline_run_id: int, source: str) -> str:
    return f"{pipeline_run_id}:{PipelineEvent.PARSE_REQUEST}:{source}"


async def trigger_pipeline_run(
    db: AsyncSession,
    project: Project,
    message: ThreadMessage,
) -> TriggerResult:
    """
    Assign run identity, persist running status, seed PipelineState, enqueue parse work.

    Call after the thread message row is flushed (including image URLs).
    """
    state = await pipeline_state.init_state_from_thread(
        db,
        project.id,
        message,
        on_parses_complete=make_parses_complete_callback(),
    )
    pipeline_run_id = state.pipeline_id

    if message.input_image_urls:
        message.input_image_urls = await copy_thread_images_to_pipeline(
            project.id,
            pipeline_run_id,
            message.input_image_urls,
        )

    project.status = ProjectStatus.running
    await _enqueue_parse_jobs(db, project.id, pipeline_run_id, message)
    await db.commit()
    await db.refresh(message)
    await db.refresh(project)

    pipeline_state.schedule_parse_timeouts(pipeline_run_id)

    return TriggerResult(pipeline_id=pipeline_run_id, status=ProjectStatus.running)


async def _enqueue_parse_jobs(
    db: AsyncSession,
    project_id: int,
    pipeline_run_id: int,
    message: ThreadMessage,
) -> None:
    sources = pipeline_state.modalities_from_message(message)
    for source in sources:
        queue_name, payload = _parse_job_for_source(source, message)
        envelope = MessageEnvelope(
            event=PipelineEvent.PARSE_REQUEST,
            project_id=project_id,
            pipeline_id=pipeline_run_id,
            payload=payload,
        )
        await enqueue_outbox(
            db,
            queue_name,
            envelope,
            project_id=project_id,
            idempotency_key=parse_request_idempotency_key(pipeline_run_id, source),
        )


def _parse_job_for_source(
    source: str,
    message: ThreadMessage,
) -> tuple[str, dict]:
    if source == "text":
        return PARSE_TEXT, {"content": message.content}
    if source == "image":
        return PARSE_IMAGE, {"image_urls": message.input_image_urls or []}
    if source == "url":
        return PARSE_URL, {"urls": message.input_urls or []}
    raise ValueError(f"Unknown parse source: {source}")
