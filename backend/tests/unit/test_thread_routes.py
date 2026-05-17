"""HTTP tests for thread routes."""

import io
import unittest
from unittest.mock import patch
from uuid import uuid4

from httpx import ASGITransport, AsyncClient

from app.main import app


class ThreadRouteTests(unittest.IsolatedAsyncioTestCase):
    async def _auth_and_project(self, client: AsyncClient) -> int:
        email = f"thread-{uuid4()}@example.com"
        password = "secret123"
        await client.post(
            "/api/auth/register",
            json={"email": email, "password": password},
        )
        login = await client.post(
            "/api/auth/login",
            json={"email": email, "password": password},
        )
        client.cookies.update(login.cookies)
        project = await client.post(
            "/api/projects/",
            json={"name": "Thread test project"},
        )
        self.assertEqual(project.status_code, 201)
        return project.json()["id"]

    async def test_thread_multipart_flow(self) -> None:
        png_bytes = (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
            b"\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
        )

        with patch(
            "app.services.storage_service._put_object",
            return_value=None,
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                project_id = await self._auth_and_project(client)

                empty = await client.post(f"/api/projects/{project_id}/thread/")
                self.assertEqual(empty.status_code, 400)

                create = await client.post(
                    f"/api/projects/{project_id}/thread/",
                    data={
                        "content": "Modern SaaS dashboard",
                        "urls": '["https://example.com"]',
                    },
                    files=[
                        (
                            "images",
                            ("shot.png", io.BytesIO(png_bytes), "image/png"),
                        ),
                    ],
                )
                self.assertEqual(create.status_code, 201)
                body = create.json()
                self.assertIn("messageId", body)
                self.assertIn("createdAt", body)
                self.assertNotIn("pipelineId", body)

                history = await client.get(f"/api/projects/{project_id}/thread/")
                self.assertEqual(history.status_code, 200)
                messages = history.json()["messages"]
                self.assertEqual(len(messages), 1)
                self.assertEqual(messages[0]["content"], "Modern SaaS dashboard")
                self.assertEqual(messages[0]["inputUrls"], ["https://example.com"])
                self.assertEqual(len(messages[0]["inputImageUrls"]), 1)
                self.assertIsNone(messages[0]["pipelineId"])


if __name__ == "__main__":
    unittest.main()
