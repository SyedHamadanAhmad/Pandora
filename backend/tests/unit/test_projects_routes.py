"""HTTP tests for project routes."""

import unittest
from uuid import uuid4

from httpx import ASGITransport, AsyncClient

from app.main import app
from app.services.auth_service import SESSION_COOKIE


class ProjectRouteTests(unittest.IsolatedAsyncioTestCase):
    async def _register_and_login(self, client: AsyncClient) -> None:
        email = f"projects-{uuid4()}@example.com"
        password = "secret123"
        await client.post(
            "/api/auth/register",
            json={"email": email, "password": password},
        )
        login = await client.post(
            "/api/auth/login",
            json={"email": email, "password": password},
        )
        self.assertEqual(login.status_code, 200)
        client.cookies.update(login.cookies)

    async def test_projects_flow(self) -> None:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            unauth = await client.get("/api/projects/")
            self.assertEqual(unauth.status_code, 401)

            await self._register_and_login(client)

            create = await client.post(
                "/api/projects/",
                json={"name": "Marketing site"},
            )
            self.assertEqual(create.status_code, 201)
            created = create.json()
            self.assertEqual(created["name"], "Marketing site")
            self.assertEqual(created["status"], "pending")
            project_id = created["id"]

            listing = await client.get("/api/projects/")
            self.assertEqual(listing.status_code, 200)
            self.assertEqual(len(listing.json()["projects"]), 1)

            get_one = await client.get(f"/api/projects/{project_id}")
            self.assertEqual(get_one.status_code, 200)
            self.assertEqual(get_one.json()["id"], project_id)

            missing = await client.get("/api/projects/999999999")
            self.assertEqual(missing.status_code, 404)

            components = await client.get(f"/api/projects/{project_id}/components")
            self.assertEqual(components.status_code, 200)
            self.assertEqual(components.json(), {"components": []})

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as other_client:
            await self._register_and_login(other_client)
            forbidden = await other_client.get(f"/api/projects/{project_id}")
        self.assertEqual(forbidden.status_code, 403)


if __name__ == "__main__":
    unittest.main()
