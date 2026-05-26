"""Unit tests for SSE fan-out (local delivery + Redis stream/pubsub)."""

import asyncio
import json
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services import sse_service


class _FakePipeline:
    def __init__(self) -> None:
        self.xadd = MagicMock()
        self.publish = MagicMock()

    async def execute(self) -> list:
        return ["1700000001000-0", 1]

    async def __aenter__(self) -> "_FakePipeline":
        return self

    async def __aexit__(self, *_args: object) -> None:
        return None


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

    def test_format_sse_message_with_sse_id(self) -> None:
        formatted = sse_service.format_sse_message(
            {"type": "schema_ready", "projectId": 1, "sseId": "1700000001000-0"}
        )
        self.assertTrue(formatted.startswith("id: 1700000001000-0\n"))
        self.assertIn("event: message\n", formatted)

    def test_format_sse_ping(self) -> None:
        self.assertEqual(sse_service.format_sse_ping(), ": ping\n\n")

    def test_channel_and_stream_keys_use_hash_tag(self) -> None:
        self.assertEqual(sse_service.channel_for_project(42), "sse:{42}:pub")
        self.assertEqual(sse_service.stream_key_for_project(42), "sse:{42}:stream")
        self.assertEqual(sse_service.project_id_from_channel("sse:{42}:pub"), 42)

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

    async def test_publish_to_redis_uses_multi_exec_pipeline(self) -> None:
        mock_redis = MagicMock()
        mock_redis.pipeline.return_value = _FakePipeline()
        payload = {"type": "ping", "projectId": 5}

        with patch("app.services.sse_service.get_redis", return_value=mock_redis):
            await sse_service.publish_to_redis(5, payload)

        mock_redis.pipeline.assert_called_once_with(transaction=True)
        pipe = mock_redis.pipeline.return_value
        pipe.xadd.assert_called_once()
        pipe.publish.assert_called_once_with(
            "sse:{5}:pub",
            '{"type":"ping","projectId":5}',
        )
        pipe.execute.assert_awaited_once()

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

    async def test_replay_stream_yields_events_with_sse_id(self) -> None:
        mock_redis = AsyncMock()
        mock_redis.xrange = AsyncMock(
            return_value=[
                (
                    "1700000001001-0",
                    {"payload": '{"type":"component_validated","projectId":42}'},
                ),
            ]
        )

        with patch("app.services.sse_service.get_redis", return_value=mock_redis):
            events = [
                event
                async for event in sse_service.replay_stream(42, after_id="1700000001000-0")
            ]

        mock_redis.xrange.assert_awaited_once_with(
            "sse:{42}:stream",
            min="(1700000001000-0",
            max="+",
        )
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["type"], "component_validated")
        self.assertEqual(events[0]["sseId"], "1700000001001-0")

    async def test_replay_stream_replays_full_buffer_on_first_connect(self) -> None:
        mock_redis = AsyncMock()
        mock_redis.xrange = AsyncMock(
            return_value=[
                (
                    "1700000001000-0",
                    {"payload": '{"type":"design_brief_ready","projectId":7}'},
                ),
            ]
        )

        with patch("app.services.sse_service.get_redis", return_value=mock_redis):
            events = [event async for event in sse_service.replay_stream(7, after_id=None)]

        mock_redis.xrange.assert_awaited_once_with("sse:{7}:stream", min="-", max="+")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["type"], "design_brief_ready")
        self.assertEqual(events[0]["sseId"], "1700000001000-0")

    async def test_stream_chunks_replays_before_live(self) -> None:
        replayed = {"type": "schema_ready", "projectId": 12, "sseId": "99-0"}

        async def fake_replay(_project_id: int, *, after_id: str | None):
            if after_id:
                yield replayed

        with patch("app.services.sse_service.replay_stream", fake_replay):
            agen = sse_service.stream_chunks(12, last_event_id="98-0")
            first = await asyncio.wait_for(agen.__anext__(), timeout=1.0)
            await agen.aclose()

        self.assertIn("id: 99-0", first)
        self.assertIn("schema_ready", first)

    async def test_stream_chunks_replays_on_first_connect(self) -> None:
        replayed = {"type": "design_brief_ready", "projectId": 12, "sseId": "1-0"}

        async def fake_replay(_project_id: int, *, after_id: str | None):
            if after_id is None:
                yield replayed

        with patch("app.services.sse_service.replay_stream", fake_replay):
            agen = sse_service.stream_chunks(12)
            first = await asyncio.wait_for(agen.__anext__(), timeout=1.0)
            await agen.aclose()

        self.assertIn("id: 1-0", first)
        self.assertIn("design_brief_ready", first)

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
