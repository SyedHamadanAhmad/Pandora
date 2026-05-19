"""Shared RabbitMQ connect / declare / consume helpers for stub workers."""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import Awaitable, Callable

import aio_pika
from aio_pika import DeliveryMode, Message
from aio_pika.abc import AbstractIncomingMessage, AbstractRobustConnection

from pandora_shared.events import MessageEnvelope
from pandora_shared.queues import ALL_QUEUES

logger = logging.getLogger(__name__)

PREFETCH_COUNT = 10

Handler = Callable[[AbstractIncomingMessage, aio_pika.abc.AbstractChannel], Awaitable[None]]


def rabbitmq_url() -> str:
    return os.environ.get("RABBITMQ_URL", "amqp://pandora:pandora@rabbitmq:5672/")


async def connect() -> AbstractRobustConnection:
    return await aio_pika.connect_robust(rabbitmq_url())


async def declare_topology(channel: aio_pika.abc.AbstractChannel) -> None:
    """Match backend ``app.rabbitmq.declare_topology`` (idempotent)."""
    for queue_name in ALL_QUEUES:
        dlq_name = f"{queue_name}.dlq"
        await channel.declare_queue(dlq_name, durable=True)
        await channel.declare_queue(
            queue_name,
            durable=True,
            arguments={
                "x-dead-letter-exchange": "",
                "x-dead-letter-routing-key": dlq_name,
            },
        )


def decode_envelope(body: bytes) -> MessageEnvelope:
    return MessageEnvelope.model_validate_json(body)


async def publish(
    channel: aio_pika.abc.AbstractChannel,
    queue_name: str,
    envelope: MessageEnvelope,
) -> None:
    body = envelope.model_dump_json().encode("utf-8")
    await channel.default_exchange.publish(
        Message(
            body=body,
            delivery_mode=DeliveryMode.PERSISTENT,
            content_type="application/json",
        ),
        routing_key=queue_name,
    )


async def _consume_queue(
    channel: aio_pika.abc.AbstractChannel,
    queue_name: str,
    handler: Handler,
) -> None:
    queue = await channel.declare_queue(queue_name, passive=True)
    async with queue.iterator() as queue_iter:
        async for message in queue_iter:
            try:
                await handler(message, channel)
            except Exception:
                logger.exception("stub handler failed queue=%s", queue_name)
                await message.nack(requeue=True)


async def run_consumers(
    connection: AbstractRobustConnection,
    bindings: list[tuple[str, Handler]],
) -> None:
    channel = await connection.channel()
    await channel.set_qos(prefetch_count=PREFETCH_COUNT)
    tasks = [
        asyncio.create_task(_consume_queue(channel, queue_name, handler), name=queue_name)
        for queue_name, handler in bindings
    ]
    try:
        await asyncio.gather(*tasks)
    except asyncio.CancelledError:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        raise


def configure_logging(name: str) -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
    logging.getLogger(name).setLevel(logging.INFO)
