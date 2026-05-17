from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.project import Project
    from app.models.session import Session
    from app.models.thread_message import ThreadMessage


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    sessions: Mapped[list["Session"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    projects: Mapped[list["Project"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    thread_messages: Mapped[list["ThreadMessage"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
