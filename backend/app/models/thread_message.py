from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import BigInteger, DateTime, ForeignKey, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.types import message_role_enum
from pandora_shared.enums import MessageRole

if TYPE_CHECKING:
    from app.models.pipeline_run import PipelineRun
    from app.models.project import Project
    from app.models.user import User


class ThreadMessage(Base):
    __tablename__ = "thread_messages"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=False
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[MessageRole] = mapped_column(message_role_enum, nullable=False)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    input_image_urls: Mapped[list[Any] | None] = mapped_column(JSONB, nullable=True)
    input_urls: Mapped[list[Any] | None] = mapped_column(JSONB, nullable=True)
    pipeline_run_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("pipeline_runs.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    project: Mapped["Project"] = relationship(back_populates="thread_messages")
    user: Mapped["User"] = relationship(back_populates="thread_messages")
    pipeline_run: Mapped["PipelineRun | None"] = relationship(back_populates="thread_message")

    @property
    def pipeline_id(self) -> int | None:
        """API alias for ``pipeline_run_id`` (bigint run identity)."""
        return self.pipeline_run_id
