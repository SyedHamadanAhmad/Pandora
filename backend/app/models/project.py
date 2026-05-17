from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.types import project_status_enum
from pandora_shared.enums import ProjectStatus

if TYPE_CHECKING:
    from app.models.component import Component
    from app.models.design_brief import DesignBrief
    from app.models.design_schema import DesignSchema
    from app.models.processed_event import ProcessedEvent
    from app.models.showcase_scene import ShowcaseScene
    from app.models.thread_message import ThreadMessage
    from app.models.user import User


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[ProjectStatus] = mapped_column(
        project_status_enum,
        nullable=False,
        server_default=ProjectStatus.pending.value,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    user: Mapped["User"] = relationship(back_populates="projects")
    thread_messages: Mapped[list["ThreadMessage"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    design_brief: Mapped["DesignBrief | None"] = relationship(
        back_populates="project", uselist=False, cascade="all, delete-orphan"
    )
    design_schemas: Mapped[list["DesignSchema"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    components: Mapped[list["Component"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    showcase_scenes: Mapped[list["ShowcaseScene"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    processed_events: Mapped[list["ProcessedEvent"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
