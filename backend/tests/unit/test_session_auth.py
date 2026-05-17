"""Tests for session_auth dependency."""

import unittest
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from fastapi import HTTPException

from app.database import async_session
from app.middleware.session_auth import SESSION_COOKIE, get_current_user_id
from app.models.user import User
from app.services.auth_service import create_session, create_user, delete_session


class SessionAuthUnitTests(unittest.IsolatedAsyncioTestCase):
    async def test_missing_cookie_returns_401(self) -> None:
        with self.assertRaises(HTTPException) as ctx:
            await get_current_user_id(pandora_session=None, db=AsyncMock())
        self.assertEqual(ctx.exception.status_code, 401)
        self.assertEqual(ctx.exception.detail, "Not authenticated")

    async def test_invalid_uuid_returns_401(self) -> None:
        with self.assertRaises(HTTPException) as ctx:
            await get_current_user_id(pandora_session="not-a-uuid", db=AsyncMock())
        self.assertEqual(ctx.exception.status_code, 401)
        self.assertEqual(ctx.exception.detail, "Invalid session")

    async def test_unknown_session_returns_401(self) -> None:
        db = AsyncMock()
        with patch(
            "app.middleware.session_auth.auth_service.get_user_id_for_session",
            new_callable=AsyncMock,
            return_value=None,
        ):
            with self.assertRaises(HTTPException) as ctx:
                await get_current_user_id(pandora_session=str(uuid4()), db=db)
        self.assertEqual(ctx.exception.detail, "Session expired")


class SessionAuthDbTests(unittest.IsolatedAsyncioTestCase):
    async def test_valid_session_returns_user_id(self) -> None:
        from sqlalchemy import text

        try:
            async with async_session() as db:
                await db.execute(text("SELECT 1"))
        except Exception as exc:
            self.skipTest(f"Postgres not available: {exc}")

        email = f"session-auth-{uuid4()}@test.local"
        async with async_session() as db:
            user = await create_user(db, email, "secret123")
            session = await create_session(db, user.id)
            await db.commit()
            user_id = user.id
            session_value = str(session.id)

        async with async_session() as db:
            resolved = await get_current_user_id(
                pandora_session=session_value,
                db=db,
            )
            self.assertEqual(resolved, user_id)

        async with async_session() as db:
            await delete_session(db, session.id)
            await db.commit()

        async with async_session() as db:
            with self.assertRaises(HTTPException) as ctx:
                await get_current_user_id(pandora_session=session_value, db=db)
            self.assertEqual(ctx.exception.detail, "Session expired")

        async with async_session() as db:
            user = await db.get(User, user_id)
            if user is not None:
                await db.delete(user)
                await db.commit()


class SessionCookieConstantTests(unittest.TestCase):
    def test_session_cookie_name(self) -> None:
        self.assertEqual(SESSION_COOKIE, "pandora_session")


if __name__ == "__main__":
    unittest.main()
