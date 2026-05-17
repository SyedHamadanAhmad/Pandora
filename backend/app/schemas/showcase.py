from datetime import datetime
from typing import Any

from app.schemas.common import ApiModel, OrmResponseModel


class ShowcaseSceneResponse(OrmResponseModel):
    id: int
    scene_index: int
    scene_name: str | None
    scene_tsx_code: str | None
    scene_css_code: str | None
    components_used: list[Any] | None
    created_at: datetime


class ShowcaseListResponse(ApiModel):
    scenes: list[ShowcaseSceneResponse]
