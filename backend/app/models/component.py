from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.types import component_status_enum
from pandora_shared.enums import ComponentStatus

if TYPE_CHECKING:
    from app.models.design_schema import DesignSchema
    from app.models.project import Project


class Component(Base):
    __tablename__ = "components"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=False
    )
    schema_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("design_schemas.id", ondelete="CASCADE"), nullable=False
    )
    spec_index: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    tsx_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    css_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[ComponentStatus] = mapped_column(
        component_status_enum,
        nullable=False,
        server_default=ComponentStatus.generating.value,
    )
    error_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    revision_round: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    props: Mapped[dict[str, Any] | list[Any] | None] = mapped_column(JSONB, nullable=True)
    variants: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB, nullable=True)
    revision_instruction: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    project: Mapped["Project"] = relationship(back_populates="components")
    schema: Mapped["DesignSchema"] = relationship(back_populates="components")
