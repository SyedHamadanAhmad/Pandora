from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.project import Project


class ShowcaseScene(Base):
    __tablename__ = "showcase_scenes"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=False
    )
    scene_index: Mapped[int] = mapped_column(Integer, nullable=False)
    scene_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    scene_tsx_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    scene_css_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    components_used: Mapped[list[Any] | None] = mapped_column(JSONB, nullable=True)
    variant_selections: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    showcase_bundle: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    project: Mapped["Project"] = relationship(back_populates="showcase_scenes")
