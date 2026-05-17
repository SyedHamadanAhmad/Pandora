"""Start a pipeline run from a thread message (Phase 3 Step 4)."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import Project
from app.models.thread_message import ThreadMessage
from app.services import pipeline_state
from app.services.message_broker import MessageBroker
from app.services.storage_service import copy_thread_images_to_pipeline
from pandora_shared.enums import ProjectStatus
from pandora_shared.events import MessageEnvelope
from pandora_shared.queues import PARSE_IMAGE, PARSE_TEXT, PARSE_URL

PARSE_REQUEST_EVENT = "pandora.parse.request"


@dataclass(frozen=True)
class TriggerResult:
    pipeline_id: UUID
    status: ProjectStatus


async def trigger_pipeline_run(
    db: AsyncSession,
    broker: MessageBroker,
    project: Project,
    message: ThreadMessage,
) -> TriggerResult:
    """
    Assign run identity, persist running status, seed PipelineState, publish parse work.

    Call after the thread message row is committed (including image URLs).
    """
    pipeline_id = uuid4()

    if message.input_image_urls:
        message.input_image_urls = await copy_thread_images_to_pipeline(
            project.id,
            pipeline_id,
            message.input_image_urls,
        )

    message.pipeline_id = pipeline_id
    project.status = ProjectStatus.running
    await db.commit()
    await db.refresh(message)
    await db.refresh(project)

    pipeline_state.init_state_from_thread(project.id, pipeline_id, message)
    pipeline_state.schedule_parse_timeouts(pipeline_id)

    await _publish_parse_jobs(broker, project.id, pipeline_id, message)

    return TriggerResult(pipeline_id=pipeline_id, status=ProjectStatus.running)


async def _publish_parse_jobs(
    broker: MessageBroker,
    project_id: int,
    pipeline_id: UUID,
    message: ThreadMessage,
) -> None:
    sources = pipeline_state.modalities_from_message(message)
    for source in sources:
        queue_name, payload = _parse_job_for_source(source, message)
        envelope = MessageEnvelope(
            event=PARSE_REQUEST_EVENT,
            project_id=project_id,
            pipeline_id=pipeline_id,
            payload=payload,
        )
        await broker.publish(queue_name, envelope)


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
