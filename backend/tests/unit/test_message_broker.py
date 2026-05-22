"""Unit tests for message_broker envelope serialization."""

import unittest
from uuid import uuid4

from aio_pika import DeliveryMode

from app.services.message_broker import decode_envelope, publish
from pandora_shared.events import MessageEnvelope


class MessageBrokerTests(unittest.IsolatedAsyncioTestCase):
    async def test_publish_uses_persistent_delivery(self) -> None:
        captured: dict = {}

        class FakeExchange:
            async def publish(self, message, routing_key: str) -> None:
                captured["message"] = message
                captured["routing_key"] = routing_key

        channel = type("Ch", (), {"default_exchange": FakeExchange()})()
        pipeline_id = 42
        envelope = MessageEnvelope(
            event="pandora.parse.request",
            project_id=1,
            pipeline_id=pipeline_id,
            payload={"content": "hello"},
        )

        await publish(channel, "pandora.parse.text", envelope)

        self.assertEqual(captured["routing_key"], "pandora.parse.text")
        self.assertEqual(captured["message"].delivery_mode, DeliveryMode.PERSISTENT)
        self.assertEqual(captured["message"].content_type, "application/json")

        decoded = decode_envelope(captured["message"].body)
        self.assertEqual(decoded.event, envelope.event)
        self.assertEqual(decoded.project_id, 1)
        self.assertEqual(decoded.pipeline_id, pipeline_id)
        self.assertEqual(decoded.payload, {"content": "hello"})


if __name__ == "__main__":
    unittest.main()
