"""Unit tests for SSE fan-out (local delivery + Redis publish)."""

import asyncio
import json
import unittest
from unittest.mock import AsyncMock, patch

from app.services import sse_service


class SseServiceTests(unittest.IsolatedAsyncioTestCase):
    def tearDown(self) -> None:
        sse_service._subscribers.clear()

    def test_format_sse_message(self) -> None:
        formatted = sse_service.format_sse_message(
            {"type": "design_brief_ready", "projectId": 1}
        )
        self.assertTrue(formatted.startswith("event: message\n"))
        self.assertIn("data: ", formatted)
        payload = json.loads(formatted.split("data: ", 1)[1].strip())
        self.assertEqual(payload["type"], "design_brief_ready")

    def test_format_sse_ping(self) -> None:
        self.assertEqual(sse_service.format_sse_ping(), ": ping\n\n")

    def test_channel_for_project_round_trip(self) -> None:
        channel = sse_service.channel_for_project(42)
        self.assertEqual(channel, "sse:project:42")
        self.assertEqual(sse_service.project_id_from_channel(channel), 42)

    def test_emit_without_subscribers_is_noop(self) -> None:
        sse_service.emit(999, {"type": "test"})

    async def test_subscriber_receives_delivered_event(self) -> None:
        received: list[dict] = []

        async def consume() -> None:
            async for event in sse_service.subscribe(7):
                received.append(event)
                return

        task = asyncio.create_task(consume())
        await asyncio.sleep(0.05)
        sse_service.deliver_local(7, {"type": "schema_ready", "projectId": 7})
        await asyncio.wait_for(task, timeout=1.0)

        self.assertEqual(received, [{"type": "schema_ready", "projectId": 7}])
        self.assertNotIn(7, sse_service._subscribers)

    async def test_deliver_local_drops_when_client_queue_full(self) -> None:
        queue: asyncio.Queue = asyncio.Queue(maxsize=1)
        sse_service._subscribers[3].add(queue)
        queue.put_nowait({"type": "first"})

        sse_service.deliver_local(3, {"type": "second"})
        sse_service.deliver_local(3, {"type": "third"})

        self.assertEqual(queue.qsize(), 1)
        self.assertEqual(queue.get_nowait()["type"], "first")

    async def test_publish_to_redis_uses_redis_when_connected(self) -> None:
        mock_redis = AsyncMock()
        with patch("app.services.sse_service.get_redis", return_value=mock_redis):
            await sse_service.publish_to_redis(5, {"type": "ping", "projectId": 5})
        mock_redis.publish.assert_awaited_once_with(
            "sse:project:5",
            '{"type":"ping","projectId":5}',
        )

    async def test_publish_to_redis_falls_back_without_redis(self) -> None:
        received: list[dict] = []

        async def consume() -> None:
            async for event in sse_service.subscribe(8):
                received.append(event)
                return

        task = asyncio.create_task(consume())
        await asyncio.sleep(0.05)
        with patch("app.services.sse_service.get_redis", return_value=None):
            await sse_service.publish_to_redis(8, {"type": "local"})
        await asyncio.wait_for(task, timeout=1.0)
        self.assertEqual(received, [{"type": "local"}])

    async def test_stream_chunks_yields_ping_on_idle(self) -> None:
        original = sse_service.HEARTBEAT_INTERVAL_SECONDS
        sse_service.HEARTBEAT_INTERVAL_SECONDS = 0.05
        try:
            agen = sse_service.stream_chunks(12)
            chunk = await asyncio.wait_for(agen.__anext__(), timeout=1.0)
        finally:
            sse_service.HEARTBEAT_INTERVAL_SECONDS = original
            await agen.aclose()

        self.assertEqual(chunk, ": ping\n\n")


if __name__ == "__main__":
    unittest.main()
