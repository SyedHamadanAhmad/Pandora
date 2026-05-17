"""HTTP tests for auth routes."""

import unittest
from uuid import uuid4

from httpx import ASGITransport, AsyncClient

from app.main import app
from app.services.auth_service import SESSION_COOKIE


class AuthRouteTests(unittest.IsolatedAsyncioTestCase):
    async def test_register_login_logout_flow(self) -> None:
        email = f"routes-{uuid4()}@example.com"
        password = "secret123"

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            register = await client.post(
                "/api/auth/register",
                json={"email": email, "password": password},
            )
            self.assertEqual(register.status_code, 201)
            user_id = register.json()["userId"]
            self.assertIsInstance(user_id, int)

            duplicate = await client.post(
                "/api/auth/register",
                json={"email": email, "password": password},
            )
            self.assertEqual(duplicate.status_code, 409)

            bad_login = await client.post(
                "/api/auth/login",
                json={"email": email, "password": "wrong-password"},
            )
            self.assertEqual(bad_login.status_code, 401)

            login = await client.post(
                "/api/auth/login",
                json={"email": email, "password": password},
            )
            self.assertEqual(login.status_code, 200)
            self.assertEqual(login.json(), {"userId": user_id})
            self.assertIn(SESSION_COOKIE, login.cookies)

            logout = await client.post(
                "/api/auth/logout",
                cookies=login.cookies,
            )
            self.assertEqual(logout.status_code, 204)

            logout_again = await client.post(
                "/api/auth/logout",
                cookies=login.cookies,
            )
            self.assertEqual(logout_again.status_code, 401)

    async def test_logout_requires_session(self) -> None:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.post("/api/auth/logout")
        self.assertEqual(response.status_code, 401)


if __name__ == "__main__":
    unittest.main()
