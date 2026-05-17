"""Unit and integration tests for auth_service."""

import unittest
from uuid import uuid4

from app.database import async_session
from app.models.user import User
from app.services.auth_service import (
    DuplicateEmailError,
    create_session,
    create_user,
    delete_session,
    get_user_by_email,
    get_user_id_for_session,
    hash_password,
    verify_password,
)


class PasswordTests(unittest.TestCase):
    def test_hash_and_verify_round_trip(self) -> None:
        hashed = hash_password("secret123")
        self.assertTrue(hashed.startswith("$2"))
        self.assertTrue(verify_password("secret123", hashed))
        self.assertFalse(verify_password("wrong", hashed))


class AuthServiceDbTests(unittest.IsolatedAsyncioTestCase):
    async def test_user_and_session_flow(self) -> None:
        from sqlalchemy import text

        try:
            async with async_session() as db:
                await db.execute(text("SELECT 1"))
        except Exception as exc:
            self.skipTest(f"Postgres not available: {exc}")

        email = f"auth-{uuid4()}@test.local"
        async with async_session() as db:
            user = await create_user(db, email, "secret123")
            await db.commit()
            user_id = user.id

        async with async_session() as db:
            found = await get_user_by_email(db, email)
            self.assertIsNotNone(found)
            assert found is not None
            self.assertEqual(found.id, user_id)
            self.assertTrue(verify_password("secret123", found.password_hash))

        async with async_session() as db:
            with self.assertRaises(DuplicateEmailError):
                await create_user(db, email, "otherpass")
            await db.rollback()

        async with async_session() as db:
            session = await create_session(db, user_id)
            await db.commit()
            session_id = session.id

        async with async_session() as db:
            self.assertEqual(await get_user_id_for_session(db, session_id), user_id)

        async with async_session() as db:
            await delete_session(db, session_id)
            await db.commit()

        async with async_session() as db:
            self.assertIsNone(await get_user_id_for_session(db, session_id))

        async with async_session() as db:
            user = await db.get(User, user_id)
            if user is not None:
                await db.delete(user)
                await db.commit()


if __name__ == "__main__":
    unittest.main()
