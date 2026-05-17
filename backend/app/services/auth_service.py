"""Password hashing and server-side session helpers (Tech Spec §4)."""

from __future__ import annotations

import uuid
from uuid import UUID

import bcrypt
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.session import Session
from app.models.user import User

SESSION_COOKIE = "pandora_session"


class DuplicateEmailError(Exception):
    """Raised when registering an email that already exists."""


def hash_password(plain: str) -> str:
    """Return a bcrypt hash suitable for storing on ``users.password_hash``."""
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """Check a plaintext password against a stored bcrypt hash."""
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


async def get_user_by_email(db: AsyncSession, email: str) -> User | None:
    result = await db.execute(select(User).where(User.email == email))
    return result.scalar_one_or_none()


async def create_user(db: AsyncSession, email: str, password: str) -> User:
    """
    Insert a new user. Caller must ``commit()``.

    Raises:
        DuplicateEmailError: if ``email`` is already registered.
    """
    user = User(email=email, password_hash=hash_password(password))
    db.add(user)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise DuplicateEmailError(email) from exc
    return user


async def create_session(db: AsyncSession, user_id: int) -> Session:
    """Create a server-side session row. Caller must ``commit()``."""
    session = Session(id=uuid.uuid4(), user_id=user_id)
    db.add(session)
    await db.flush()
    return session


async def delete_session(db: AsyncSession, session_id: UUID) -> None:
    """Remove a session (logout). Caller must ``commit()``."""
    result = await db.execute(select(Session).where(Session.id == session_id))
    session = result.scalar_one_or_none()
    if session is not None:
        await db.delete(session)


async def get_user_id_for_session(db: AsyncSession, session_id: UUID) -> int | None:
    """Resolve a session cookie value to ``user_id``, or ``None`` if invalid."""
    result = await db.execute(
        select(Session.user_id).where(Session.id == session_id)
    )
    return result.scalar_one_or_none()
