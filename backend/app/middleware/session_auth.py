"""FastAPI dependencies for HttpOnly session cookie authentication."""

from __future__ import annotations

from uuid import UUID

from fastapi import Cookie, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services import auth_service

SESSION_COOKIE = auth_service.SESSION_COOKIE


async def get_current_user_id(
    pandora_session: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    db: AsyncSession = Depends(get_db),
) -> int:
    """
    Resolve the logged-in user from the ``pandora_session`` cookie.

    Authorization must not use ``userId`` from the request body or query string.
    """
    if not pandora_session:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    try:
        session_id = UUID(pandora_session)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid session",
        ) from None

    user_id = await auth_service.get_user_id_for_session(db, session_id)
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired",
        )
    return user_id
