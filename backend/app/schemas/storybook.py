"""Storybook read API schemas (Phase 1a / 1c)."""

from __future__ import annotations

from typing import Any

from pydantic import Field, field_validator

from app.schemas.common import ApiModel, OrmResponseModel
from app.schemas.component import ComponentResponse
from app.services.variant_normalize import variants_for_api
from pandora_shared.enums import ComponentStatus, ProjectStatus


class SemanticTokenPair(ApiModel):
    background: str
    foreground: str


class TokenSchemaResponse(ApiModel):
    editable: list[str]
    semantic_pairs: list[SemanticTokenPair]


class ComponentSpecSummary(ApiModel):
    name: str
    type: str | None = None
    variants: list[str] = Field(default_factory=list)
    props: dict[str, Any] | list[Any] | None = None


class StorybookComponentSummary(ApiModel):
    id: int
    name: str
    status: ComponentStatus
    spec_index: int
    variants: list[dict[str, Any]] | None = None
    props: dict[str, Any] | list[Any] | None = None
    preview_available: bool
    tsx_preview: str | None = None
    css_preview: str | None = None
    error_reason: str | None = None

    @field_validator("variants", mode="before")
    @classmethod
    def _normalize_variants(cls, value: Any) -> list[dict[str, Any]] | None:
        return variants_for_api(value)


class StorybookSummary(ApiModel):
    total: int
    validated: int
    failed: int
    generating: int
    validating: int = 0
    revised: int = 0


class StorybookOverviewResponse(ApiModel):
    project_id: int
    project_status: ProjectStatus
    design_tokens: dict[str, Any] = Field(default_factory=dict)
    token_schema: TokenSchemaResponse
    global_config: dict[str, Any] = Field(default_factory=dict)
    component_specs: list[ComponentSpecSummary] = Field(default_factory=list)
    components: list[StorybookComponentSummary] = Field(default_factory=list)
    summary: StorybookSummary


class ComponentDetailResponse(ApiModel):
    project_id: int
    component: ComponentResponse
    spec: dict[str, Any] = Field(default_factory=dict)
    design_tokens: dict[str, Any] = Field(default_factory=dict)
    global_config: dict[str, Any] = Field(default_factory=dict)


class PatchTokensRequest(ApiModel):
    design_tokens: dict[str, Any] = Field(default_factory=dict)


class TokenPatchResponse(ApiModel):
    design_tokens: dict[str, Any] = Field(default_factory=dict)


class SuggestTokensRequest(ApiModel):
    message: str = Field(min_length=1, max_length=4096)


class SuggestTokensResponse(ApiModel):
    proposed_tokens: dict[str, Any] = Field(default_factory=dict)
    design_tokens: dict[str, Any] = Field(default_factory=dict)
    explanation: str


class ApplyTokensRequest(ApiModel):
    design_tokens: dict[str, Any] = Field(default_factory=dict)
    regenerate_components: bool = False


class ApplyTokensResponse(ApiModel):
    design_tokens: dict[str, Any] = Field(default_factory=dict)
    regenerate_queued: int = 0
    status: str


class ReviseComponentRequest(ApiModel):
    message: str = Field(min_length=1, max_length=4096)


class ReviseComponentResponse(ApiModel):
    component_id: int
    status: ComponentStatus
