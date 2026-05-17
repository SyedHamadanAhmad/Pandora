from datetime import datetime
from uuid import UUID

from app.schemas.common import ApiModel, OrmResponseModel
from pandora_shared.enums import MessageRole


class ThreadMessageResponse(OrmResponseModel):
    id: int
    role: MessageRole
    content: str | None
    input_image_urls: list[str] | None
    input_urls: list[str] | None
    pipeline_id: UUID | None
    created_at: datetime


class CreateThreadResponse(ApiModel):
    """Phase 2: no pipelineId — assigned in Phase 3."""

    message_id: int
    created_at: datetime


class ThreadListResponse(ApiModel):
    messages: list[ThreadMessageResponse]
