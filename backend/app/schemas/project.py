from datetime import datetime

from pydantic import Field

from app.schemas.common import ApiModel, OrmResponseModel
from pandora_shared.enums import ProjectStatus


class CreateProjectRequest(ApiModel):
    name: str = Field(min_length=1, max_length=255)


class ProjectResponse(OrmResponseModel):
    id: int
    name: str
    status: ProjectStatus
    created_at: datetime
    updated_at: datetime


class ProjectListResponse(ApiModel):
    projects: list[ProjectResponse]
