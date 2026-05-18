"""Typed RabbitMQ payload models (Tech Spec §7.5)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

ParseSource = Literal["text", "image", "url"]

PARSE_SOURCES: frozenset[ParseSource] = frozenset({"text", "image", "url"})


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
