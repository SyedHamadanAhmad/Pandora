"""Unit tests for Redis → local SSE relay (W-B04)."""

from __future__ import annotations

import asyncio
import json
import unittest
from unittest.mock import MagicMock, patch

from app.services import sse_service
from app.services.sse_relay import run_sse_relay


class SseRelayDeliveryTests(unittest.IsolatedAsyncioTestCase):
    def tearDown(self) -> None:
        sse_service._subscribers.clear()

    async def test_relay_forwards_pmessage_to_local_subscriber(self) -> None:
        received: list[dict] = []

        async def consume() -> None:
            async for event in sse_service.subscribe(42):
                received.append(event)
                return

        consumer = asyncio.create_task(consume())
        await asyncio.sleep(0.05)

        shutdown = asyncio.Event()
        delivered = False

        class FakePubSub:
            async def psubscribe(self, _pattern: str) -> None:
                return None

            async def get_message(self, **_kwargs) -> dict | None:
                nonlocal delivered
                if shutdown.is_set():
                    return None
                if not delivered:
                    delivered = True
                    return {
                        "type": "pmessage",
                        "channel": "sse:{42}:pub",
                        "data": json.dumps({"type": "schema_ready", "projectId": 42}),
                    }
                await asyncio.sleep(0.02)
                return None

            async def punsubscribe(self, _pattern: str) -> None:
                return None

            async def aclose(self) -> None:
                return None

        fake_redis = MagicMock()
        fake_redis.pubsub.return_value = FakePubSub()

        with patch("app.services.sse_relay.get_redis", return_value=fake_redis):
            relay = asyncio.create_task(run_sse_relay(shutdown_event=shutdown))
            await asyncio.wait_for(consumer, timeout=2.0)
            shutdown.set()
            relay.cancel()
            try:
                await relay
            except asyncio.CancelledError:
                pass

        self.assertEqual(received, [{"type": "schema_ready", "projectId": 42}])


if __name__ == "__main__":
    unittest.main()
