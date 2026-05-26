"""HTTP tests for thread routes."""

import io
import unittest
from unittest.mock import patch
from uuid import uuid4

from httpx import ASGITransport, AsyncClient

from app.main import app
from app.services.message_broker import MessageBroker


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

        class _FakeExchange:
            async def publish(self, message, routing_key: str) -> None:
                return None

        fake_channel = type("Ch", (), {"default_exchange": _FakeExchange()})()
        app.state.message_broker = MessageBroker(fake_channel)  # type: ignore[arg-type]

        with (
            patch("app.services.storage_service._put_object", return_value=None),
            patch(
                "app.services.pipeline_service.copy_thread_images_to_pipeline",
                side_effect=lambda _pid, _plid, urls: urls,
            ),
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
                self.assertIn("pipelineId", body)
                self.assertEqual(body["status"], "running")

                history = await client.get(f"/api/projects/{project_id}/thread/")
                self.assertEqual(history.status_code, 200)
                messages = history.json()["messages"]
                self.assertEqual(len(messages), 1)
                self.assertEqual(messages[0]["content"], "Modern SaaS dashboard")
                self.assertEqual(messages[0]["inputUrls"], ["https://example.com"])
                self.assertEqual(len(messages[0]["inputImageUrls"]), 1)
                self.assertEqual(messages[0]["pipelineId"], body["pipelineId"])

                too_many_urls = await client.post(
                    f"/api/projects/{project_id}/thread/",
                    data={
                        "content": "x",
                        "urls": '["https://a.com","https://b.com","https://c.com","https://d.com"]',
                    },
                )
                self.assertEqual(too_many_urls.status_code, 400)
    unittest.main()
