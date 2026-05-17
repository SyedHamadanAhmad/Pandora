from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.project import Project


class ProcessedEvent(Base):
    __tablename__ = "processed_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    idempotency_key: Mapped[str] = mapped_column(String(512), unique=True, nullable=False)
    project_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=False
    )
    processed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    project: Mapped["Project"] = relationship(back_populates="processed_events")
