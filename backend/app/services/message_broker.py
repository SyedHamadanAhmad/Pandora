"""RabbitMQ publish helpers for standard MessageEnvelope payloads (Tech Spec §7.5)."""

from __future__ import annotations

import aio_pika
from aio_pika import DeliveryMode, Message
from aio_pika.abc import AbstractChannel, AbstractRobustChannel

from pandora_shared.events import MessageEnvelope


async def open_publish_channel(
    connection: aio_pika.RobustConnection,
) -> AbstractRobustChannel:
    """Open a channel for publishing pipeline messages."""
    return await connection.channel()


async def publish(
    channel: AbstractChannel,
    queue_name: str,
    envelope: MessageEnvelope,
) -> None:
    """
    Publish a durable JSON message to a named queue via the default exchange.

    Queue names must come from pandora_shared.queues — not arbitrary strings.
    """
    body = envelope.model_dump_json().encode("utf-8")
    await channel.default_exchange.publish(
        Message(
            body=body,
            delivery_mode=DeliveryMode.PERSISTENT,
            content_type="application/json",
        ),
        routing_key=queue_name,
    )


def decode_envelope(body: bytes) -> MessageEnvelope:
    """Parse a RabbitMQ message body into a MessageEnvelope."""
    return MessageEnvelope.model_validate_json(body)


class MessageBroker:
    """Thin wrapper around a publish channel for pipeline services."""

    def __init__(self, channel: AbstractChannel) -> None:
        self._channel = channel

    @property
    def channel(self) -> AbstractChannel:
        return self._channel

    async def publish(self, queue_name: str, envelope: MessageEnvelope) -> None:
        await publish(self._channel, queue_name, envelope)
