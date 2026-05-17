from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.component import Component
    from app.models.design_brief import DesignBrief
    from app.models.project import Project


class DesignSchema(Base):
    __tablename__ = "design_schemas"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=False
    )
    brief_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("design_briefs.id", ondelete="CASCADE"), nullable=False
    )
    design_tokens: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    global_config: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    component_specs: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB, nullable=True)
    component_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    project: Mapped["Project"] = relationship(back_populates="design_schemas")
    brief: Mapped["DesignBrief"] = relationship(back_populates="design_schemas")
    components: Mapped[list["Component"]] = relationship(
        back_populates="schema", cascade="all, delete-orphan"
    )
