"""Durable pipeline run coordination (Phase 0)."""

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.project import Project
    from app.models.thread_message import ThreadMessage


class PipelineRun(Base):
    __tablename__ = "pipeline_runs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("projects.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    thread_message_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("thread_messages.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    url_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    parse_expected: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    parse_received: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    parse_pending: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, server_default="[]"
    )
    parse_results: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default="{}"
    )
    expected_components: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    resolved_components: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    revision_round: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    run_complete: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    brief_requested: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    project: Mapped["Project"] = relationship(back_populates="pipeline_runs")
    thread_message: Mapped["ThreadMessage"] = relationship(back_populates="pipeline_run")
