"""Typed RabbitMQ payload models (Tech Spec §7.5)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

ParseSource = Literal["text", "image", "url"]

PARSE_SOURCES: frozenset[ParseSource] = frozenset({"text", "image", "url"})

VerificationPriority = Literal["P1", "P2", "P3"]


class ParseResultPayload(BaseModel):
    """Result from a parser agent on ``pandora.parse.results``."""

    source: ParseSource
    data: dict[str, Any] | None = None
    error: str | None = None


class ParseTextWorkPayload(BaseModel):
    content: str


class ParseImageWorkPayload(BaseModel):
    image_urls: list[str] = Field(default_factory=list)


class ParseUrlWorkPayload(BaseModel):
    urls: list[str] = Field(default_factory=list)


class BriefRequestWorkPayload(BaseModel):
    """Work on ``pandora.brief.request`` (merged parse outputs)."""

    sources: dict[str, Any] = Field(default_factory=dict)
    input_gaps: list[str] = Field(default_factory=list)


class BriefReadyPayload(BaseModel):
    """Result on ``pandora.brief.ready`` — matches ``_apply_brief_ready``."""

    color_tokens: dict[str, Any] | None = None
    typography_scale: dict[str, Any] | None = None
    spacing_system: dict[str, Any] | None = None
    design_flavour: str | None = None
    tone: str | None = None
    component_list: list[str] | None = None
    input_gaps: list[str] = Field(default_factory=list)


class ComponentSpecPayload(BaseModel):
    """One row in ``design_schemas.component_specs``."""

    name: str
    type: str | None = None
    variants: list[str] = Field(default_factory=list)
    layout: str | None = None

    model_config = {"extra": "allow"}


class SchemaRequestWorkPayload(BaseModel):
    """Work on ``pandora.schema.request`` (consumer sends the brief-ready body)."""

    model_config = {"extra": "allow"}

    brief_id: int | None = None
    design_flavour: str | None = None
    component_list: list[str] = Field(default_factory=list)

    @field_validator("component_list", mode="before")
    @classmethod
    def coalesce_component_list(cls, v: Any) -> list[str]:
        if v is None:
            return []
        if not isinstance(v, list):
            return []
        return [str(x).strip() for x in v if str(x).strip()]


class SchemaReadyPayload(BaseModel):
    """Result on ``pandora.schema.ready`` — matches ``_apply_schema_ready``."""

    design_tokens: dict[str, Any] | None = None
    global_config: dict[str, Any] | None = None
    component_specs: list[dict[str, Any]] = Field(default_factory=list)

    @field_validator("component_specs")
    @classmethod
    def cap_component_specs(cls, specs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if len(specs) > 15:
            raise ValueError("component_specs exceeds max 15")
        return specs


class ComponentGenerateWorkPayload(BaseModel):
    """Work on ``pandora.component.generate``."""

    spec: dict[str, Any] = Field(default_factory=dict)
    spec_index: int = 0
    design_tokens: dict[str, Any] | None = None
    global_config: dict[str, Any] | None = None
    revision_instruction: str | None = None


class ComponentCodePayload(BaseModel):
    """TSX/CSS output shared by generated and validated envelopes."""

    tsx_code: str
    css_code: str | None = None
    props: dict[str, Any] | None = None
    variants: list[str] = Field(default_factory=list)
    spec_type: str | None = None


class ComponentGeneratedPayload(ComponentCodePayload):
    """Result on ``pandora.component.generated`` (Feedback input)."""


class ComponentValidatedPayload(ComponentCodePayload):
    """Result on ``pandora.component.validated``."""


class ComponentFailedPayload(BaseModel):
    """Result on ``pandora.component.failed``."""

    error_reason: str | None = None
    error: str | None = None

    def resolved_error(self) -> str:
        return self.error_reason or self.error or "failed"


class VerificationIssuePayload(BaseModel):
    priority: VerificationPriority
    component_id: int | None = None
    message: str

    model_config = {"extra": "allow"}


class VerificationStartWorkPayload(BaseModel):
    """Work on ``pandora.verification.start``."""

    design_tokens: dict[str, Any] | None = None
    global_config: dict[str, Any] | None = None
    components: list[dict[str, Any]] = Field(default_factory=list)


class VerificationCompletePayload(BaseModel):
    """Result on ``pandora.verification.complete``."""

    issues: list[VerificationIssuePayload] = Field(default_factory=list)
    approved: bool = False
    revisions: list[dict[str, Any]] = Field(default_factory=list)

    def has_blocking_issues(self) -> bool:
        return any(issue.priority in ("P1", "P2") for issue in self.issues)


