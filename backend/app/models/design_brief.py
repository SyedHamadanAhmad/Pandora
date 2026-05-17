from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import BigInteger, DateTime, ForeignKey, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.design_schema import DesignSchema
    from app.models.project import Project


class DesignBrief(Base):
    __tablename__ = "design_briefs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("projects.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    color_tokens: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    typography_scale: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    spacing_system: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    design_flavour: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    tone: Mapped[str | None] = mapped_column(Text, nullable=True)
    component_list: Mapped[list[Any] | None] = mapped_column(JSONB, nullable=True)
    input_gaps: Mapped[list[Any] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    project: Mapped["Project"] = relationship(back_populates="design_brief")
    design_schemas: Mapped[list["DesignSchema"]] = relationship(
        back_populates="brief", cascade="all, delete-orphan"
    )
