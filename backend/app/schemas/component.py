from datetime import datetime
from typing import Any

from pydantic import field_validator

from app.schemas.common import ApiModel, OrmResponseModel
from app.services.variant_normalize import variants_for_api
from pandora_shared.enums import ComponentStatus


class ComponentResponse(OrmResponseModel):
    id: int
    spec_index: int
    name: str
    status: ComponentStatus
    tsx_code: str | None
    css_code: str | None
    error_reason: str | None
    retry_count: int
    revision_round: int
    props: dict[str, Any] | list[Any] | None
    variants: list[dict[str, Any]] | None
    revision_instruction: str | None
    created_at: datetime
    updated_at: datetime

    @field_validator("variants", mode="before")
    @classmethod
    def _normalize_variants(cls, value: Any) -> list[dict[str, Any]] | None:
        return variants_for_api(value)


class ComponentListResponse(ApiModel):
    components: list[ComponentResponse]
