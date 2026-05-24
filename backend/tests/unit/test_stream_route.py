"""HTTP tests for project SSE stream route."""

import asyncio
import unittest
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from httpx import ASGITransport, AsyncClient
from fastapi import FastAPI, HTTPException, status

from app.middleware.session_auth import get_current_user_id
from app.routers.stream import router as stream_router
from app.services import sse_service

# App without lifespan — avoids Rabbit consumer + cross-test event-loop issues.
_test_app = FastAPI()
_test_app.include_router(stream_router)


class StreamRouteTests(unittest.IsolatedAsyncioTestCase):
    def tearDown(self) -> None:
        sse_service._subscribers.clear()
        _test_app.dependency_overrides.clear()

    async def test_stream_requires_auth(self) -> None:
        async with AsyncClient(
            transport=ASGITransport(app=_test_app),
            base_url="http://test",
        ) as client:
            response = await client.get("/api/projects/1/stream")
        self.assertEqual(response.status_code, 401)

    async def test_stream_forbidden_for_other_user(self) -> None:
        async def deny_project(*_args, **_kwargs) -> None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Forbidden",
            )

        async def fake_user() -> int:
            return 1

        _test_app.dependency_overrides[get_current_user_id] = fake_user

        with patch(
            "app.routers.stream.get_project_for_user",
            new_callable=AsyncMock,
            side_effect=deny_project,
        ):
            async with AsyncClient(
                transport=ASGITransport(app=_test_app),
                base_url="http://test",
            ) as client:
                response = await client.get("/api/projects/1/stream")

        self.assertEqual(response.status_code, 403)

    async def test_stream_delivers_emitted_event(self) -> None:
        project_id = 42
        async def fake_user() -> int:
            return 1

        _test_app.dependency_overrides[get_current_user_id] = fake_user

        with patch(
            "app.routers.stream.get_project_for_user",
            new_callable=AsyncMock,
            return_value=None,
        ):
            async def emit_event() -> None:
                await asyncio.sleep(0.1)
                sse_service.deliver_local(
                    project_id,
                    {
                        "type": "design_brief_ready",
                        "projectId": project_id,
                        "pipelineId": str(uuid4()),
                    },
                )

            emitter = asyncio.create_task(emit_event())

            async with AsyncClient(
                transport=ASGITransport(app=_test_app),
                base_url="http://test",
            ) as client:
                async with client.stream(
                    "GET", f"/api/projects/{project_id}/stream"
                ) as response:
                    self.assertEqual(response.status_code, 200)
                    self.assertIn("text/event-stream", response.headers["content-type"])

                    body = ""
                    async for chunk in response.aiter_text():
                        body += chunk
                        if "design_brief_ready" in body:
                            break

            await emitter
            self.assertIn("event: message", body)
            self.assertIn("design_brief_ready", body)


if __name__ == "__main__":
    unittest.main()
